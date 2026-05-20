#!/usr/bin/env python
"""DeploymentAgent environment and Gurobi license check."""

from __future__ import annotations

import json
import math
import os
import platform
import sys
import time
from pathlib import Path

import gurobipy as gp
from gurobipy import GRB


ROOT = Path("/home/zeio99/Alv")
METADATA_DIR = ROOT / "results" / "metadata"


def main() -> int:
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    log_path = METADATA_DIR / "gurobi_tiny_mip.log"
    log_path.unlink(missing_ok=True)

    result = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "conda_env": os.environ.get("CONDA_PREFIX"),
        "grb_license_file": os.environ.get("GRB_LICENSE_FILE"),
        "solver": "Gurobi",
        "paper_solver": "CPLEX 22.1",
        "gurobi_version": gp.gurobi.version(),
        "required_parameters": {"Threads": 1, "MIPGap": 1e-5, "LazyConstraints": 1},
        "tiny_mip": {"status": None, "objective": None, "x": None, "y": None},
        "license": {"available": False, "log_excerpt": "", "type": None, "expiration": None},
        "all_params_recorded": False,
        "gurobi_parameters": {},
    }

    try:
        model = gp.Model("deployment_tiny_mip")
        model.Params.Threads = 1
        model.Params.MIPGap = 1e-5
        model.Params.LazyConstraints = 1
        model.Params.LogFile = str(log_path)
        model.Params.LogToConsole = 0
        x_var = model.addVar(vtype=GRB.BINARY, name="x")
        y_var = model.addVar(vtype=GRB.BINARY, name="y")
        model.addConstr(x_var + y_var >= 1, name="cover")
        model.setObjective(x_var + 2 * y_var, GRB.MINIMIZE)
        model.optimize()

        result["tiny_mip"] = {
            "status": int(model.Status),
            "status_name": {GRB.OPTIMAL: "OPTIMAL"}.get(model.Status, str(model.Status)),
            "objective": float(model.ObjVal) if model.SolCount else None,
            "x": float(x_var.X) if model.SolCount else None,
            "y": float(y_var.X) if model.SolCount else None,
        }
        result["license"]["available"] = model.Status == GRB.OPTIMAL
        for param_name in ["Threads", "MIPGap", "LazyConstraints", "TimeLimit", "Seed"]:
            try:
                value = model.getParamInfo(param_name)[2]
                if isinstance(value, float) and not math.isfinite(value):
                    value = str(value)
                result["gurobi_parameters"][param_name] = value
            except gp.GurobiError as exc:
                result["gurobi_parameters"][param_name] = f"unavailable: {exc}"
    except Exception as exc:  # noqa: BLE001 - metadata must capture deployment failures.
        result["tiny_mip"]["error"] = repr(exc)
    finally:
        if log_path.exists():
            text = log_path.read_text(errors="replace")
            result["license"]["log_excerpt"] = "\n".join(text.splitlines()[:25])
            for line in text.splitlines():
                lower = line.lower()
                if "license" in lower:
                    result["license"]["type"] = line.strip()
                if "expires" in lower:
                    result["license"]["expiration"] = line.strip()

    result["all_params_recorded"] = bool(result["gurobi_parameters"])
    (METADATA_DIR / "environment.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )

    summary = {
        "gurobi_version": result["gurobi_version"],
        "grb_license_file": result["grb_license_file"],
        "tiny_mip": result["tiny_mip"],
        "license_available": result["license"]["available"],
        "license_type": result["license"]["type"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if result["tiny_mip"].get("status_name") == "OPTIMAL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
