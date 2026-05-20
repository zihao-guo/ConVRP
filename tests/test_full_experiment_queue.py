from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import scripts.poll_runs as poll_runs
from scripts.submit_full_queue import ensure_full_registry, inferred_registry_status, plan_full_jobs


class FullExperimentQueueTests(unittest.TestCase):
    def test_plan_full_jobs_requires_all_methods_for_every_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            for name in ["a__omega100__alpha20", "b__omega500__alpha80"]:
                path = data_root / "processed" / "omega100" / "A" / f"{name}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")

            jobs = plan_full_jobs(data_root)

        self.assertEqual(len(jobs), 8)
        self.assertEqual({method for _, method in jobs}, {"BC", "BD", "SAA-BC", "SAA-BD"})

    def test_registry_initialization_is_full_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_root = root / "data"
            registry = root / "state" / "run_registry.jsonl"
            for name in ["a__omega100__alpha20", "b__omega500__alpha80"]:
                path = data_root / "processed" / "omega100" / "A" / f"{name}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")

            first = ensure_full_registry(data_root=data_root, registry_path=registry, seed=0)
            second = ensure_full_registry(data_root=data_root, registry_path=registry, seed=0)
            records = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(first["created"], 8)
        self.assertEqual(second["created"], 0)
        self.assertEqual(len(records), 8)
        self.assertTrue(all(record["status"] == "pending" for record in records))

    def test_poll_runs_counts_latest_registry_record_per_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "run_registry.jsonl"
            registry.write_text(
                "\n".join(
                    [
                        json.dumps({"run_id": "r1", "status": "pending", "raw_result_path": "/tmp/missing-r1.json"}),
                        json.dumps({"run_id": "r1", "status": "running", "pid": 99999999, "raw_result_path": "/tmp/missing-r1.json"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            old_registry = poll_runs.REGISTRY
            poll_runs.REGISTRY = registry
            try:
                summary = poll_runs.summarize()
            finally:
                poll_runs.REGISTRY = old_registry

        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["pending"], 1)

    def test_queue_treats_dead_running_pid_without_raw_as_pending_for_restart(self) -> None:
        record = {
            "run_id": "dead-running",
            "status": "running",
            "pid": 99999999,
            "raw_result_path": "/tmp/alv-definitely-missing-raw.json",
        }

        self.assertEqual(inferred_registry_status(record), "pending")

    def test_queue_treats_missing_tmux_session_without_raw_as_pending_for_restart(self) -> None:
        record = {
            "run_id": "dead-tmux-running",
            "status": "running",
            "pid": "tmux:alv_definitely_missing_session",
            "raw_result_path": "/tmp/alv-definitely-missing-raw.json",
        }

        self.assertEqual(inferred_registry_status(record), "pending")


if __name__ == "__main__":
    unittest.main()
