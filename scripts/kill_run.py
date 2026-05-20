#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
from pathlib import Path


REGISTRY = Path("/home/zeio99/Alv/state/run_registry.jsonl")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    args = parser.parse_args()
    records = [json.loads(line) for line in REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]
    matches = [record for record in records if record["run_id"] == args.run_id]
    if not matches:
        raise SystemExit(f"unknown run_id: {args.run_id}")
    record = matches[-1]
    if record.get("slurm_job_id"):
        subprocess.run(["scancel", str(record["slurm_job_id"])], check=True)
    elif isinstance(record.get("pid"), int):
        os.kill(int(record["pid"]), signal.SIGTERM)
    elif isinstance(record.get("pid"), str) and str(record["pid"]).startswith("tmux:"):
        subprocess.run(["tmux", "kill-session", "-t", str(record["pid"]).split(":", 1)[1]], check=True)
    else:
        raise SystemExit(f"run has no killable pid/job id: {args.run_id}")
    print(json.dumps({"killed": args.run_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

