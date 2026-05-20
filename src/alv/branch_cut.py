from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import gurobipy as gp
from gurobipy import GRB

from alv.data import Instance
from alv.model import BuiltModel, build_extensive_form
from alv.subproblem import solve_fixed_y_scenario_subproblem


@dataclass(frozen=True)
class BCPrimalHeuristicSolution:
    total_cost: float
    scenario_costs: dict[int, float]
    variable_values: dict[Any, float]


def solve_branch_and_cut(
    instance: Instance,
    *,
    name: str | None = None,
    time_limit: float | None = None,
    output: bool = True,
) -> BuiltModel:
    built = build_extensive_form(
        instance,
        name=name,
        time_limit=time_limit,
        lazy_constraints=True,
        output=output,
    )
    built.model.Params.PreCrush = 1
    built.model._alv_time_limit = time_limit  # type: ignore[attr-defined]
    built.model._alv_enable_primal_heuristic = True  # type: ignore[attr-defined]
    built.model._alv_primal_heuristic_attempts = 0  # type: ignore[attr-defined]
    built.model._alv_primal_heuristic_solutions = 0  # type: ignore[attr-defined]
    built.model._alv_best_incumbent_obj = float("inf")  # type: ignore[attr-defined]
    built.model._alv_best_incumbent_time = None  # type: ignore[attr-defined]
    built.model.optimize(branch_and_cut_callback)
    return built


def branch_and_cut_callback(model: gp.Model, where: int) -> None:
    built: BuiltModel = model._alv_built  # type: ignore[attr-defined]
    if where == GRB.Callback.MIPNODE:
        if model.cbGet(GRB.Callback.MIPNODE_STATUS) != GRB.OPTIMAL:
            return
        if int(model.cbGet(GRB.Callback.MIPNODE_NODCNT)) != 0:
            return
        x_solution = model.cbGetNodeRel(built.x)
        z_solution = model.cbGetNodeRel(built.z)
        for vehicle in built.instance.vehicles:
            for scenario in built.scenario_ids:
                for component in violated_fractional_sec_sets(built, x_solution, z_solution, vehicle, scenario):
                    lhs, rhs = _sec_expr(built, component, z_solution, vehicle, scenario)
                    model.cbCut(lhs <= rhs)
        return

    if where != GRB.Callback.MIPSOL:
        return

    x_solution = model.cbGetSolution(built.x)
    z_solution = model.cbGetSolution(built.z)
    if hasattr(model, "cbGet"):
        incumbent_obj = float(model.cbGet(GRB.Callback.MIPSOL_OBJ))
        best_obj = float(getattr(model, "_alv_best_incumbent_obj", float("inf")))
        if incumbent_obj < best_obj - 1e-9:
            model._alv_best_incumbent_obj = incumbent_obj  # type: ignore[attr-defined]
            model._alv_best_incumbent_time = float(model.cbGet(GRB.Callback.RUNTIME))  # type: ignore[attr-defined]

    if getattr(model, "_alv_enable_primal_heuristic", False):
        y_solution = model.cbGetSolution(built.y)
        s_solution = model.cbGetSolution(built.s)
        integer_y = {key: int(float(value) > 0.5) for key, value in y_solution.items()}
        model._alv_primal_heuristic_attempts += 1  # type: ignore[attr-defined]
        heuristic = build_primal_heuristic_solution(
            built,
            integer_y,
            {key: int(float(value) > 0.5) for key, value in s_solution.items()},
            time_limit=_remaining_callback_time(model),
        )
        if heuristic is not None:
            model.cbSetSolution(
                list(heuristic.variable_values.keys()),
                list(heuristic.variable_values.values()),
            )
            model._alv_primal_heuristic_solutions += 1  # type: ignore[attr-defined]

    for vehicle in built.instance.vehicles:
        for scenario in built.scenario_ids:
            for component in _integer_subtour_components(built, x_solution, z_solution, vehicle, scenario):
                lhs, rhs = _sec_expr(built, component, z_solution, vehicle, scenario)
                model.cbLazy(lhs <= rhs)


