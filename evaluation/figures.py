"""Report figures and key numbers, recomputed from the JSONL logs.

  .\\.venv\\Scripts\\python.exe -m evaluation.figures
Writes results/figures/*.png and results/analysis_numbers.json.
"""

from __future__ import annotations

import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from evaluation.faults import load_faults
from evaluation.metrics import final_records

MODES = ["baseline", "raw_retry", "proposed"]
COLORS = {"raw_retry": "#7aa6e8", "proposed": "#1f4fbf"}


def mcnemar(records, mode_a, mode_b):
    outcome = {(r.get("fault_id") or r["task_id"], r["repeat"], r["mode"]): r["score"]["success"] for r in records}
    a_only = b_only = 0
    for item, repeat in {(k[0], k[1]) for k in outcome}:
        a, b = outcome.get((item, repeat, mode_a)), outcome.get((item, repeat, mode_b))
        if a is None or b is None:
            continue
        a_only += a and not b
        b_only += b and not a
    n = a_only + b_only
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(a_only, b_only) + 1)) / 2 ** n)
    return {"only_" + mode_a: a_only, "only_" + mode_b: b_only, "p_value": p}


def _cost(records, mode, key):
    runs = [r["run"] for r in records if r["mode"] == mode]
    if key == "tokens":
        return st.mean(run["prompt_tokens"] + run["completion_tokens"] for run in runs)
    if key == "latency":
        return st.median(run["latency_s"] for run in runs)
    return st.mean(run[key] for run in runs)


def _rate(records, mode):
    runs = [r for r in records if r["mode"] == mode]
    return sum(r["score"]["success"] for r in runs) / len(runs)


def main(natural_path="results/formal.jsonl", faults_path="results/faults.jsonl", out="results"):
    natural, faults = final_records(natural_path), final_records(faults_path)
    out = Path(out)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    panels = [("tool_calls", "Tool calls per run"), ("model_requests", "Model requests per run"),
              ("tokens", "Tokens per run"), ("latency", "Median latency (s)")]
    numbers = {
        "natural_success": {m: _rate(natural, m) for m in MODES},
        "fault_recovery": {m: _rate(faults, m) for m in MODES},
        "natural_cost": {m: {k: _cost(natural, m, k) for k, _ in panels} for m in MODES},
        "fault_cost": {m: {k: _cost(faults, m, k) for k, _ in panels} | {"repairs": _cost(faults, m, "repairs")}
                       for m in MODES},
        "mcnemar_faults": {f"{a}_vs_{b}": mcnemar(faults, a, b)
                           for a, b in (("baseline", "raw_retry"), ("baseline", "proposed"), ("raw_retry", "proposed"))},
        "total_tokens": {"prompt": sum(r["run"]["prompt_tokens"] for r in natural + faults),
                         "completion": sum(r["run"]["completion_tokens"] for r in natural + faults)},
    }
    (out / "analysis_numbers.json").write_text(json.dumps(numbers, indent=1), encoding="utf-8")

    # Figure 1: natural success vs fault recovery
    figure = Figure(figsize=(7, 4.2), dpi=200, layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    width, xs = 0.36, range(len(MODES))
    groups = [(numbers["natural_success"], "#c9d1db", "Natural tasks (120 runs per mode)", -1),
              (numbers["fault_recovery"], "#1f4fbf", "Injected faults (30 runs per mode)", 1)]
    for values, color, label, side in groups:
        bars = axes.bar([x + side * width / 2 for x in xs], [values[m] for m in MODES], width, color=color, label=label)
        for bar in bars:
            axes.annotate(f"{bar.get_height():.0%}", (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                          ha="center", va="bottom", xytext=(0, 3), textcoords="offset points", fontsize=9)
    axes.set_xticks(list(xs), MODES)
    axes.set_ylim(0, 1.1)
    axes.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    axes.set(ylabel="Task success rate", title="All modes solve natural tasks; only retry modes recover from faults")
    axes.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=2)
    axes.spines[["top", "right"]].set_visible(False)
    figure.savefig(out / "figures" / "fig1_success_vs_recovery.png")

    # Figure 2: cost of recovery on injected faults
    figure = Figure(figsize=(9, 3.2), dpi=200, layout="constrained")
    FigureCanvasAgg(figure)
    for axes, (key, title) in zip(figure.subplots(1, 4), panels):
        values = [numbers["fault_cost"][m][key] for m in MODES[1:]]
        bars = axes.bar(MODES[1:], values, color=[COLORS[m] for m in MODES[1:]])
        for bar in bars:
            text = f"{bar.get_height():,.0f}" if key == "tokens" else f"{bar.get_height():.2f}"
            axes.annotate(text, (bar.get_x() + bar.get_width() / 2, bar.get_height()), ha="center", va="bottom",
                          xytext=(0, 2), textcoords="offset points", fontsize=8)
        axes.set_title(title, fontsize=9)
        axes.set_ylim(0, max(values) * 1.2)
        axes.tick_params(labelsize=8)
        axes.spines[["top", "right"]].set_visible(False)
    figure.suptitle("On injected faults, structured feedback recovers with fewer calls, tokens and seconds", fontsize=10)
    figure.savefig(out / "figures" / "fig2_fault_cost.png")

    # Figure 3: per-fault recovery grid
    grid = defaultdict(lambda: defaultdict(int))
    for record in faults:
        grid[record["fault_id"]][record["mode"]] += record["score"]["success"]
    cases = load_faults()
    data = [[grid[case["fault_id"]][m] / 3 for m in MODES] for case in cases]
    figure = Figure(figsize=(6.5, 4.6), dpi=200, layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    axes.imshow(data, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    for i, case in enumerate(cases):
        for j, mode in enumerate(MODES):
            axes.text(j, i, f"{grid[case['fault_id']][mode]}/3", ha="center", va="center", fontsize=8,
                      color="white" if data[i][j] > 0.6 else "black")
    axes.set_xticks(range(len(MODES)), MODES)
    axes.set_yticks(range(len(cases)), [f"{c['fault_id']} {c['kind']}" for c in cases], fontsize=8)
    axes.set_title("Recovered runs per injected fault (3 repeats)", fontsize=10)
    figure.savefig(out / "figures" / "fig3_per_fault.png")
    print(json.dumps(numbers, indent=1))


if __name__ == "__main__":
    main()
