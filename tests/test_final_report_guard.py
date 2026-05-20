from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.final_report_guard import assess_final_report_readiness


class FinalReportGuardTests(unittest.TestCase):
    def test_current_workspace_cannot_claim_full_reproduction(self) -> None:
        readiness = assess_final_report_readiness(Path("/home/zeio99/Alv"))

        self.assertFalse(readiness["can_claim_full_reproduction"])
        self.assertIn("full_experiment_results_incomplete", readiness["blocking_reasons"])
        self.assertTrue(
            {
                "alignment_contains_non_solver_deviation",
                "alignment_tables_missing",
            }
            & set(readiness["blocking_reasons"])
        )
        self.assertNotIn("bd_not_exact_branch_and_check", readiness["blocking_reasons"])
        self.assertNotIn("bc_sec_deviation_not_solver_only", readiness["blocking_reasons"])
        self.assertNotIn("saa_statistics_protocol_incomplete", readiness["blocking_reasons"])
        self.assertFalse(readiness["required_conditions"]["all_target_methods_run"])

    def test_only_solver_difference_and_complete_tables_allow_full_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state").mkdir()
            (root / "results" / "processed").mkdir(parents=True)
            (root / "results" / "tables").mkdir(parents=True)
            (root / "state" / "workflow_state.json").write_text(
                json.dumps(
                    {
                        "state": "TABLES_DONE",
                        "method_status": {
                            "BC": "paper_equivalent",
                            "BD": "paper_equivalent",
                            "SAA": "paper_equivalent",
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "results" / "processed" / "result_completeness.json").write_text(
                json.dumps({"complete": True, "expected_total_method_instance_results": 552}),
                encoding="utf-8",
            )
            for name in [
                "table_1_alignment.csv",
                "table_2_alignment.csv",
                "table_3_alignment.csv",
                "appendix_b11_alignment.csv",
                "appendix_b12_alignment.csv",
            ]:
                (root / "results" / "tables" / name).write_text("status\nsolver_difference\n", encoding="utf-8")

            readiness = assess_final_report_readiness(root)

        self.assertTrue(readiness["can_claim_full_reproduction"])
        self.assertEqual(readiness["blocking_reasons"], [])

    def test_missing_saa_protocol_status_blocks_full_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state").mkdir()
            (root / "results" / "processed").mkdir(parents=True)
            (root / "results" / "tables").mkdir(parents=True)
            (root / "state" / "workflow_state.json").write_text(
                json.dumps(
                    {
                        "state": "TABLES_DONE",
                        "method_status": {"BC": "paper_equivalent", "BD": "paper_equivalent"},
                    }
                ),
                encoding="utf-8",
            )
            (root / "results" / "processed" / "result_completeness.json").write_text(
                json.dumps({"complete": True, "expected_total_method_instance_results": 552}),
                encoding="utf-8",
            )
            for name in [
                "table_1_alignment.csv",
                "table_2_alignment.csv",
                "table_3_alignment.csv",
                "appendix_b11_alignment.csv",
                "appendix_b12_alignment.csv",
            ]:
                (root / "results" / "tables" / name).write_text("status\nsolver_difference\n", encoding="utf-8")

            readiness = assess_final_report_readiness(root)

        self.assertFalse(readiness["can_claim_full_reproduction"])
        self.assertIn("saa_statistics_protocol_incomplete", readiness["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
