from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import gurobipy as gp
from gurobipy import GRB

from alv.data import Instance


@dataclass(frozen=True)
class BuiltModel:
    instance: Instance
    model: gp.Model
    y: dict[tuple[int, int], gp.Var]
    s: dict[int, gp.Var]
    lam: dict[int, gp.Var]
    z: dict[tuple[int, int, int], gp.Var]
    x: dict[tuple[int, int, int, int], gp.Var]
    edges: tuple[tuple[int, int], ...]
    scenario_customers: dict[int, tuple[int, ...]]
    scenario_edges: dict[int, tuple[tuple[int, int], ...]]
    scenario_ids: tuple[int, ...]


def build_extensive_form(
    instance: Instance,
    *,
    name: str | None = None,
    time_limit: float | None = None,
    lazy_constraints: bool = False,
    output: bool = True,
) -> BuiltModel:
    model = gp.Model(name or f"convrp_{instance.name}")
    model.Params.OutputFlag = int(output)
    model.Params.Threads = 1
    model.Params.MIPGap = 1e-5
    if time_limit is not None:
        model.Params.TimeLimit = time_limit
    if lazy_constraints:
        model.Params.LazyConstraints = 1

    customers = instance.customers
    vehicles = instance.vehicles
    scenarios = instance.scenarios
    scenario_ids = tuple(scenario.id for scenario in scenarios)
    scenario_by_id = {scenario.id: scenario for scenario in scenarios}
    edges = tuple(sorted(instance.distances))
    scenario_customers = {
        scenario.id: tuple(sorted(scenario.demands))
        for scenario in scenarios
    }
    scenario_edges = {
        scenario.id: tuple(
            edge for edge in edges if edge[0] in (instance.depot, *scenario_customers[scenario.id])
            and edge[1] in (instance.depot, *scenario_customers[scenario.id])
        )
        for scenario in scenarios
    }

    y = {
        (i, k): model.addVar(vtype=GRB.BINARY, name=f"y[{i},{k}]")
        for i in customers
        for k in vehicles
    }
    s = {k: model.addVar(vtype=GRB.BINARY, name=f"s[{k}]") for k in vehicles}
    lam = {i: model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"lambda[{i}]") for i in customers}
    z = {
        (i, k, w): model.addVar(vtype=GRB.BINARY, name=f"z[{i},{k},{w}]")
        for w in scenario_ids
        for i in scenario_customers[w]
        for k in vehicles
    }
    x: dict[tuple[int, int, int, int], gp.Var] = {}
    for w in scenario_ids:
        for i, j in scenario_edges[w]:
            for k in vehicles:
                if i == instance.depot:
                    x[i, j, k, w] = model.addVar(
                        lb=0.0,
                        ub=2.0,
                        vtype=GRB.INTEGER,
                        name=f"x[{i},{j},{k},{w}]",
                    )
                else:
                    x[i, j, k, w] = model.addVar(vtype=GRB.BINARY, name=f"x[{i},{j},{k},{w}]")

    model.update()

    for i in customers:
        model.addConstr(gp.quicksum(y[i, k] for k in vehicles) <= instance.D + lam[i], name=f"consistency[{i}]")
        model.addConstr(gp.quicksum(y[i, k] for k in vehicles) >= 1, name=f"valid_assign[{i}]")

    for scenario in scenarios:
        w = scenario.id
        active_customers = scenario_customers[w]
        active_edges = scenario_edges[w]
        for i in active_customers:
            model.addConstr(gp.quicksum(z[i, k, w] for k in vehicles) <= 1, name=f"visit_once[{i},{w}]")
            for k in vehicles:
                model.addConstr(z[i, k, w] <= y[i, k], name=f"link[{i},{k},{w}]")

        for k in vehicles:
            for i in active_customers:
                model.addConstr(
                    _incident_expr(x, active_edges, i, k, w) == 2 * z[i, k, w],
                    name=f"degree[{i},{k},{w}]",
                )
            model.addConstr(
                gp.quicksum(x[0, j, k, w] for j in active_customers if (0, j, k, w) in x) <= 2,
                name=f"depot_degree[{k},{w}]",
            )
            model.addConstr(
                gp.quicksum(scenario.demands[i] * z[i, k, w] for i in active_customers) <= instance.capacity,
                name=f"capacity[{k},{w}]",
            )

    for k in vehicles:
        model.addConstr(gp.quicksum(y[i, k] for i in customers) <= len(customers) * s[k], name=f"activation[{k}]")

    for pos, k in enumerate(vehicles):
        if pos == 0:
            continue
        prev = vehicles[pos - 1]
        model.addConstr(s[k] <= s[prev], name=f"sym_s[{k}]")

    if scenario_ids:
        omega0 = scenario_ids[0]
        for pos, k in enumerate(vehicles):
            if pos == 0:
                continue
            prev = vehicles[pos - 1]
            active_customers = scenario_customers[omega0]
            model.addConstr(
                gp.quicksum(x[0, j, k, omega0] for j in active_customers if (0, j, k, omega0) in x)
                <= gp.quicksum(x[0, j, prev, omega0] for j in active_customers if (0, j, prev, omega0) in x),
                name=f"sym_depot[{k}]",
            )

    consistency_penalty = gp.quicksum(instance.penalties_consistency[i] * lam[i] for i in customers)
    expected_travel = gp.LinExpr()
    expected_skip = gp.LinExpr()
    for w in scenario_ids:
        scenario = scenario_by_id[w]
        rho = scenario.probability
        expected_travel += rho * gp.quicksum(
            instance.distances[i, j] * x[i, j, k, w]
            for i, j in scenario_edges[w]
            for k in vehicles
        )
        expected_skip += rho * gp.quicksum(
            instance.penalties_skip[i] * (1 - gp.quicksum(z[i, k, w] for k in vehicles))
            for i in scenario.demands
        )

    model.setObjective(consistency_penalty + expected_travel + expected_skip, GRB.MINIMIZE)
    built = BuiltModel(
        instance=instance,
        model=model,
        y=y,
        s=s,
        lam=lam,
        z=z,
        x=x,
        edges=edges,
        scenario_customers=scenario_customers,
        scenario_edges=scenario_edges,
        scenario_ids=scenario_ids,
    )
    model._alv_built = built  # type: ignore[attr-defined]
    return built


