#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path


REGISTRY = Path("/home/zeio99/Alv/state/run_registry.jsonl")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()

    while True:
        print(json.dumps(summarize(), indent=2, sort_keys=True))
        if not args.watch:
            return 0
        time.sleep(args.interval)


def summarize() -> dict[str, object]:
    records = list(read_latest_registry().values())
    counts = Counter()
    missing_raw = []
    for record in records:
        status = inferred_status(record)
        counts[status] += 1
        if status == "done" and not Path(record["raw_result_path"]).exists():
            missing_raw.append(record["run_id"])
    return {
        "total": len(records),
        "pending": counts["pending"],
        "running": counts["running"],
        "done": counts["done"],
        "failed": counts["failed"],
        "timeout": counts["timeout"],
        "missing_raw_result_files": missing_raw,
    }


def read_registry() -> list[dict[str, object]]:
    if not REGISTRY.exists():
        return []
    return [json.loads(line) for line in REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_latest_registry() -> dict[str, dict[str, object]]:
    latest: dict[str, dict[str, object]] = {}
    for record in read_registry():
        latest[str(record["run_id"])] = record
    return latest


def inferred_status(record: dict[str, object]) -> str:
    raw = Path(str(record["raw_result_path"]))
    if raw.exists():
        try:
            result = json.loads(raw.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return "failed"
        return "failed" if result.get("status") == "failed" else "done"
    pid = record.get("pid")
    if isinstance(pid, int) and Path(f"/proc/{pid}").exists():
        return "running"
    if record.get("status") == "running" and isinstance(pid, int):
        return "pending"
    if isinstance(pid, str) and pid.startswith("tmux:"):
        session = pid.split(":", 1)[1]
        return "running" if tmux_session_exists(session) else "pending"
    if record.get("slurm_job_id"):
        return "running"
    return str(record.get("status", "pending"))


def tmux_session_exists(session: str) -> bool:
    if not shutil.which("tmux"):
        return False
    result = subprocess.run(["tmux", "has-session", "-t", session], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


if __name__ == "__main__":
    raise SystemExit(main())
