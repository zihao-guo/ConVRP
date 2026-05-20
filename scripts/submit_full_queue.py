#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from scripts.submit_full import METHODS, time_limit_for_method


ROOT = Path("/home/zeio99/Alv")
DATA_ROOT = Path("/mnt/e/currentWORK/AAA_Project/P3/data")
REGISTRY = ROOT / "state" / "run_registry.jsonl"
RAW_ROOT = ROOT / "results" / "raw"
LOG_ROOT = ROOT / "results" / "logs"
LOCK = ROOT / "state" / "locks" / "full_experiment_queue.lock"
MANAGER_SESSION = "alv_full_experiment_manager"


@dataclass
class RunningChild:
    pid_ref: int | str
    process: subprocess.Popen[bytes] | None = None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit", action="store_true", help="Initialize the full 552-job registry and start a background queue manager.")
    parser.add_argument("--worker", action="store_true", help="Run the queue worker in the foreground.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--poll-interval", type=int, default=30)
    args = parser.parse_args()

    if args.concurrency < 1:
        raise SystemExit("--concurrency must be >= 1")
    if args.submit == args.worker:
        raise SystemExit("choose exactly one of --submit or --worker")

    if args.submit:
        if args.dry_run:
            summary = {"planned": len(plan_full_jobs(DATA_ROOT)), "created": 0, "already_registered": 0}
        else:
            summary = ensure_full_registry(data_root=DATA_ROOT, registry_path=REGISTRY, seed=args.seed)
        summary["dry_run"] = args.dry_run
        summary["concurrency"] = args.concurrency
        summary["expected_total_jobs"] = len(plan_full_jobs(DATA_ROOT))
        if not args.dry_run:
            summary["manager"] = start_background_manager(args.concurrency, args.seed, args.poll_interval)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    return worker_loop(concurrency=args.concurrency, poll_interval=args.poll_interval)


def plan_full_jobs(data_root: Path) -> list[tuple[Path, str]]:
    instances = sorted((data_root / "processed").glob("omega*/*/*.json"))
    return [(instance, method) for instance in instances for method in METHODS]


def ensure_full_registry(*, data_root: Path, registry_path: Path, seed: int) -> dict[str, int]:
    jobs = plan_full_jobs(data_root)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {record["run_id"] for record in read_latest_records(registry_path).values()}
    created = 0
    with registry_path.open("a", encoding="utf-8") as handle:
        for instance, method in jobs:
            record = build_pending_record(instance, method, seed=seed)
            if record["run_id"] in existing:
                continue
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            created += 1
    return {"planned": len(jobs), "created": created, "already_registered": len(jobs) - created}


def build_pending_record(instance: Path, method: str, *, seed: int) -> dict[str, object]:
    time_limit = time_limit_for_method(method)
    config = {
        "method": method,
        "solver": "gurobi",
        "threads": 1,
        "mip_gap": 1e-5,
        "seed": seed,
        "time_limit_seconds": time_limit,
    }
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
    instance_id = instance.stem
    run_id = f"{method.lower().replace('-', '_')}__{instance_id}__{config_hash}"
    raw_result = RAW_ROOT / method / f"{run_id}.json"
    log_path = LOG_ROOT / method / f"{run_id}.log"
    command = (
        "cd /home/zeio99/Alv && "
        "source scripts/activate_env.sh && "
        "PYTHONPATH=src:. python scripts/run_single.py "
        f"--run-id {run_id} --instance-json {instance} --method {method} "
        f"--raw-result-path {raw_result} --time-limit {time_limit} --seed {seed}"
    )
    return {
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
        "backend": "queue",
        "pid": None,
        "slurm_job_id": None,
        "command": command,
        "time_limit_seconds": time_limit,
        "paper_time_protocol": "BC/BD full Omega 10h; SAA sample problems 30min each, evaluation time additional",
    }