def build_primal_heuristic_solution(
    built: BuiltModel,
    y_values: dict[tuple[int, int], int],
    s_values: dict[int, int],
    *,
    output_flag: int = 0,
    time_limit: float | None = None,
) -> BCPrimalHeuristicSolution | None:
    instance = built.instance
    variable_values: dict[Any, float] = {}
    for key, variable in built.y.items():
        variable_values[variable] = float(y_values[key])
    for key, variable in built.s.items():
        variable_values[variable] = float(s_values[key])

    consistency_penalty = 0.0
    for customer in instance.customers:
        assigned = sum(y_values[customer, vehicle] for vehicle in instance.vehicles)
        lam_value = max(0, assigned - instance.D)
        consistency_penalty += instance.penalties_consistency[customer] * lam_value
        variable_values[built.lam[customer]] = float(lam_value)

    scenario_costs: dict[int, float] = {}
    for scenario in instance.scenarios:
        sub_result = solve_fixed_y_scenario_subproblem(
            instance,
            scenario,
            y_values,
            name=f"{built.model.ModelName}_primal_heuristic_{scenario.id}",
            time_limit=time_limit,
            output_flag=output_flag,
        )
        if sub_result.status != GRB.OPTIMAL:
            return None
        scenario_costs[scenario.id] = sub_result.travel_cost + sub_result.skipping_cost
        for (customer, vehicle), value in sub_result.z_values.items():
            variable_values[built.z[customer, vehicle, scenario.id]] = value
        for (i, j, vehicle), value in sub_result.x_values.items():
            variable_values[built.x[i, j, vehicle, scenario.id]] = value

    for key, variable in built.z.items():
        variable_values.setdefault(variable, 0.0)
    for key, variable in built.x.items():
        variable_values.setdefault(variable, 0.0)

    expected_recourse = sum(
        scenario.probability * scenario_costs[scenario.id]
        for scenario in instance.scenarios
    )
    return BCPrimalHeuristicSolution(
        total_cost=float(consistency_penalty + expected_recourse),
        scenario_costs=scenario_costs,
        variable_values=variable_values,
    )


def _remaining_callback_time(model: gp.Model) -> float | None:
    time_limit = getattr(model, "_alv_time_limit", None)
    if time_limit is None:
        return None
    runtime = float(model.cbGet(GRB.Callback.RUNTIME))
    return max(1e-3, float(time_limit) - runtime)


def violated_fractional_sec_sets(
    built: BuiltModel,
    x_solution: Any,
    z_solution: Any,
    vehicle: int,
    scenario: int,
    *,
    tolerance: float = 1e-6,
) -> list[frozenset[int]]:
    depot = built.instance.depot
    active_customers = tuple(
        customer
        for customer in built.scenario_customers[scenario]
        if _solution_value(z_solution, (customer, vehicle, scenario)) > tolerance
    )
    if len(active_customers) < 2:
        return []

    nodes = (depot, *active_customers)
    cuts: list[frozenset[int]] = []
    seen: set[frozenset[int]] = set()
    for sink in active_customers:
        _, source_side = _undirected_min_cut_source_side(
            nodes,
            built.scenario_edges[scenario],
            x_solution,
            vehicle,
            scenario,
            source=depot,
            sink=sink,
            tolerance=tolerance,
        )
        component = frozenset(node for node in nodes if node not in source_side and node != depot)
        if len(component) < 2 or component in seen:
            continue
        ell = _sec_reference_customer(component, z_solution, vehicle, scenario)
        cut_capacity = _cut_capacity(built, component, x_solution, vehicle, scenario)
        if cut_capacity < 2.0 * _solution_value(z_solution, (ell, vehicle, scenario)) - tolerance:
            seen.add(component)
            cuts.append(component)
    return cuts


