#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path("/home/zeio99/Alv")
DATA_ROOT = Path("/mnt/e/currentWORK/AAA_Project/P3/data")
RAW_ROOT = ROOT / "results" / "raw"
DEFAULT_OUTPUT = ROOT / "results" / "processed" / "result_completeness.json"
METHODS = ("BC", "BD", "SAA-BC", "SAA-BD")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", default=str(RAW_ROOT))
    parser.add_argument("--data-root", default=str(DATA_ROOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()

    report = check_completeness(Path(args.raw_root), Path(args.data_root))
    if not args.no_write:
        write_completeness_report(report, Path(args.output))
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["complete"]:
        return 0
    if args.allow_empty and report["total_raw_results"] == 0:
        return 0
    return 2


def check_completeness(raw_root: Path, data_root: Path) -> dict[str, object]:
    expected_instances = {path.stem for path in (data_root / "processed").glob("omega*/*/*.json")}
    by_method: dict[str, dict[str, object]] = {}
    total_raw = 0
    complete = True

    for method in METHODS:
        seen: set[str] = set()
        failed: list[str] = []
        malformed: list[str] = []
        for path in sorted((raw_root / method).glob("*.json")):
            total_raw += 1
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                malformed.append(str(path))
                continue
            if payload.get("paper_equivalent_run") is not True:
                continue
            instance_stem = Path(str(payload.get("instance_path", ""))).stem
            if instance_stem:
                seen.add(instance_stem)
            if payload.get("status") == "failed":
                failed.append(str(path))

        missing = sorted(expected_instances - seen)
        extra = sorted(seen - expected_instances)
        method_complete = not missing and not failed and not malformed and not extra
        complete = complete and method_complete
        by_method[method] = {
            "expected_instances": len(expected_instances),
            "seen_instances": len(seen),
            "missing_count": len(missing),
            "missing_examples": missing[:10],
            "failed_count": len(failed),
            "failed_examples": failed[:10],
            "malformed_count": len(malformed),
            "malformed_examples": malformed[:10],
            "extra_count": len(extra),
            "extra_examples": extra[:10],
            "complete": method_complete,
        }

    return {
        "complete": complete,
        "expected_instances": len(expected_instances),
        "expected_methods": list(METHODS),
        "expected_total_method_instance_results": len(expected_instances) * len(METHODS),
        "total_raw_results": total_raw,
        "methods": by_method,
    }


def write_completeness_report(report: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
