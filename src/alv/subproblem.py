from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import gurobipy as gp
from gurobipy import GRB

from alv.data import Instance, Scenario


@dataclass(frozen=True)
class FixedYScenarioSubproblem:
    instance: Instance
    scenario: Scenario
    model: gp.Model
    z: dict[tuple[int, int], gp.Var]
    x: dict[tuple[int, int, int], gp.Var]
    active_customers: tuple[int, ...]
    active_edges: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class FixedYScenarioResult:
    scenario_id: int
    status: int
    objective: float
    travel_cost: float
    skipping_cost: float
    skipped_customer_events: int
    total_customer_events: int
    z_values: dict[tuple[int, int], float]
    x_values: dict[tuple[int, int, int], float]


def solve_fixed_y_scenario_subproblem(
    instance: Instance,
    scenario: Scenario,
    y_values: dict[tuple[int, int], int | float],
    *,
    name: str | None = None,
    output_flag: int = 0,
    time_limit: float | None = None,
) -> FixedYScenarioResult:
    built = build_fixed_y_scenario_subproblem(
        instance,
        scenario,
        y_values,
        name=name,
        output_flag=output_flag,
        time_limit=time_limit,
    )
    try:
        built.model.optimize(_fixed_y_subproblem_callback)

        if built.model.Status != GRB.OPTIMAL:
            return FixedYScenarioResult(
                scenario_id=scenario.id,
                status=built.model.Status,
                objective=float("inf"),
                travel_cost=float("inf"),
                skipping_cost=float("inf"),
                skipped_customer_events=0,
                total_customer_events=len(scenario.demands),
                z_values={},
                x_values={},
            )

        travel_cost = sum(
            instance.distances[i, j] * built.x[i, j, k].X
            for i, j in built.active_edges
            for k in instance.vehicles
        )
        skipping_cost = sum(
            instance.penalties_skip[i] * (1.0 - sum(built.z[i, k].X for k in instance.vehicles))
            for i in built.active_customers
        )
        skipped_customer_events = sum(
            1
            for i in built.active_customers
            if sum(built.z[i, k].X for k in instance.vehicles) <= 0.5
        )
        return FixedYScenarioResult(
            scenario_id=scenario.id,
            status=built.model.Status,
            objective=float(travel_cost + skipping_cost),
            travel_cost=float(travel_cost),
            skipping_cost=float(skipping_cost),
            skipped_customer_events=int(skipped_customer_events),
            total_customer_events=len(scenario.demands),
            z_values={key: float(var.X) for key, var in built.z.items()},
            x_values={key: float(var.X) for key, var in built.x.items()},
        )
    finally:
        built.model.dispose()


def build_fixed_y_scenario_subproblem(
    instance: Instance,
    scenario: Scenario,
    y_values: dict[tuple[int, int], int | float],
    *,
    name: str | None = None,
    output_flag: int = 0,
    time_limit: float | None = None,
) -> FixedYScenarioSubproblem:
    model = gp.Model(name or f"convrp_fixed_y_subproblem_{instance.name}_{scenario.id}")
    model.Params.OutputFlag = output_flag
    model.Params.Threads = 1
    model.Params.MIPGap = 1e-5
    model.Params.LazyConstraints = 1
    model.Params.PreCrush = 1
    if time_limit is not None:
        model.Params.TimeLimit = time_limit

    active_customers = tuple(sorted(scenario.demands))
    active_nodes = (instance.depot, *active_customers)
    active_node_set = set(active_nodes)
    active_edges = tuple(
        sorted(edge for edge in instance.distances if edge[0] in active_node_set and edge[1] in active_node_set)
    )

    z = {
        (i, k): model.addVar(vtype=GRB.BINARY, name=f"z[{i},{k}]")
        for i in active_customers
        for k in instance.vehicles
    }
    x: dict[tuple[int, int, int], gp.Var] = {}
    for i, j in active_edges:
        for k in instance.vehicles:
            if i == instance.depot:
                x[i, j, k] = model.addVar(lb=0.0, ub=2.0, vtype=GRB.INTEGER, name=f"x[{i},{j},{k}]")
            else:
                x[i, j, k] = model.addVar(vtype=GRB.BINARY, name=f"x[{i},{j},{k}]")
    model.update()

    for i in active_customers:
        model.addConstr(gp.quicksum(z[i, k] for k in instance.vehicles) <= 1, name=f"visit_once[{i}]")
        for k in instance.vehicles:
            model.addConstr(z[i, k] <= int(float(y_values[i, k]) > 0.5), name=f"link[{i},{k}]")

    for k in instance.vehicles:
        for i in active_customers:
            model.addConstr(_incident_expr(x, active_edges, i, k) == 2 * z[i, k], name=f"degree[{i},{k}]")
        model.addConstr(
            gp.quicksum(x[instance.depot, j, k] for j in active_customers if (instance.depot, j, k) in x) <= 2,
            name=f"depot_degree[{k}]",
        )
        model.addConstr(
            gp.quicksum(scenario.demands[i] * z[i, k] for i in active_customers) <= instance.capacity,
            name=f"capacity[{k}]",
        )

    travel = gp.quicksum(
        instance.distances[i, j] * x[i, j, k]
        for i, j in active_edges
        for k in instance.vehicles
    )
    skipping = gp.quicksum(
        instance.penalties_skip[i] * (1 - gp.quicksum(z[i, k] for k in instance.vehicles))
        for i in active_customers
    )
    model.setObjective(travel + skipping, GRB.MINIMIZE)

    built = FixedYScenarioSubproblem(
        instance=instance,
        scenario=scenario,
        model=model,
        z=z,
        x=x,
        active_customers=active_customers,
        active_edges=active_edges,
    )
    model._alv_fixed_y_subproblem = built  # type: ignore[attr-defined]
    return built


