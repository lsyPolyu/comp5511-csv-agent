"""Batch experiment runner (real DeepSeek API).

Examples (Windows PowerShell, from the project folder):
  .\\.venv\\Scripts\\python.exe -m evaluation.runner --split dev --repeats 1 --out results/smoke.jsonl
  .\\.venv\\Scripts\\python.exe -m evaluation.runner --split formal --repeats 3 --out results/formal.jsonl
  .\\.venv\\Scripts\\python.exe -m evaluation.runner --faults --repeats 3 --out results/faults.jsonl
Add --dry-run to print the plan without calling the API. Re-running the same
command resumes: finished runs are skipped; runs that ended in api_error or
timeout are retried once and both records are kept.
"""

from __future__ import annotations

import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

from comp5511.controller import MODES, SYSTEM_PROMPT, AgentConfig, run_agent
from comp5511.datasets import load_csv
from comp5511.llm import DeepSeekClient
from comp5511.runlog import append_run, read_runs
from comp5511.state import AnalysisSession
from comp5511.tools import TOOL_SPECS
from evaluation.faults import Injector, load_faults
from evaluation.references import DATA_FILES, all_references, load_tasks
from evaluation.scoring import score_run, snapshot

NOTES = json.loads(Path(__file__).with_name("data_notes.json").read_text(encoding="utf-8"))
RETRYABLE = ("api_error", "timeout")


def plan_runs(args) -> list[dict]:
    """Interleave modes inside each (task, repeat) so time effects hit all modes alike."""
    jobs = []
    if args.faults:
        for fault in load_faults():
            for repeat in range(args.repeats):
                for mode in args.modes:
                    jobs.append({"kind": "fault", "task_id": fault["task_id"], "fault": fault,
                                 "mode": mode, "repeat": repeat})
    else:
        for task in load_tasks(args.split):
            for repeat in range(args.repeats):
                for mode in args.modes:
                    jobs.append({"kind": "natural", "task_id": task["task_id"], "fault": None,
                                 "mode": mode, "repeat": repeat})
    return jobs


def job_key(job: dict) -> str:
    fault_id = job["fault"]["fault_id"] if job.get("fault") else (job.get("fault_id") or "-")
    return f"{job['kind']}|{job['task_id']}|{fault_id}|{job['mode']}|{job['repeat']}"


def run_one(job: dict, tasks: dict, refs: dict, data: dict, model: str | None) -> dict:
    task = tasks[job["task_id"]]
    session = AnalysisSession()
    session.replace_dataset(load_csv(data[task["dataset"]], DATA_FILES[task["dataset"]].name))
    injector = Injector(job["fault"]) if job["fault"] else None
    llm = DeepSeekClient(model=model)
    run = run_agent(task["question"], session, llm, AgentConfig(mode=job["mode"]),
                    data_notes=NOTES[task["dataset"]], injector=injector)
    record = {"kind": job["kind"], "task_id": task["task_id"], "dataset": task["dataset"],
              "type": task["type"], "mode": job["mode"], "repeat": job["repeat"],
              "fault_id": job["fault"]["fault_id"] if job["fault"] else None,
              "fault_triggered": bool(injector and injector.triggered),
              "run": run.to_dict(), **snapshot(session, run)}
    record["status"], record["answer"] = run.status, run.answer
    record["score"] = score_run(task, refs[task["task_id"]], record)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="formal", choices=["formal", "dev"])
    parser.add_argument("--faults", action="store_true", help="run the 10 fault cases instead of natural tasks")
    parser.add_argument("--modes", nargs="+", default=list(MODES), choices=list(MODES))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default=None, help="DeepSeek model id (default: env DEEPSEEK_MODEL or deepseek-chat)")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None, help="only the first N pending runs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    load_dotenv()

    jobs = plan_runs(args)
    done = {}
    for record in read_runs(args.out):
        if "manifest" in record:
            continue
        key = job_key(record)
        done.setdefault(key, []).append(record["status"])
    pending = [job for job in jobs if job_key(job) not in done
               or (all(status in RETRYABLE for status in done[job_key(job)]) and len(done[job_key(job)]) < 2)]
    if args.limit:
        pending = pending[: args.limit]
    print(f"planned {len(jobs)} runs, already logged {len(done)}, to run now {len(pending)}")
    if args.dry_run or not pending:
        return

    tasks = {task["task_id"]: task for task in load_tasks()}
    refs = all_references()
    data = {name: path.read_bytes() for name, path in DATA_FILES.items()}
    probe = DeepSeekClient(model=args.model)
    append_run(args.out, {"manifest": {"model": probe.model, "modes": args.modes, "repeats": args.repeats,
                                       "split": None if args.faults else args.split, "faults": args.faults,
                                       "system_prompt": SYSTEM_PROMPT, "tool_specs": TOOL_SPECS,
                                       "temperature": probe.temperature, "max_tokens": probe.max_tokens}})
    lock = threading.Lock()
    finished = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(run_one, job, tasks, refs, data, args.model): job for job in pending}
        for future in as_completed(futures):
            job = futures[future]
            try:
                record = future.result()
            except Exception as exc:  # keep going; the failure is logged and can be retried
                record = {"kind": job["kind"], "task_id": job["task_id"], "mode": job["mode"],
                          "repeat": job["repeat"], "fault_id": job["fault"]["fault_id"] if job["fault"] else None,
                          "status": "api_error", "error": f"{type(exc).__name__}: {exc}",
                          "score": {"success": False, "reason": "runner_error"}}
            with lock:
                append_run(args.out, record)
                finished += 1
                print(f"[{finished}/{len(pending)}] {job_key(job)} -> {record['status']} "
                      f"{'OK' if record['score']['success'] else record['score']['reason']}", flush=True)


if __name__ == "__main__":
    main()
