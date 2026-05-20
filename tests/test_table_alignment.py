from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_alignment_tables import generate_alignment_tables


class TableAlignmentTests(unittest.TestCase):
    def test_generates_required_alignment_tables_from_paper_baselines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir()
            (root / "results" / "tables").mkdir(parents=True)
            baseline = json.loads(Path("/home/zeio99/Alv/configs/paper_baselines.json").read_text(encoding="utf-8"))
            (root / "configs" / "paper_baselines.json").write_text(json.dumps(baseline), encoding="utf-8")

            generated = generate_alignment_tables(root)

            self.assertIn(root / "results" / "tables" / "table_1_alignment.csv", generated)
            self.assertIn(root / "results" / "tables" / "PAPER_TABLES.md", generated)
            with (root / "results" / "tables" / "table_1_alignment.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            markdown = (root / "results" / "tables" / "PAPER_TABLES.md").read_text(encoding="utf-8")

        self.assertTrue(rows)
        self.assertIn("Table 1", markdown)
        self.assertIn("PDF paper baseline", markdown)
        self.assertEqual(
            {
                "table_name",
                "row_key",
                "method",
                "metric",
                "paper_value",
                "our_value",
                "diff_abs",
                "diff_pct",
                "status",
                "notes",
            },
            set(rows[0]),
        )
        self.assertIn("not_run", {row["status"] for row in rows})

    def test_partial_raw_results_do_not_populate_full_paper_table_aggregates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configs").mkdir()
            (root / "results" / "tables").mkdir(parents=True)
            (root / "results" / "raw" / "BC").mkdir(parents=True)
            baseline = json.loads(Path("/home/zeio99/Alv/configs/paper_baselines.json").read_text(encoding="utf-8"))
            (root / "configs" / "paper_baselines.json").write_text(json.dumps(baseline), encoding="utf-8")
            (root / "results" / "raw" / "BC" / "one_bc.json").write_text(
                json.dumps(
                    {
                        "paper_equivalent_run": True,
                        "status": 2,
                        "method": "BC",
                        "instance_path": "/mnt/e/currentWORK/AAA_Project/P3/data/processed/omega100/A/convrp_10_test_1__omega100__alpha20.json",
                        "objective": 17.25,
                        "best_bound": 17.25,
                        "runtime_seconds": 0.4,
                        "time_to_best_seconds": 0.2,
                    }
                ),
                encoding="utf-8",
            )

            generate_alignment_tables(root)

            with (root / "results" / "tables" / "table_1_alignment.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        total_count = next(
            row
            for row in rows
            if row["row_key"] == "probability=total"
            and row["method"] == "ALL"
            and row["metric"] == "number_of_instances"
        )
        self.assertEqual(total_count["our_value"], "")
        self.assertEqual(total_count["status"], "not_run")


if __name__ == "__main__":
    unittest.main()
