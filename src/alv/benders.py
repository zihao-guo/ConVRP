from __future__ import annotations

from dataclasses import dataclass

import gurobipy as gp
from gurobipy import GRB

from alv.data import Instance, Scenario
from alv.subproblem import solve_fixed_y_scenario_subproblem


@dataclass(frozen=True)
class BuiltMaster:
    instance: Instance
    model: gp.Model
    y: dict[tuple[int, int], gp.Var]
    s: dict[int, gp.Var]
    lam: dict[int, gp.Var]
    theta: dict[int, gp.Var]
    scenario_lower_bounds: dict[int, float]
    cut_counts: dict[int, int]


@dataclass(frozen=True)
class ScenarioEvaluation:
    scenario_id: int
    status: int
    objective: float
    travel_cost: float
    skipping_cost: float
    skipped_customer_events: int
    total_customer_events: int


@dataclass(frozen=True)
class BendersIteration:
    index: int
    lower_bound: float
    first_stage_cost: float
    y_values: dict[tuple[int, int], int]
    lambda_values: dict[int, float]
    theta_values: dict[int, float]
    scenario_costs: dict[int, float]
    added_cuts: tuple[int, ...]


@dataclass(frozen=True)
class BendersResult:
    method: str
    status: int
    lower_bound: float
    upper_bound: float
    best_time_seconds: float | None
    best_y_values: dict[tuple[int, int], int] | None
    best_lambda_values: dict[int, float] | None
    iterations: tuple[BendersIteration, ...]
    master: BuiltMaster


def build_master(
    instance: Instance,
    *,
    name: str | None = None,
    time_limit: float | None = None,
    output_flag: int = 0,
    scenario_lower_bounds: dict[int, float] | None = None,
) -> BuiltMaster:
    model = gp.Model(name or f"convrp_benders_master_{instance.name}")
    model.Params.OutputFlag = output_flag
    model.Params.Threads = 1
    model.Params.MIPGap = 1e-5
    model.Params.LazyConstraints = 1
    if time_limit is not None:
        model.Params.TimeLimit = time_limit

    customers = instance.customers
    vehicles = instance.vehicles
    scenario_ids = tuple(scenario.id for scenario in instance.scenarios)
    scenario_by_id = {scenario.id: scenario for scenario in instance.scenarios}
    lower_bounds = {
        scenario_id: initial_scenario_lower_bound(instance, scenario_by_id[scenario_id])
        for scenario_id in scenario_ids
    }
    if scenario_lower_bounds is not None:
        lower_bounds.update({int(key): float(value) for key, value in scenario_lower_bounds.items()})

    y = {
        (i, k): model.addVar(vtype=GRB.BINARY, name=f"y[{i},{k}]")
        for i in customers
        for k in vehicles
    }
    s = {k: model.addVar(vtype=GRB.BINARY, name=f"s[{k}]") for k in vehicles}
    lam = {i: model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"lambda[{i}]") for i in customers}
    theta = {
        scenario_id: model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"theta[{scenario_id}]")
        for scenario_id in scenario_ids
    }
    model.update()

    for i in customers:
        model.addConstr(gp.quicksum(y[i, k] for k in vehicles) <= instance.D + lam[i], name=f"consistency[{i}]")
        model.addConstr(gp.quicksum(y[i, k] for k in vehicles) >= 1, name=f"valid_assign[{i}]")

    for k in vehicles:
        model.addConstr(gp.quicksum(y[i, k] for i in customers) <= len(customers) * s[k], name=f"activation[{k}]")

    for pos, k in enumerate(vehicles):
        if pos == 0:
            continue
        model.addConstr(s[k] <= s[vehicles[pos - 1]], name=f"sym_s[{k}]")

    for scenario_id in scenario_ids:
        model.addConstr(theta[scenario_id] >= lower_bounds[scenario_id], name=f"theta_lb[{scenario_id}]")

    consistency_penalty = gp.quicksum(instance.penalties_consistency[i] * lam[i] for i in customers)
    expected_recourse = gp.quicksum(scenario.probability * theta[scenario.id] for scenario in instance.scenarios)
    model.setObjective(consistency_penalty + expected_recourse, GRB.MINIMIZE)
    model.update()

    built = BuiltMaster(
        instance=instance,
        model=model,
        y=y,
        s=s,
        lam=lam,
        theta=theta,
        scenario_lower_bounds=lower_bounds,
        cut_counts={scenario_id: 0 for scenario_id in scenario_ids},
    )
    model._alv_benders_master = built  # type: ignore[attr-defined]
    return built


