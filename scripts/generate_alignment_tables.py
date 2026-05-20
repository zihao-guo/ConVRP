#!/usr/bin/env python
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


ALIGNMENT_HEADER = [
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
]
EXPECTED_METHODS = ("BC", "BD", "SAA-BC", "SAA-BD")
EXPECTED_INSTANCE_COUNT = 138


def generate_alignment_tables(root: Path) -> list[Path]:
    baselines = json.loads((root / "configs" / "paper_baselines.json").read_text(encoding="utf-8"))
    raw_results = _load_raw_results(root)
    if not _has_complete_full_experiment(raw_results):
        raw_results = {}
    tables_dir = root / "results" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    outputs = [
        _write_alignment(tables_dir / "table_1_alignment.csv", _table_1_rows(baselines, raw_results)),
        _write_alignment(tables_dir / "table_2_alignment.csv", _table_2_rows(baselines, raw_results)),
        _write_alignment(tables_dir / "table_3_alignment.csv", _table_3_rows(baselines, raw_results)),
        _write_alignment(tables_dir / "appendix_b11_alignment.csv", _appendix_rows(baselines, raw_results, "appendix_b11_saa_bc", "SAA-BC")),
        _write_alignment(tables_dir / "appendix_b12_alignment.csv", _appendix_rows(baselines, raw_results, "appendix_b12_saa_bd", "SAA-BD")),
    ]
    outputs.extend(_write_paper_reference_tables(tables_dir, baselines))
    outputs.append(_write_markdown_summary(tables_dir / "PAPER_TABLES.md", baselines))
    return outputs


def _alignment_row(
    table_name: str,
    row_key: str,
    method: str,
    metric: str,
    paper_value: Any,
    *,
    our_value: Any = None,
    notes: str = "full experiment raw result not available yet",
) -> dict[str, Any]:
    diff_abs, diff_pct, status = _alignment_status(paper_value, our_value)
    return {
        "table_name": table_name,
        "row_key": row_key,
        "method": method,
        "metric": metric,
        "paper_value": paper_value,
        "our_value": "" if our_value is None else our_value,
        "diff_abs": "" if diff_abs is None else diff_abs,
        "diff_pct": "" if diff_pct is None else diff_pct,
        "status": status,
        "notes": notes if status == "not_run" else "computed from paper-equivalent Gurobi raw results",
    }