def _incident_expr(
    x: dict[tuple[int, int, int, int], gp.Var],
    edges: tuple[tuple[int, int], ...],
    node: int,
    vehicle: int,
    scenario: int,
) -> gp.LinExpr:
    return gp.quicksum(
        x[i, j, vehicle, scenario]
        for i, j in edges
        if i == node or j == node
    )


def objective_accounting(built: BuiltModel) -> dict[str, float]:
    instance = built.instance
    if built.model.SolCount == 0:
        raise ValueError("objective accounting requires an incumbent solution")

    travel = 0.0
    skipping = 0.0
    for scenario in instance.scenarios:
        w = scenario.id
        rho = scenario.probability
        for i, j in built.scenario_edges[w]:
            for k in instance.vehicles:
                travel += rho * instance.distances[i, j] * built.x[i, j, k, w].X
        for i in scenario.demands:
            served = sum(built.z[i, k, w].X for k in instance.vehicles)
            skipping += rho * instance.penalties_skip[i] * (1.0 - served)

    consistency = sum(instance.penalties_consistency[i] * built.lam[i].X for i in instance.customers)
    total = travel + consistency + skipping
    return {
        "total_cost": float(total),
        "travel_cost": float(travel),
        "consistency_penalty": float(consistency),
        "skipping_cost": float(skipping),
    }


def solution_first_stage_y(built: BuiltModel, tolerance: float = 0.5) -> dict[tuple[int, int], int]:
    if built.model.SolCount == 0:
        raise ValueError("first-stage extraction requires an incumbent solution")
    return {key: int(var.X > tolerance) for key, var in built.y.items()}


def model_metadata(built: BuiltModel) -> dict[str, Any]:
    return {
        "variables": {
            "y": len(built.y),
            "s": len(built.s),
            "lambda": len(built.lam),
            "z": len(built.z),
            "x": len(built.x),
        },
        "constraints": built.model.NumConstrs,
        "scenario_count": len(built.scenario_ids),
        "vehicle_count": len(built.instance.vehicles),
        "customer_count": len(built.instance.customers),
    }
