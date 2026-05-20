#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from alv.benders import solve_benders_like
from alv.branch_cut import solve_branch_and_cut
from alv.data import load_instance
from alv.model import objective_accounting, solution_first_stage_y
from alv.saa import SAA_BC_CONFIG, SAA_BD_CONFIG, run_saa


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--instance-json", required=True)
    parser.add_argument("--method", required=True, choices=["BC", "BD", "SAA-BC", "SAA-BD"])
    parser.add_argument("--raw-result-path", required=True)
    parser.add_argument("--time-limit", type=float, default=None)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    started = time.time()
    instance = load_instance(Path(args.instance_json))
    result: dict[str, object] = {
        "run_id": args.run_id,
        "instance_path": args.instance_json,
        "method": args.method,
        "start_time_unix": started,
        "solver": "Gurobi",
        "paper_solver": "CPLEX 22.1",
        "time_limit_seconds": args.time_limit,
        "threads": 1,
        "mip_gap": 1e-5,
        "paper_equivalent_run": _paper_equivalent_run_marker(),
    }

    try:
        if args.method == "BC":
            built = solve_branch_and_cut(instance, name=args.run_id, time_limit=args.time_limit, output=True)
            accounting = objective_accounting(built) if built.model.SolCount else None
            result.update(
                {
                    "status": int(built.model.Status),
                    "objective": float(built.model.ObjVal) if built.model.SolCount else None,
                    "best_bound": float(built.model.ObjBound) if built.model.SolCount else None,
                    "time_to_best_seconds": built.model._alv_best_incumbent_time if built.model.SolCount else None,
                    "objective_accounting": accounting,
                    "first_stage_y": {f"{i},{k}": v for (i, k), v in solution_first_stage_y(built).items()}
                    if built.model.SolCount
                    else {},
                }
            )
        elif args.method == "BD":
            bd = solve_benders_like(instance, name=args.run_id, time_limit=args.time_limit)
            result.update(
                {
                    "status": int(bd.status),
                    "method_status": bd.method,
                    "objective": bd.upper_bound,
                    "best_bound": bd.lower_bound,
                    "time_to_best_seconds": bd.best_time_seconds,
                    "iterations": len(bd.iterations),
                }
            )
        elif args.method == "SAA-BC":
            config = SAA_BC_CONFIG.__class__(**{**SAA_BC_CONFIG.__dict__, "seed": args.seed})
            saa = run_saa(instance, config)
            best_eval, best_y = _best_saa_details(saa)
            result.update(
                {
                    "status": 2 if saa.best_total_cost is not None else 3,
                    "objective": saa.best_total_cost,
                    "time_to_best_seconds": saa.best_time_seconds,
                    "best_replication": saa.best_replication,
                    "replications": config.replications,
                    "sample_size": config.sample_size,
                    "sample_time_limit_seconds": config.sample_time_limit_seconds,
                    "best_full_omega_evaluation": asdict(best_eval) if best_eval is not None else None,
                    "solution_attributes": _solution_attributes(instance, best_y, best_eval),
                    "saa_statistics": asdict(saa.statistics) if saa.statistics is not None else None,
                    "sample_memberships": [list(rep.sample_membership) for rep in saa.replications],
                    "sample_objectives": [rep.sample_objective for rep in saa.replications],
                    "sample_lower_bounds": [rep.sample_lower_bound for rep in saa.replications],
                }
            )
        elif args.method == "SAA-BD":
            config = SAA_BD_CONFIG.__class__(**{**SAA_BD_CONFIG.__dict__, "seed": args.seed})
            saa = run_saa(instance, config)
            best_eval, best_y = _best_saa_details(saa)
            result.update(
                {
                    "status": 2 if saa.best_total_cost is not None else 3,
                    "method_status": "BD",
                    "objective": saa.best_total_cost,
                    "time_to_best_seconds": saa.best_time_seconds,
                    "best_replication": saa.best_replication,
                    "replications": config.replications,
                    "sample_size": config.sample_size,
                    "sample_time_limit_seconds": config.sample_time_limit_seconds,
                    "best_full_omega_evaluation": asdict(best_eval) if best_eval is not None else None,
                    "solution_attributes": _solution_attributes(instance, best_y, best_eval),
                    "saa_statistics": asdict(saa.statistics) if saa.statistics is not None else None,
                    "sample_memberships": [list(rep.sample_membership) for rep in saa.replications],
                    "sample_objectives": [rep.sample_objective for rep in saa.replications],
                    "sample_lower_bounds": [rep.sample_lower_bound for rep in saa.replications],
                }
            )
    except Exception as exc:  # noqa: BLE001 - raw result must record failure.
        result.update({"status": "failed", "error": repr(exc)})
        exit_code = 1
    else:
        exit_code = 0

    result["end_time_unix"] = time.time()
    result["elapsed_seconds"] = result["end_time_unix"] - started
    raw_path = Path(args.raw_result_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return exit_code


def _paper_equivalent_run_marker() -> bool:
    state_path = Path("/home/zeio99/Alv/state/workflow_state.json")
    if not state_path.exists():
        return False
    state = json.loads(state_path.read_text(encoding="utf-8"))
    method_status = state.get("method_status", {})
    return (
        method_status.get("BC") == "paper_equivalent"
        and method_status.get("BD") == "paper_equivalent"
        and method_status.get("SAA") == "paper_equivalent"
    )


def _best_saa_details(saa):
    if saa.best_replication is None:
        return None, {}
    for replication in saa.replications:
        if replication.replication == saa.best_replication:
            return replication.full_omega_evaluation, replication.y_values
    return None, {}


def _solution_attributes(instance, y_values, full_eval) -> dict[str, float | int | None]:
    if not y_values:
        return {
            "number_of_clusters": None,
            "violation_level": None,
            "skipped_customers_percent": None,
        }
    nonempty_clusters = sum(
        1
        for vehicle in instance.vehicles
        if any(int(round(float(y_values.get((customer, vehicle), 0)))) for customer in instance.customers)
    )
    violation_count = sum(
        max(
            0,
            sum(int(round(float(y_values.get((customer, vehicle), 0)))) for vehicle in instance.vehicles)
            - instance.D,
        )
        for customer in instance.customers
    )
    return {
        "number_of_clusters": int(nonempty_clusters),
        "violation_level": 0.0
        if not instance.customers
        else float(100.0 * violation_count / len(instance.customers)),
        "skipped_customers_percent": None if full_eval is None else full_eval.skipped_customers_percent,
    }


if __name__ == "__main__":
    raise SystemExit(main())