def evaluate_scenario_subproblem(
    instance: Instance,
    scenario: Scenario,
    y_values: dict[tuple[int, int], int | float],
    *,
    name: str | None = None,
    output_flag: int = 0,
    time_limit: float | None = None,
) -> ScenarioEvaluation:
    result = solve_fixed_y_scenario_subproblem(
        instance,
        scenario,
        y_values,
        name=name or f"convrp_benders_subproblem_{instance.name}_{scenario.id}",
        output_flag=output_flag,
        time_limit=time_limit,
    )
    return ScenarioEvaluation(
        scenario_id=scenario.id,
        status=result.status,
        objective=result.objective,
        travel_cost=result.travel_cost,
        skipping_cost=result.skipping_cost,
        skipped_customer_events=result.skipped_customer_events,
        total_customer_events=len(scenario.demands),
    )


def add_integer_optimality_cut(
    master: BuiltMaster,
    *,
    scenario_id: int,
    y_hat: dict[tuple[int, int], int],
    recourse_cost: float,
    lower_bound: float | None = None,
) -> gp.Constr:
    expr = _integer_cut_selector_expr(master, y_hat)
    rhs = float(recourse_cost) * expr
    cut_index = master.cut_counts[scenario_id]
    constr = master.model.addConstr(
        master.theta[scenario_id] >= rhs,
        name=f"integer_optimality[{scenario_id},{cut_index}]",
    )
    master.cut_counts[scenario_id] += 1
    master.model.update()
    return constr


def integer_cut_rhs_value(
    y_values: dict[tuple[int, int], int],
    y_hat: dict[tuple[int, int], int],
    *,
    recourse_cost: float,
    lower_bound: float,
) -> float:
    ones = sum(y_hat.values())
    selector = (
        sum(y_values[key] for key, value in y_hat.items() if value == 1)
        - sum(y_values[key] for key, value in y_hat.items() if value == 0)
        - ones
        + 1
    )
    return float(recourse_cost * selector)


def initial_scenario_lower_bound(instance: Instance, scenario: Scenario) -> float:
    active_customers = tuple(sorted(scenario.demands))
    if not active_customers:
        return 0.0
    active_nodes = (instance.depot, *active_customers)
    total = 0.0
    for i in active_customers:
        adjacent_costs = []
        for j in active_nodes:
            if i == j:
                continue
            edge = (min(i, j), max(i, j))
            adjacent_costs.append(instance.distances[edge])
        total += min(instance.penalties_skip[i], min(adjacent_costs))
    return float(total)


def solve_benders_like(
    instance: Instance,
    *,
    name: str | None = None,
    max_iterations: int = 50,
    tolerance: float = 1e-6,
    time_limit: float | None = None,
    output_flag: int = 0,
) -> BendersResult:
    return solve_benders_branch_and_check(
        instance,
        name=name,
        tolerance=tolerance,
        time_limit=time_limit,
        output_flag=output_flag,
    )