def _table_1_rows(baselines: dict[str, Any], raw_results: dict[str, dict[str, dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    table_name = "table_1_method_comparison"
    table = baselines[table_name]
    raw_results = raw_results or {}
    aggregates = _method_aggregates(raw_results)
    rows = [
        _alignment_row(
            table_name,
            f"probability={probability}",
            "ALL",
            "number_of_instances",
            value,
            our_value=_count_instances(raw_results, alpha=probability),
        )
        for probability, value in table["number_of_instances"].items()
    ]
    for metric, by_method in table["statistics"].items():
        if metric == "number_of_optimal":
            by_method = {method: values for method, values in by_method.items() if method != "note"}
        for method, values in by_method.items():
            for probability, value in values.items():
                rows.append(
                    _alignment_row(
                        table_name,
                        f"probability={probability}",
                        method,
                        metric,
                        value,
                        our_value=aggregates.get((method, str(probability), metric)),
                    )
                )
    return rows


def _table_2_rows(baselines: dict[str, Any], raw_results: dict[str, dict[str, dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    table_name = "table_2_gap_by_omega_and_set"
    table = baselines[table_name]
    raw_results = raw_results or {}
    aggregates = _method_aggregates(raw_results)
    rows: list[dict[str, Any]] = []
    for row in table["rows"]:
        row_key = f"omega={row['scenario_set_size']};set={row['set']}"
        group_key = f"omega={row['scenario_set_size']};set={row['set']}"
        rows.append(
            _alignment_row(
                table_name,
                row_key,
                "ALL",
                "number_of_instances",
                row["number_of_instances"],
                our_value=_count_instances(raw_results, omega=row["scenario_set_size"], set_name=row["set"]),
            )
        )
        for method, value in row["gap_to_best_percent"].items():
            rows.append(_alignment_row(table_name, row_key, method, "gap_to_best_percent", value, our_value=aggregates.get((method, group_key, "gap_to_best_percent"))))
    total = table["total"]
    rows.append(_alignment_row(table_name, "total", "ALL", "number_of_instances", total["number_of_instances"], our_value=_count_instances(raw_results)))
    for method, value in total["gap_to_best_percent"].items():
        rows.append(_alignment_row(table_name, "total", method, "gap_to_best_percent", value, our_value=aggregates.get((method, "total", "gap_to_best_percent"))))
    return rows


def _table_3_rows(baselines: dict[str, Any], raw_results: dict[str, dict[str, dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    table_name = "table_3_saa_bc_solution_attributes"
    table = baselines[table_name]
    raw_results = raw_results or {}
    aggregates = _saa_bc_attribute_aggregates(raw_results)
    metrics = [
        "number_of_instances",
        "total_cost",
        "travel_cost_percent",
        "consistency_penalty_percent",
        "skipping_cost_percent",
        "number_of_clusters",
        "violation_level",
        "skipped_customers_percent",
    ]
    rows: list[dict[str, Any]] = []
    for row in table["rows"]:
        row_key = f"omega={row['scenario_set_size']};alpha={row['probability_of_occurrence_percent']}"
        for metric in metrics:
            rows.append(_alignment_row(table_name, row_key, "SAA-BC", metric, row[metric], our_value=aggregates.get((row_key, metric))))
    for metric, value in table["total"].items():
        rows.append(_alignment_row(table_name, "total", "SAA-BC", metric, value, our_value=aggregates.get(("total", metric))))
    return rows


def _appendix_rows(
    baselines: dict[str, Any],
    raw_results: dict[str, dict[str, dict[str, Any]]] | None,
    table_name: str,
    method: str,
) -> list[dict[str, Any]]:
    metrics = [
        "number_of_instances",
        "total_cost",
        "total_time_seconds",
        "time_to_best_seconds",
        "opt_gap_percent",
        "sample_gap_percent",
        "selected_for_main_experiments",
    ]
    raw_results = raw_results or {}
    aggregates = _method_aggregates(raw_results)
    rows = []
    for row in baselines[table_name]["rows"]:
        if not row["selected_for_main_experiments"]:
            continue
        row_key = f"sample_time={row['sample_time_minutes']};M={row['M']};N={row['sample_size']}"
        for metric in metrics:
            rows.append(_alignment_row(table_name, row_key, method, metric, row[metric], our_value=aggregates.get((method, "total", metric))))
    return rows


def _write_alignment(path: Path, rows: list[dict[str, Any]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ALIGNMENT_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _load_raw_results(root: Path) -> dict[str, dict[str, dict[str, Any]]]:
    results: dict[str, dict[str, dict[str, Any]]] = {}
    raw_root = root / "results" / "raw"
    if not raw_root.exists():
        return results
    for path in sorted(raw_root.glob("*/*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("paper_equivalent_run") is not True:
            continue
        if payload.get("status") == "failed" or payload.get("objective") is None:
            continue
        instance_id = Path(str(payload.get("instance_path", ""))).stem
        method = str(payload.get("method", path.parent.name))
        meta = _instance_meta(payload)
        results.setdefault(instance_id, {})[method] = {**payload, "_meta": meta}
    return results


def _has_complete_full_experiment(raw_results: dict[str, dict[str, dict[str, Any]]]) -> bool:
    if len(raw_results) != EXPECTED_INSTANCE_COUNT:
        return False
    expected = set(EXPECTED_METHODS)
    return all(set(methods) == expected for methods in raw_results.values())


def _instance_meta(payload: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(payload.get("instance_path", "")))
    stem = path.stem
    omega_match = re.search(r"__omega(\d+)", stem)
    alpha_match = re.search(r"__alpha(\d+)", stem)
    return {
        "instance_id": stem,
        "set": path.parent.name,
        "omega": int(omega_match.group(1)) if omega_match else None,
        "alpha": alpha_match.group(1) if alpha_match else None,
    }


def _count_instances(
    raw_results: dict[str, dict[str, dict[str, Any]]],
    *,
    alpha: str | int | None = None,
    omega: int | None = None,
    set_name: str | None = None,
) -> int | None:
    if not raw_results:
        return None
    count = 0
    for methods in raw_results.values():
        sample = next(iter(methods.values()), None)
        if sample is None:
            continue
        meta = sample["_meta"]
        if alpha is not None and str(alpha) != "total" and str(meta["alpha"]) != str(alpha):
            continue
        if omega is not None and meta["omega"] != omega:
            continue
        if set_name is not None and meta["set"] != set_name:
            continue
        count += 1
    return count


def _method_aggregates(raw_results: dict[str, dict[str, dict[str, Any]]]) -> dict[tuple[str, str, str], float | int]:
    if not raw_results:
        return {}
    best_objectives = {
        instance_id: min(float(payload["objective"]) for payload in methods.values() if payload.get("objective") is not None)
        for instance_id, methods in raw_results.items()
        if any(payload.get("objective") is not None for payload in methods.values())
    }
    aggregates: dict[tuple[str, str, str], float | int] = {}
    for method in ("BC", "BD", "SAA-BC", "SAA-BD"):
        for group_key, predicate in _groups():
            payloads = [
                methods[method]
                for instance_id, methods in raw_results.items()
                if method in methods and predicate(methods[method]["_meta"]) and instance_id in best_objectives
            ]
            if not payloads:
                continue
            aggregates[method, group_key, "number_of_optimal"] = sum(
                1
                for payload in payloads
                if _is_optimal(payload, best_objectives[str(payload["_meta"]["instance_id"])])
            )
            aggregates[method, group_key, "total_cost"] = _round(_mean([float(payload["objective"]) for payload in payloads]))
            aggregates[method, group_key, "gap_to_best_percent"] = _round(
                _mean(
                    [
                        100.0 * (float(payload["objective"]) - best_objectives[str(payload["_meta"]["instance_id"])])
                        / abs(best_objectives[str(payload["_meta"]["instance_id"])])
                        for payload in payloads
                        if abs(best_objectives[str(payload["_meta"]["instance_id"])]) > 1e-12
                    ]
                )
            )
            aggregates[method, group_key, "total_time_seconds"] = _round(_mean([float(payload.get("elapsed_seconds", 0.0)) for payload in payloads]))
            aggregates[method, group_key, "time_to_best_seconds"] = _round(
                _mean(
                    [
                        float(payload.get("time_to_best_seconds") or payload.get("elapsed_seconds", 0.0))
                        for payload in payloads
                    ]
                )
            )
            stats = [payload.get("saa_statistics") for payload in payloads if payload.get("saa_statistics")]
            if stats:
                aggregates[method, group_key, "opt_gap_percent"] = _round(_mean([float(stat["opt_gap_percent"]) for stat in stats if stat.get("opt_gap_percent") is not None]))
                aggregates[method, group_key, "sample_gap_percent"] = _round(_mean([float(stat["sample_gap_percent"]) for stat in stats if stat.get("sample_gap_percent") is not None]))
            selected = payloads[0].get("method") in {"SAA-BC", "SAA-BD"}
            aggregates[method, group_key, "selected_for_main_experiments"] = selected
    return aggregates


def _saa_bc_attribute_aggregates(raw_results: dict[str, dict[str, dict[str, Any]]]) -> dict[tuple[str, str], float | int]:
    aggregates: dict[tuple[str, str], float | int] = {}
    if not raw_results:
        return aggregates
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for omega in (100, 500):
        for alpha in ("20", "50", "80"):
            row_key = f"omega={omega};alpha={alpha}"
            groups.append(
                (
                    row_key,
                    [
                        methods["SAA-BC"]
                        for methods in raw_results.values()
                        if "SAA-BC" in methods
                        and methods["SAA-BC"]["_meta"]["omega"] == omega
                        and methods["SAA-BC"]["_meta"]["alpha"] == alpha
                    ],
                )
            )
    groups.append(("total", [methods["SAA-BC"] for methods in raw_results.values() if "SAA-BC" in methods]))
    for row_key, payloads in groups:
        if not payloads:
            continue
        aggregates[row_key, "number_of_instances"] = len(payloads)
        aggregates[row_key, "total_cost"] = _round(_mean([float(payload["objective"]) for payload in payloads]))
        evaluations = [payload.get("best_full_omega_evaluation") or {} for payload in payloads]
        attributes = [payload.get("solution_attributes") or {} for payload in payloads]
        aggregates[row_key, "travel_cost_percent"] = _component_percent(evaluations, "travel_cost")
        aggregates[row_key, "consistency_penalty_percent"] = _component_percent(evaluations, "consistency_penalty")
        aggregates[row_key, "skipping_cost_percent"] = _component_percent(evaluations, "skipping_cost")
        aggregates[row_key, "number_of_clusters"] = _round(_mean([float(attr["number_of_clusters"]) for attr in attributes if attr.get("number_of_clusters") is not None]))
        aggregates[row_key, "violation_level"] = _round(_mean([float(attr["violation_level"]) for attr in attributes if attr.get("violation_level") is not None]))
        aggregates[row_key, "skipped_customers_percent"] = _round(_mean([float(attr["skipped_customers_percent"]) for attr in attributes if attr.get("skipped_customers_percent") is not None]))
    return aggregates


def _groups():
    yield "20", lambda meta: str(meta["alpha"]) == "20"
    yield "50", lambda meta: str(meta["alpha"]) == "50"
    yield "80", lambda meta: str(meta["alpha"]) == "80"
    yield "total", lambda meta: True
    for omega in (100, 500):
        for set_name in ("A", "B", "D"):
            yield f"omega={omega};set={set_name}", lambda meta, omega=omega, set_name=set_name: meta["omega"] == omega and meta["set"] == set_name


def _is_optimal(payload: dict[str, Any], best_objective: float) -> bool:
    status = payload.get("status")
    if payload.get("method") in {"BC", "BD"}:
        return status == 2
    objective = float(payload["objective"])
    return abs(objective - best_objective) <= max(1e-5, 1e-5 * abs(best_objective))


def _component_percent(evaluations: list[dict[str, Any]], key: str) -> float | None:
    values = []
    for evaluation in evaluations:
        total = evaluation.get("total_cost")
        component = evaluation.get(key)
        if total is None or component is None or abs(float(total)) <= 1e-12:
            continue
        values.append(100.0 * float(component) / abs(float(total)))
    return _round(_mean(values))


def _alignment_status(paper_value: Any, our_value: Any) -> tuple[float | None, float | None, str]:
    if our_value is None:
        return None, None, "not_run"
    if isinstance(paper_value, bool):
        return (0.0 if bool(our_value) == paper_value else 1.0), None, "exact_match" if bool(our_value) == paper_value else "solver_difference"
    try:
        paper_float = float(paper_value)
        our_float = float(our_value)
    except (TypeError, ValueError):
        exact = str(paper_value) == str(our_value)
        return (0.0 if exact else None), None, "exact_match" if exact else "solver_difference"
    diff_abs = abs(our_float - paper_float)
    diff_pct = None if abs(paper_float) <= 1e-12 else 100.0 * diff_abs / abs(paper_float)
    if diff_abs <= 1e-6:
        status = "exact_match"
    elif diff_pct is not None and diff_pct <= 2.0:
        status = "close"
    else:
        status = "solver_difference"
    return _round(diff_abs), _round(diff_pct), status


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _write_paper_reference_tables(tables_dir: Path, baselines: dict[str, Any]) -> list[Path]:
    outputs = [
        _write_reference(tables_dir / "paper_table_1_method_comparison.csv", _table_1_rows(baselines)),
        _write_reference(tables_dir / "paper_table_2_gap_by_omega_and_set.csv", _table_2_rows(baselines)),
        _write_reference(tables_dir / "paper_table_3_saa_bc_solution_attributes.csv", _table_3_rows(baselines)),
        _write_reference(tables_dir / "paper_appendix_b11_saa_bc.csv", _appendix_rows(baselines, None, "appendix_b11_saa_bc", "SAA-BC")),
        _write_reference(tables_dir / "paper_appendix_b12_saa_bd.csv", _appendix_rows(baselines, None, "appendix_b12_saa_bd", "SAA-BD")),
    ]
    return outputs


def _write_reference(path: Path, alignment_rows: list[dict[str, Any]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["row_key", "method", "metric", "paper_value"])
        writer.writeheader()
        for row in alignment_rows:
            writer.writerow(
                {
                    "row_key": row["row_key"],
                    "method": row["method"],
                    "metric": row["metric"],
                    "paper_value": row["paper_value"],
                }
            )
    return path


def _write_markdown_summary(path: Path, baselines: dict[str, Any]) -> Path:
    lines = [
        "# PDF Paper Baseline Tables",
        "",
        "These are PDF paper baseline values for visual comparison. They are not reproduction results.",
        "",
        "## Table 1",
        "",
    ]
    lines.extend(_markdown_alignment_rows(_table_1_rows(baselines)))
    lines.extend(["", "## Table 2", ""])
    lines.extend(_markdown_alignment_rows(_table_2_rows(baselines)))
    lines.extend(["", "## Table 3", ""])
    lines.extend(_markdown_alignment_rows(_table_3_rows(baselines)))
    lines.extend(["", "## Appendix B.11", ""])
    lines.extend(_markdown_alignment_rows(_appendix_rows(baselines, None, "appendix_b11_saa_bc", "SAA-BC")))
    lines.extend(["", "## Appendix B.12", ""])
    lines.extend(_markdown_alignment_rows(_appendix_rows(baselines, None, "appendix_b12_saa_bd", "SAA-BD")))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _markdown_alignment_rows(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| row_key | method | metric | PDF paper baseline |",
        "| --- | --- | --- | ---: |",
    ]
    for row in rows:
        lines.append(f"| {row['row_key']} | {row['method']} | {row['metric']} | {row['paper_value']} |")
    return lines


def main() -> int:
    root = Path("/home/zeio99/Alv")
    outputs = generate_alignment_tables(root)
    print(json.dumps({"generated": [str(path) for path in outputs]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