def _integer_subtour_components(
    built: BuiltModel,
    x_solution: Any,
    z_solution: Any,
    vehicle: int,
    scenario: int,
    *,
    tolerance: float = 1e-6,
) -> list[frozenset[int]]:
    depot = built.instance.depot
    visited = {
        customer
        for customer in built.scenario_customers[scenario]
        if _solution_value(z_solution, (customer, vehicle, scenario)) > 1.0 - tolerance
    }
    if len(visited) < 2:
        return []

    nodes = {depot, *visited}
    adjacency = {node: set() for node in nodes}
    for i, j in built.scenario_edges[scenario]:
        if i not in nodes or j not in nodes:
            continue
        if _solution_value(x_solution, (i, j, vehicle, scenario)) > tolerance:
            adjacency[i].add(j)
            adjacency[j].add(i)

    components: list[frozenset[int]] = []
    remaining = set(nodes)
    while remaining:
        start = remaining.pop()
        stack = [start]
        component = {start}
        while stack:
            node = stack.pop()
            for neighbor in adjacency[node]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)
        if depot not in component:
            subtour = frozenset(component & visited)
            if len(subtour) >= 2:
                components.append(subtour)
    return components


def _sec_expr(
    built: BuiltModel,
    component: frozenset[int],
    z_solution: Any,
    vehicle: int,
    scenario: int,
) -> tuple[gp.LinExpr, gp.LinExpr]:
    ell = _sec_reference_customer(component, z_solution, vehicle, scenario)
    lhs = gp.quicksum(
        built.x[i, j, vehicle, scenario]
        for i, j in built.scenario_edges[scenario]
        if i in component and j in component
    )
    rhs = gp.quicksum(
        built.z[i, vehicle, scenario]
        for i in component
        if i != ell
    )
    return lhs, rhs


def _sec_reference_customer(
    component: frozenset[int],
    z_solution: Any,
    vehicle: int,
    scenario: int,
) -> int:
    return max(
        component,
        key=lambda customer: (_solution_value(z_solution, (customer, vehicle, scenario)), -customer),
    )


def _cut_capacity(
    built: BuiltModel,
    component: frozenset[int],
    x_solution: Any,
    vehicle: int,
    scenario: int,
) -> float:
    total = 0.0
    for i, j in built.scenario_edges[scenario]:
        if (i in component) != (j in component):
            total += _solution_value(x_solution, (i, j, vehicle, scenario))
    return float(total)


def _undirected_min_cut_source_side(
    nodes: tuple[int, ...],
    edges: tuple[tuple[int, int], ...],
    x_solution: Any,
    vehicle: int,
    scenario: int,
    *,
    source: int,
    sink: int,
    tolerance: float,
) -> tuple[float, frozenset[int]]:
    residual = {node: {other: 0.0 for other in nodes if other != node} for node in nodes}
    for i, j in edges:
        if i not in residual or j not in residual:
            continue
        capacity = max(0.0, _solution_value(x_solution, (i, j, vehicle, scenario)))
        residual[i][j] += capacity
        residual[j][i] += capacity

    flow = 0.0
    while True:
        parent = _augmenting_path(residual, source, sink, tolerance)
        if sink not in parent:
            break
        augment = float("inf")
        node = sink
        while node != source:
            prev = parent[node]
            augment = min(augment, residual[prev][node])
            node = prev
        node = sink
        while node != source:
            prev = parent[node]
            residual[prev][node] -= augment
            residual[node][prev] += augment
            node = prev
        flow += augment

    source_side = set()
    stack = [source]
    while stack:
        node = stack.pop()
        if node in source_side:
            continue
        source_side.add(node)
        for neighbor, capacity in residual[node].items():
            if capacity > tolerance and neighbor not in source_side:
                stack.append(neighbor)
    return float(flow), frozenset(source_side)


def _augmenting_path(
    residual: dict[int, dict[int, float]],
    source: int,
    sink: int,
    tolerance: float,
) -> dict[int, int]:
    parent: dict[int, int] = {}
    queue = [source]
    seen = {source}
    for node in queue:
        if node == sink:
            break
        for neighbor, capacity in residual[node].items():
            if capacity <= tolerance or neighbor in seen:
                continue
            seen.add(neighbor)
            parent[neighbor] = node
            queue.append(neighbor)
    return parent


def _solution_value(solution: Any, key: tuple[int, ...]) -> float:
    if isinstance(solution, Mapping):
        return float(solution[key])
    return float(solution[key])
