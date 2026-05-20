#!/usr/bin/env python
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


REQUIRED_ALIGNMENT_TABLES = (
    "table_1_alignment.csv",
    "table_2_alignment.csv",
    "table_3_alignment.csv",
    "appendix_b11_alignment.csv",
    "appendix_b12_alignment.csv",
)
ALLOWED_ALIGNMENT_STATUSES = {"exact_match", "close", "solver_difference"}


def assess_final_report_readiness(root: Path) -> dict[str, Any]:
    state = _read_json(root / "state" / "workflow_state.json", default={})
    completeness = _read_json(root / "results" / "processed" / "result_completeness.json", default=None)
    blocking: list[str] = []
    warnings: list[str] = []

    if not completeness:
        blocking.append("full_experiment_results_incomplete")
    elif not completeness.get("complete"):
        blocking.append("full_experiment_results_incomplete")
    elif completeness.get("expected_total_method_instance_results") != 552:
        blocking.append("unexpected_method_instance_result_count")

    method_status = state.get("method_status", {})
    if method_status.get("BD") != "paper_equivalent":
        blocking.append("bd_not_exact_branch_and_check")
    if method_status.get("BC") != "paper_equivalent":
        blocking.append("bc_sec_deviation_not_solver_only")
    if method_status.get("SAA") != "paper_equivalent":
        blocking.append("saa_statistics_protocol_incomplete")

    tables_dir = root / "results" / "tables"
    missing_tables = [name for name in REQUIRED_ALIGNMENT_TABLES if not (tables_dir / name).exists()]
    if missing_tables:
        blocking.append("alignment_tables_missing")
        warnings.append(f"missing alignment tables: {missing_tables}")
    else:
        bad_statuses = _alignment_bad_statuses(tables_dir)
        if bad_statuses:
            blocking.append("alignment_contains_non_solver_deviation")
            warnings.extend(bad_statuses[:20])

    return {
        "can_claim_full_reproduction": not blocking,
        "blocking_reasons": blocking,
        "warnings": warnings,
        "required_conditions": {
            "all_138_instances_run": bool(completeness and completeness.get("complete")),
            "all_target_methods_run": bool(
                completeness
                and completeness.get("complete")
                and completeness.get("expected_total_method_instance_results") == 552
            ),
            "all_required_tables_generated": not missing_tables,
            "only_solver_or_minor_numeric_differences": "alignment_contains_non_solver_deviation" not in blocking
            and method_status.get("BC") == "paper_equivalent"
            and method_status.get("BD") == "paper_equivalent"
            and method_status.get("SAA") == "paper_equivalent",
        },
    }


def _read_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _alignment_bad_statuses(tables_dir: Path) -> list[str]:
    bad: list[str] = []
    for name in REQUIRED_ALIGNMENT_TABLES:
        path = tables_dir / name
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if "status" not in (reader.fieldnames or []):
                bad.append(f"{name}: missing status column")
                continue
            for index, row in enumerate(reader, start=2):
                status = row.get("status", "")
                if status not in ALLOWED_ALIGNMENT_STATUSES:
                    bad.append(f"{name}:{index}: status={status}")
    return bad


def main() -> int:
    root = Path("/home/zeio99/Alv")
    readiness = assess_final_report_readiness(root)
    print(json.dumps(readiness, indent=2, sort_keys=True))
    return 0 if readiness["can_claim_full_reproduction"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
