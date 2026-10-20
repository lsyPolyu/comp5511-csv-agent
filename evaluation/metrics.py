"""Compute metrics and charts from the JSONL logs; every number is recomputable.

  .\\.venv\\Scripts\\python.exe -m evaluation.metrics --natural results/formal.jsonl --faults results/faults.jsonl
Writes results/summary.md, results/metrics.json and PNG charts in results/.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from comp5511.controller import MODES
from comp5511.runlog import read_runs

RETRYABLE = ("api_error", "timeout")


def final_records(path) -> list[dict]:
    """One record per run key: the last non-retryable record if any, else the last one."""
    groups = defaultdict(list)
    for record in read_runs(path):
        if "manifest" in record:
            continue
        key = (record["kind"], record["task_id"], record.get("fault_id"), record["mode"], record["repeat"])
        groups[key].append(record)
    chosen = []
    for records in groups.values():
        good = [record for record in records if record["status"] not in RETRYABLE]
        chosen.append((good or records)[-1])
    return chosen


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * q
    low, high = math.floor(index), math.ceil(index)
    return values[low] + (values[high] - values[low]) * (index - low)


def bootstrap_ci(records, resamples=2000, seed=0):
    """95% CI of the success rate, resampling tasks (repeats stay together)."""
    by_task = defaultdict(list)
    for record in records:
        by_task[record["task_id"]].append(1 if record["score"]["success"] else 0)
    tasks = list(by_task)
    if not tasks:
        return None, None
    rng = random.Random(seed)
    rates = []
    for _ in range(resamples):
        sample = [score for task in rng.choices(tasks, k=len(tasks)) for score in by_task[task]]
        rates.append(sum(sample) / len(sample))
    return percentile(rates, 0.025), percentile(rates, 0.975)


def mcnemar(records, mode_a, mode_b):
    """Exact McNemar test on runs paired by (task, repeat)."""
    outcome = {(r["task_id"], r["repeat"], r["mode"]): r["score"]["success"] for r in records}
    pairs = {(task, repeat) for task, repeat, mode in outcome}
    b = c = 0
    for task, repeat in pairs:
        a_ok, b_ok = outcome.get((task, repeat, mode_a)), outcome.get((task, repeat, mode_b))
        if a_ok is None or b_ok is None:
            continue
        b += a_ok and not b_ok
        c += b_ok and not a_ok
    n = b + c
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)
    return {"only_" + mode_a: b, "only_" + mode_b: c, "p_value": p}


def cost(records):
    latency = [r["run"]["latency_s"] for r in records if r.get("run")]
    tokens = [r["run"]["prompt_tokens"] + r["run"]["completion_tokens"] for r in records
              if r.get("run") and r["run"]["prompt_tokens"] is not None]
    return {
        "median_latency_s": median(latency) if latency else None,
        "p95_latency_s": percentile(latency, 0.95),
        "mean_model_requests": sum(r["run"]["model_requests"] for r in records if r.get("run")) / max(1, len(latency)),
        "mean_tool_calls": sum(r["run"]["tool_calls"] for r in records if r.get("run")) / max(1, len(latency)),
        "mean_tokens": sum(tokens) / len(tokens) if tokens else None,
        "tokens_known_runs": len(tokens),
        "total_prompt_tokens": sum(r["run"]["prompt_tokens"] for r in records if r.get("run") and r["run"]["prompt_tokens"] is not None),
        "total_completion_tokens": sum(r["run"]["completion_tokens"] for r in records if r.get("run") and r["run"]["completion_tokens"] is not None),
    }


def summarize(natural, faults):
    out = {"natural": {}, "faults": {}, "paired": {}}
    modes = [mode for mode in MODES if any(r["mode"] == mode for r in natural + faults)]
    for mode in modes:
        records = [r for r in natural if r["mode"] == mode]
        if records:
            successes = sum(r["score"]["success"] for r in records)
            low, high = bootstrap_ci(records)
            out["natural"][mode] = {
                "runs": len(records), "successes": successes, "success_rate": successes / len(records),
                "ci95": [low, high], "status": dict(Counter(r["status"] for r in records)),
                "failure_reasons": dict(Counter(r["score"]["reason"] for r in records if not r["score"]["success"])),
                "repairs_used_runs": sum(1 for r in records if r.get("run") and r["run"]["repairs"] > 0),
                **cost(records),
            }
        frecords = [r for r in faults if r["mode"] == mode]
        if frecords:
            triggered = [r for r in frecords if r.get("fault_triggered")]
            recovered = sum(r["score"]["success"] for r in triggered)
            out["faults"][mode] = {
                "runs": len(frecords), "triggered": len(triggered), "recovered": recovered,
                "recovery_rate": recovered / len(triggered) if triggered else None,
                "status": dict(Counter(r["status"] for r in triggered)), **cost(triggered),
            }
    for other in modes:
        if other != "baseline" and natural:
            out["paired"][f"baseline_vs_{other}"] = mcnemar(natural, "baseline", other)
    return out


def _bar_chart(path, title, labels, values, ylabel, errors=None):
    figure = Figure(figsize=(6, 4), dpi=150, layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    bars = axes.bar(labels, values, color=["#9aa5b1", "#5b8def", "#1f4fbf"][: len(labels)],
                    yerr=errors, capsize=6 if errors else 0)
    for bar, value in zip(bars, values):
        axes.annotate(f"{value:.0%}" if ylabel.endswith("(%)") else f"{value:.2f}",
                      (bar.get_x() + bar.get_width() / 2, value), ha="center", va="bottom",
                      xytext=(0, 3), textcoords="offset points")
    axes.set(title=title, ylabel=ylabel)
    if ylabel.endswith("(%)"):
        axes.set_ylim(0, 1.08)
        axes.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    axes.spines[["top", "right"]].set_visible(False)
    figure.savefig(path)


def write_outputs(summary, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    lines = ["# Experiment summary", ""]
    if summary["natural"]:
        lines += ["## Natural tasks", "", "| Mode | Runs | Success rate | 95% CI | Median latency (s) | p95 latency (s) | Mean model requests | Mean tokens |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for mode, m in summary["natural"].items():
            ci = m["ci95"]
            lines.append(f"| {mode} | {m['runs']} | {m['success_rate']:.1%} | {ci[0]:.1%}-{ci[1]:.1%} | "
                         f"{m['median_latency_s']} | {m['p95_latency_s']:.2f} | {m['mean_model_requests']:.2f} | "
                         f"{m['mean_tokens'] if m['mean_tokens'] is None else round(m['mean_tokens'])} |")
        lines += ["", "Failure reasons: " + json.dumps({k: v['failure_reasons'] for k, v in summary['natural'].items()}), ""]
        for name, test in summary["paired"].items():
            lines.append(f"- McNemar {name}: {test}")
        modes = list(summary["natural"])
        rates = [summary["natural"][m]["success_rate"] for m in modes]
        errors = [[rate - summary["natural"][m]["ci95"][0] for m, rate in zip(modes, rates)],
                  [summary["natural"][m]["ci95"][1] - rate for m, rate in zip(modes, rates)]]
        _bar_chart(out_dir / "success_rate.png", "Task success rate (natural tasks)", modes, rates,
                   "Success rate (%)", errors)
        _bar_chart(out_dir / "model_requests.png", "Mean model requests per run", modes,
                   [summary["natural"][m]["mean_model_requests"] for m in modes], "Requests")
    if summary["faults"]:
        lines += ["", "## Injected faults", "", "| Mode | Runs | Triggered | Recovered | Recovery rate |", "| --- | --- | --- | --- | --- |"]
        for mode, m in summary["faults"].items():
            rate = "n/a" if m["recovery_rate"] is None else f"{m['recovery_rate']:.1%}"
            lines.append(f"| {mode} | {m['runs']} | {m['triggered']} | {m['recovered']} | {rate} |")
        modes = [m for m in summary["faults"] if summary["faults"][m]["recovery_rate"] is not None]
        if modes:
            _bar_chart(out_dir / "recovery_rate.png", "Recovery rate on injected faults", modes,
                       [summary["faults"][m]["recovery_rate"] for m in modes], "Recovery rate (%)")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--natural", default="results/formal.jsonl")
    parser.add_argument("--faults", default="results/faults.jsonl")
    parser.add_argument("--out-dir", default="results")
    args = parser.parse_args(argv)
    natural = final_records(args.natural)
    faults = final_records(args.faults)
    summary = summarize(natural, faults)
    write_outputs(summary, Path(args.out_dir))
    print((Path(args.out_dir) / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