def _fixed_y_subproblem_callback(model: gp.Model, where: int) -> None:
    built: FixedYScenarioSubproblem = model._alv_fixed_y_subproblem  # type: ignore[attr-defined]
    if where == GRB.Callback.MIPNODE:
        if model.cbGet(GRB.Callback.MIPNODE_STATUS) != GRB.OPTIMAL:
            return
        if int(model.cbGet(GRB.Callback.MIPNODE_NODCNT)) != 0:
            return
        x_solution = model.cbGetNodeRel(built.x)
        z_solution = model.cbGetNodeRel(built.z)
        for vehicle in built.instance.vehicles:
            for component in _violated_fractional_sec_sets(built, x_solution, z_solution, vehicle):
                lhs, rhs = _sec_expr(built, component, z_solution, vehicle)
                model.cbCut(lhs <= rhs)
        return

    if where != GRB.Callback.MIPSOL:
        return

    x_solution = model.cbGetSolution(built.x)
    z_solution = model.cbGetSolution(built.z)
    for vehicle in built.instance.vehicles:
        for component in _integer_subtour_components(built, x_solution, z_solution, vehicle):
            lhs, rhs = _sec_expr(built, component, z_solution, vehicle)
            model.cbLazy(lhs <= rhs)


def _incident_expr(
    x: dict[tuple[int, int, int], gp.Var],
    edges: tuple[tuple[int, int], ...],
    node: int,
    vehicle: int,
) -> gp.LinExpr:
    return gp.quicksum(x[i, j, vehicle] for i, j in edges if i == node or j == node)


def _integer_subtour_components(
    built: FixedYScenarioSubproblem,
    x_solution: Any,
    z_solution: Any,
    vehicle: int,
    *,
    tolerance: float = 1e-6,
) -> list[frozenset[int]]:
    depot = built.instance.depot
    visited = {
        customer
        for customer in built.active_customers
        if _solution_value(z_solution, (customer, vehicle)) > 1.0 - tolerance
    }
    if len(visited) < 2:
        return []

    nodes = {depot, *visited}
    adjacency = {node: set() for node in nodes}
    for i, j in built.active_edges:
        if i not in nodes or j not in nodes:
            continue
        if _solution_value(x_solution, (i, j, vehicle)) > tolerance:
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


def _violated_fractional_sec_sets(
    built: FixedYScenarioSubproblem,
    x_solution: Any,
    z_solution: Any,
    vehicle: int,
    *,
    tolerance: float = 1e-6,
) -> list[frozenset[int]]:
    depot = built.instance.depot
    active_customers = tuple(
        customer
        for customer in built.active_customers
        if _solution_value(z_solution, (customer, vehicle)) > tolerance
    )
    if len(active_customers) < 2:
        return []

    nodes = (depot, *active_customers)
    cuts: list[frozenset[int]] = []
    seen: set[frozenset[int]] = set()
    for sink in active_customers:
        _, source_side = _undirected_min_cut_source_side(
            nodes,
            built.active_edges,
            x_solution,
            vehicle,
            source=depot,
            sink=sink,
            tolerance=tolerance,
        )
        component = frozenset(node for node in nodes if node not in source_side and node != depot)
        if len(component) < 2 or component in seen:
            continue
        ell = _sec_reference_customer(component, z_solution, vehicle)
        cut_capacity = _cut_capacity(built, component, x_solution, vehicle)
        if cut_capacity < 2.0 * _solution_value(z_solution, (ell, vehicle)) - tolerance:
            seen.add(component)
            cuts.append(component)
    return cuts


def _sec_expr(
    built: FixedYScenarioSubproblem,
    component: frozenset[int],
    z_solution: Any,
    vehicle: int,
) -> tuple[gp.LinExpr, gp.LinExpr]:
    ell = _sec_reference_customer(component, z_solution, vehicle)
    lhs = gp.quicksum(
        built.x[i, j, vehicle]
        for i, j in built.active_edges
        if i in component and j in component
    )
    rhs = gp.quicksum(built.z[i, vehicle] for i in component if i != ell)
    return lhs, rhs


def _sec_reference_customer(component: frozenset[int], z_solution: Any, vehicle: int) -> int:
    return max(component, key=lambda customer: (_solution_value(z_solution, (customer, vehicle)), -customer))


def _cut_capacity(
    built: FixedYScenarioSubproblem,
    component: frozenset[int],
    x_solution: Any,
    vehicle: int,
) -> float:
    total = 0.0
    for i, j in built.active_edges:
        if (i in component) != (j in component):
            total += _solution_value(x_solution, (i, j, vehicle))
    return float(total)


def _undirected_min_cut_source_side(
    nodes: tuple[int, ...],
    edges: tuple[tuple[int, int], ...],
    x_solution: Any,
    vehicle: int,
    *,
    source: int,
    sink: int,
    tolerance: float,
) -> tuple[float, frozenset[int]]:
    residual = {node: {other: 0.0 for other in nodes if other != node} for node in nodes}
    for i, j in edges:
        if i not in residual or j not in residual:
            continue
        capacity = max(0.0, _solution_value(x_solution, (i, j, vehicle)))
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