def solve_benders_branch_and_check(
    instance: Instance,
    *,
    name: str | None = None,
    tolerance: float = 1e-6,
    time_limit: float | None = None,
    output_flag: int = 0,
) -> BendersResult:
    master = build_master(instance, name=name, time_limit=time_limit, output_flag=output_flag)
    master.model._alv_time_limit = time_limit  # type: ignore[attr-defined]
    master.model._alv_benders_tolerance = tolerance  # type: ignore[attr-defined]
    master.model._alv_benders_iterations = []  # type: ignore[attr-defined]
    master.model._alv_best_upper_bound = float("inf")  # type: ignore[attr-defined]
    master.model._alv_best_upper_bound_time = None  # type: ignore[attr-defined]
    master.model._alv_best_y_values = None  # type: ignore[attr-defined]
    master.model._alv_best_lambda_values = None  # type: ignore[attr-defined]

    master.model.optimize(_benders_branch_and_check_callback)
    iterations = tuple(master.model._alv_benders_iterations)  # type: ignore[attr-defined]
    status = master.model.Status
    lower_bound = float(master.model.ObjBound) if master.model.SolCount else float("inf")
    upper_bound = float(master.model._alv_best_upper_bound)  # type: ignore[attr-defined]
    if upper_bound == float("inf") and master.model.SolCount:
        upper_bound = float(master.model.ObjVal)
    best_time = master.model._alv_best_upper_bound_time  # type: ignore[attr-defined]
    return BendersResult(
        method="BD",
        status=status,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        best_time_seconds=best_time,
        best_y_values=master.model._alv_best_y_values,  # type: ignore[attr-defined]
        best_lambda_values=master.model._alv_best_lambda_values,  # type: ignore[attr-defined]
        iterations=iterations,
        master=master,
    )


def _benders_branch_and_check_callback(model: gp.Model, where: int) -> None:
    if where != GRB.Callback.MIPSOL:
        return

    master: BuiltMaster = model._alv_benders_master  # type: ignore[attr-defined]
    tolerance: float = model._alv_benders_tolerance  # type: ignore[attr-defined]
    y_solution = model.cbGetSolution(master.y)
    theta_solution = model.cbGetSolution(master.theta)
    lam_solution = model.cbGetSolution(master.lam)
    y_values = {key: int(float(value) > 0.5) for key, value in y_solution.items()}
    lambda_values = {customer: float(value) for customer, value in lam_solution.items()}

    first_stage_cost = sum(master.instance.penalties_consistency[i] * float(lam_solution[i]) for i in master.instance.customers)
    theta_values = {scenario_id: float(value) for scenario_id, value in theta_solution.items()}
    scenario_costs: dict[int, float] = {}
    added_cuts: list[int] = []

    for scenario in master.instance.scenarios:
        evaluation = evaluate_scenario_subproblem(
            master.instance,
            scenario,
            y_values,
            name=f"{master.model.ModelName}_callback_subproblem_{len(model._alv_benders_iterations)}_{scenario.id}",  # type: ignore[attr-defined]
            output_flag=0,
            time_limit=_remaining_callback_time(model),
        )
        if evaluation.status != GRB.OPTIMAL:
            continue
        scenario_costs[scenario.id] = evaluation.objective
        if theta_values[scenario.id] < evaluation.objective - tolerance:
            lhs = master.theta[scenario.id]
            rhs = evaluation.objective * _integer_cut_selector_expr(master, y_values)
            model.cbLazy(lhs >= rhs)
            added_cuts.append(scenario.id)

    if scenario_costs:
        candidate_upper_bound = first_stage_cost + sum(
            scenario.probability * scenario_costs[scenario.id]
            for scenario in master.instance.scenarios
            if scenario.id in scenario_costs
        )
        if candidate_upper_bound < float(model._alv_best_upper_bound) - tolerance:  # type: ignore[attr-defined]
            model._alv_best_upper_bound = candidate_upper_bound  # type: ignore[attr-defined]
            model._alv_best_upper_bound_time = float(model.cbGet(GRB.Callback.RUNTIME))  # type: ignore[attr-defined]
            model._alv_best_y_values = dict(y_values)  # type: ignore[attr-defined]
            model._alv_best_lambda_values = dict(lambda_values)  # type: ignore[attr-defined]
    model._alv_benders_iterations.append(  # type: ignore[attr-defined]
        BendersIteration(
            index=len(model._alv_benders_iterations),  # type: ignore[attr-defined]
            lower_bound=first_stage_cost
            + sum(scenario.probability * theta_values[scenario.id] for scenario in master.instance.scenarios),
            first_stage_cost=float(first_stage_cost),
            y_values=y_values,
            lambda_values=lambda_values,
            theta_values=theta_values,
            scenario_costs=scenario_costs,
            added_cuts=tuple(added_cuts),
        )
    )


