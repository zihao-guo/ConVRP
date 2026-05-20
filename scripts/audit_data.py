#!/usr/bin/env python
from __future__ import annotations

import csv
import json
from pathlib import Path

from alv.data import load_all_instances, summary_rows, validate_dataset


DATA_ROOT = Path("/mnt/e/currentWORK/AAA_Project/P3/data")
ROOT = Path("/home/zeio99/Alv")


def main() -> int:
    instances = load_all_instances(DATA_ROOT)
    validation = validate_dataset(instances, DATA_ROOT)

    processed_dir = ROOT / "results" / "processed"
    tables_dir = ROOT / "results" / "tables"
    processed_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    (processed_dir / "data_validation.json").write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rows = summary_rows(instances)
    table_path = tables_dir / "data_summary.csv"
    with table_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "set",
                "omega",
                "alpha",
                "records",
                "base_instances",
                "min_customers",
                "max_customers",
                "min_vehicles",
                "max_vehicles",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({"valid": validation["valid"], "total_instances": validation["total_instances"]}))
    return 0 if validation["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