def start_background_manager(concurrency: int, seed: int, poll_interval: int) -> str:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    command = (
        "cd /home/zeio99/Alv && "
        "source scripts/activate_env.sh && "
        f"PYTHONPATH=src:. python scripts/submit_full_queue.py --worker --concurrency {concurrency} "
        f"--seed {seed} --poll-interval {poll_interval}"
    )
    log_path = LOG_ROOT / "full_experiment_manager.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("tmux"):
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", MANAGER_SESSION, f"{command} >> {log_path} 2>&1"],
            check=True,
        )
        return f"tmux:{MANAGER_SESSION}"
    handle = log_path.open("a", encoding="utf-8")
    proc = subprocess.Popen(["bash", "-lc", command], stdout=handle, stderr=subprocess.STDOUT)
    return f"pid:{proc.pid}"


def worker_loop(*, concurrency: int, poll_interval: int) -> int:
    if LOCK.exists():
        raise SystemExit(f"queue lock exists: {LOCK}")
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    running: dict[str, RunningChild] = {}
    try:
        while True:
            latest = read_latest_records(REGISTRY)
            for run_id, child in list(running.items()):
                exit_code = child_exit_code(child, latest[run_id])
                if exit_code is None:
                    continue
                record = latest[run_id]
                raw_path = Path(str(record["raw_result_path"]))
                status = "done" if exit_code == 0 and raw_path.exists() else "failed"
                append_record(REGISTRY, {**record, "status": status, "end_time": timestamp(), "exit_code": exit_code})
                del running[run_id]

            latest = read_latest_records(REGISTRY)
            pending = [
                record
                for record in latest.values()
                if inferred_registry_status(record) == "pending" and record["run_id"] not in running
            ]
            while pending and len(running) < concurrency:
                record = pending.pop(0)
                child = start_child(record)
                running[str(record["run_id"])] = child
                append_record(
                    REGISTRY,
                    {**record, "status": "running", "pid": child.pid_ref, "start_time": timestamp()},
                )

            latest = read_latest_records(REGISTRY)
            unfinished = [
                record
                for record in latest.values()
                if inferred_registry_status(record) in {"pending", "running"}
            ]
            if not unfinished and not running:
                return 0
            time.sleep(poll_interval)
    finally:
        LOCK.unlink(missing_ok=True)


def start_child(record: dict[str, object]) -> RunningChild:
    log_path = Path(str(record["log_path"]))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = Path(str(record["raw_result_path"]))
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("tmux"):
        session = tmux_child_session_name(str(record["run_id"]))
        command = f"{record['command']} >> {log_path} 2>&1"
        subprocess.run(["tmux", "new-session", "-d", "-s", session, str(command)], check=True)
        return RunningChild(pid_ref=f"tmux:{session}")
    handle = log_path.open("ab")
    proc = subprocess.Popen(["bash", "-lc", str(record["command"])], stdout=handle, stderr=subprocess.STDOUT)
    return RunningChild(pid_ref=proc.pid, process=proc)


def child_exit_code(child: RunningChild, record: dict[str, object]) -> int | None:
    if child.process is not None:
        return child.process.poll()
    if isinstance(child.pid_ref, str) and child.pid_ref.startswith("tmux:"):
        session = child.pid_ref.split(":", 1)[1]
        if tmux_session_exists(session):
            return None
        raw_path = Path(str(record["raw_result_path"]))
        return 0 if raw_path.exists() else 1
    return 1


def read_latest_records(registry_path: Path) -> dict[str, dict[str, object]]:
    latest: dict[str, dict[str, object]] = {}
    if not registry_path.exists():
        return latest
    for line in registry_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        latest[str(record["run_id"])] = record
    return latest


def append_record(registry_path: Path, record: dict[str, object]) -> None:
    with registry_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def inferred_registry_status(record: dict[str, object]) -> str:
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
    return str(record.get("status", "pending"))


def tmux_child_session_name(run_id: str) -> str:
    safe = run_id.replace(".", "_").replace("/", "_")
    digest = hashlib.sha1(run_id.encode()).hexdigest()[:8]
    return f"alv_job_{safe[:70]}_{digest}"


def tmux_session_exists(session: str) -> bool:
    if not shutil.which("tmux"):
        return False
    result = subprocess.run(["tmux", "has-session", "-t", session], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


if __name__ == "__main__":
    raise SystemExit(main())