def _remaining_callback_time(model: gp.Model) -> float | None:
    time_limit = getattr(model, "_alv_time_limit", None)
    if time_limit is None:
        return None
    runtime = float(model.cbGet(GRB.Callback.RUNTIME))
    return max(1e-3, float(time_limit) - runtime)


def solve_benders_iterative(
    instance: Instance,
    *,
    name: str | None = None,
    max_iterations: int = 50,
    tolerance: float = 1e-6,
    time_limit: float | None = None,
    output_flag: int = 0,
) -> BendersResult:
    master = build_master(instance, name=name, time_limit=time_limit, output_flag=output_flag)
    iterations: list[BendersIteration] = []
    best_upper_bound = float("inf")
    last_master_bound = float("inf")
    status = GRB.LOADED

    for iteration_index in range(max_iterations):
        master.model.optimize()
        status = master.model.Status
        if status != GRB.OPTIMAL:
            break

        master_bound = float(master.model.ObjVal)
        last_master_bound = master_bound
        y_values = _solution_y_values(master)
        theta_values = {scenario_id: float(var.X) for scenario_id, var in master.theta.items()}
        first_stage_cost = sum(instance.penalties_consistency[i] * master.lam[i].X for i in instance.customers)

        scenario_costs: dict[int, float] = {}
        added_cuts: list[int] = []
        for scenario in instance.scenarios:
            evaluation = evaluate_scenario_subproblem(
                instance,
                scenario,
                y_values,
                name=f"{name or instance.name}_subproblem_{iteration_index}_{scenario.id}",
                output_flag=output_flag,
            )
            if evaluation.status != GRB.OPTIMAL:
                status = evaluation.status
                break
            scenario_costs[scenario.id] = evaluation.objective
            if theta_values[scenario.id] < evaluation.objective - tolerance:
                add_integer_optimality_cut(
                    master,
                    scenario_id=scenario.id,
                    y_hat=y_values,
                    recourse_cost=evaluation.objective,
                )
                added_cuts.append(scenario.id)

        if status != GRB.OPTIMAL:
            break

        candidate_upper_bound = first_stage_cost + sum(
            scenario.probability * scenario_costs[scenario.id] for scenario in instance.scenarios
        )
        best_upper_bound = min(best_upper_bound, candidate_upper_bound)
        iterations.append(
            BendersIteration(
                index=iteration_index,
                lower_bound=master_bound,
                first_stage_cost=float(first_stage_cost),
                y_values=y_values,
                lambda_values={customer: float(master.lam[customer].X) for customer in instance.customers},
                theta_values=theta_values,
                scenario_costs=scenario_costs,
                added_cuts=tuple(added_cuts),
            )
        )
        if not added_cuts:
            break

    lower_bound = last_master_bound if status == GRB.OPTIMAL else float("inf")
    return BendersResult(
        method="BD-like",
        status=status,
        lower_bound=lower_bound,
        upper_bound=best_upper_bound,
        best_time_seconds=None,
        best_y_values=iterations[-1].y_values if iterations else None,
        best_lambda_values=iterations[-1].lambda_values if iterations else None,
        iterations=tuple(iterations),
        master=master,
    )


def _integer_cut_selector_expr(master: BuiltMaster, y_hat: dict[tuple[int, int], int]) -> gp.LinExpr:
    ones = sum(y_hat.values())
    return (
        gp.quicksum(master.y[key] for key, value in y_hat.items() if value == 1)
        - gp.quicksum(master.y[key] for key, value in y_hat.items() if value == 0)
        - ones
        + 1
    )


def _solution_y_values(master: BuiltMaster) -> dict[tuple[int, int], int]:
    return {key: int(var.X > 0.5) for key, var in master.y.items()}


def _incident_expr(
    x: dict[tuple[int, int, int], gp.Var],
    edges: tuple[tuple[int, int], ...],
    node: int,
    vehicle: int,
) -> gp.LinExpr:
    return gp.quicksum(x[i, j, vehicle] for i, j in edges if i == node or j == node)
