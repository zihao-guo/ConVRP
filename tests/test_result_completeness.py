from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_result_completeness import check_completeness, write_completeness_report


class ResultCompletenessTests(unittest.TestCase):
    def test_empty_results_are_incomplete_against_138_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = check_completeness(
                Path(tmp),
                Path("/mnt/e/currentWORK/AAA_Project/P3/data"),
            )

        self.assertFalse(report["complete"])
        self.assertEqual(report["expected_instances"], 138)
        self.assertEqual(report["expected_total_method_instance_results"], 552)
        self.assertEqual(report["methods"]["BC"]["missing_count"], 138)

    def test_complete_tiny_fixture_requires_every_method_and_instance(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as data_tmp:
            data_root = Path(data_tmp)
            raw_root = Path(raw_tmp)
            for name in ["a__omega100__alpha20", "b__omega100__alpha20"]:
                path = data_root / "processed" / "omega100" / "A" / f"{name}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            for method in ["BC", "BD", "SAA-BC", "SAA-BD"]:
                for name in ["a__omega100__alpha20", "b__omega100__alpha20"]:
                    path = raw_root / method / f"{method}_{name}.json"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        json.dumps({"instance_path": f"/fake/{name}.json", "status": 2, "paper_equivalent_run": True}),
                        encoding="utf-8",
                    )

            report = check_completeness(raw_root, data_root)

        self.assertTrue(report["complete"])
        self.assertEqual(report["expected_total_method_instance_results"], 8)

    def test_results_without_paper_equivalent_marker_do_not_count_for_final_completeness(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as data_tmp:
            data_root = Path(data_tmp)
            raw_root = Path(raw_tmp)
            path = data_root / "processed" / "omega100" / "A" / "a__omega100__alpha20.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
            for method in ["BC", "BD", "SAA-BC", "SAA-BD"]:
                raw_path = raw_root / method / f"{method}_a.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(json.dumps({"instance_path": str(path), "status": 2}), encoding="utf-8")

            report = check_completeness(raw_root, data_root)

        self.assertFalse(report["complete"])
        self.assertEqual(report["methods"]["BC"]["missing_count"], 1)

    def test_write_completeness_report_refreshes_guard_input_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "results" / "processed" / "result_completeness.json"
            report = {"complete": False, "total_raw_results": 0}

            write_completeness_report(report, output_path)

            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), report)


if __name__ == "__main__":
    unittest.main()
