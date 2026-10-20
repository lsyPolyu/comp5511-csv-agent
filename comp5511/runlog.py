"""Append-only JSONL run logs (one line per agent run). Never stores API keys."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def append_run(path: str | Path, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, default=str, ensure_ascii=False) + "\n")


def read_runs(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
