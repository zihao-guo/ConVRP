#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from scripts.poll_runs import summarize


ROOT = Path("/home/zeio99/Alv")
MONITOR_LOG = ROOT / "results" / "metadata" / "full_experiment_monitor.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()

    MONITOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    while True:
        snapshot = summarize()
        snapshot["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with MONITOR_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, sort_keys=True) + "\n")
        print(json.dumps(snapshot, sort_keys=True), flush=True)
        if snapshot["pending"] == 0 and snapshot["running"] == 0:
            return 0 if snapshot["failed"] == 0 and snapshot["timeout"] == 0 else 2
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
