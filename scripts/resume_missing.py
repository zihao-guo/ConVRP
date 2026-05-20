#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


REGISTRY = Path("/home/zeio99/Alv/state/run_registry.jsonl")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    records = [json.loads(line) for line in REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()] if REGISTRY.exists() else []
    resubmitted = []
    for record in records:
        raw_path = Path(record["raw_result_path"])
        failed = False
        if raw_path.exists():
            try:
                failed = json.loads(raw_path.read_text(encoding="utf-8")).get("status") == "failed"
            except json.JSONDecodeError:
                failed = True
        missing = not raw_path.exists()
        if args.force or missing or failed:
            log_path = Path(record["log_path"])
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handle = log_path.open("a", encoding="utf-8")
            proc = subprocess.Popen(["bash", "-lc", record["command"]], stdout=handle, stderr=subprocess.STDOUT)
            new_record = dict(record)
            new_record["pid"] = proc.pid
            new_record["status"] = "running"
            new_record["resubmitted_from"] = record["run_id"]
            with REGISTRY.open("a", encoding="utf-8") as registry:
                registry.write(json.dumps(new_record, sort_keys=True) + "\n")
            resubmitted.append(record["run_id"])
    print(json.dumps({"resubmitted": resubmitted, "count": len(resubmitted)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

