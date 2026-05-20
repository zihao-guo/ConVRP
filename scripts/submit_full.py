#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path


ROOT = Path("/home/zeio99/Alv")
DATA_ROOT = Path("/mnt/e/currentWORK/AAA_Project/P3/data")
REGISTRY = ROOT / "state" / "run_registry.jsonl"
RAW_ROOT = ROOT / "results" / "raw"
LOG_ROOT = ROOT / "results" / "logs"
METHODS = ("BC", "BD", "SAA-BC", "SAA-BD")
STANDALONE_TIME_LIMIT_SECONDS = 10 * 60 * 60
SAA_SAMPLE_TIME_LIMIT_SECONDS = 30 * 60


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", action="append", choices=METHODS)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backend", choices=["auto", "slurm", "tmux", "nohup"], default="auto")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    methods = tuple(args.method or METHODS)
    instances = sorted((DATA_ROOT / "processed").glob("omega*/*/*.json"))
    jobs = [(instance, method) for instance in instances for method in methods]
    if args.limit is not None:
        jobs = jobs[: args.limit]
    backend = choose_backend(args.backend)
    print(json.dumps({"backend": backend, "jobs": len(jobs), "dry_run": args.dry_run}))
    if args.dry_run:
        return 0

    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)

    for instance, method in jobs:
        submit_run(instance, method, backend, seed=args.seed)
    return 0


def choose_backend(requested: str) -> str:
    if requested != "auto":
        return requested
    if shutil.which("sbatch"):
        return "slurm"
    if shutil.which("tmux"):
        return "tmux"
    return "nohup"


def submit_run(instance: Path, method: str, backend: str, *, seed: int) -> None:
    time_limit = time_limit_for_method(method)
    config = {
        "method": method,
        "solver": "gurobi",
        "threads": 1,
        "mip_gap": 1e-5,
        "seed": seed,
        "time_limit_seconds": time_limit,
        "paper_time_protocol": "BC/BD full Omega 10h; SAA sample problems 30min each, evaluation time additional",
    }
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
    instance_id = instance.stem
    run_id = f"{method.lower().replace('-', '_')}__{instance_id}__{config_hash}"
    raw_result = RAW_ROOT / method / f"{run_id}.json"
    log_path = LOG_ROOT / method / f"{run_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    command = (
        "cd /home/zeio99/Alv && "
        "source scripts/activate_env.sh && "
        "PYTHONPATH=src python scripts/run_single.py "
        f"--run-id {run_id} --instance-json {instance} --method {method} "
        f"--raw-result-path {raw_result} --time-limit {time_limit} --seed {seed}"
    )
    record = {
        "run_id": run_id,
        "instance_id": instance_id,
        "instance_path": str(instance),
        "method": method,
        "config_hash": config_hash,
        "status": "pending",
        "submit_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "start_time": None,
        "end_time": None,
        "raw_result_path": str(raw_result),
        "log_path": str(log_path),
        "backend": backend,
        "pid": None,
        "slurm_job_id": None,
        "command": command,
        "time_limit_seconds": time_limit,
        "paper_time_protocol": config["paper_time_protocol"],
    }

    if backend == "slurm":
        result = subprocess.run(["sbatch", "--parsable", "--output", str(log_path), "--wrap", command], text=True, capture_output=True, check=True)
        record["slurm_job_id"] = result.stdout.strip()
        record["status"] = "running"
    elif backend == "tmux":
        session = run_id[:80].replace(".", "_")
        subprocess.run(["tmux", "new-session", "-d", "-s", session, f"{command} > {log_path} 2>&1"], check=True)
        record["pid"] = f"tmux:{session}"
        record["status"] = "running"
    else:
        handle = log_path.open("w", encoding="utf-8")
        proc = subprocess.Popen(["bash", "-lc", command], stdout=handle, stderr=subprocess.STDOUT)
        record["pid"] = proc.pid
        record["status"] = "running"

    with REGISTRY.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def time_limit_for_method(method: str) -> int:
    if method in {"BC", "BD"}:
        return STANDALONE_TIME_LIMIT_SECONDS
    if method in {"SAA-BC", "SAA-BD"}:
        return SAA_SAMPLE_TIME_LIMIT_SECONDS
    raise ValueError(f"unknown method {method}")


if __name__ == "__main__":
    raise SystemExit(main())
