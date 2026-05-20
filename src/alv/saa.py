from __future__ import annotations

import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gurobipy import GRB

from alv.benders import evaluate_scenario_subproblem, solve_benders_like
from alv.branch_cut import solve_branch_and_cut
from alv.data import Instance, Scenario
from alv.model import objective_accounting, solution_first_stage_y


MethodName = Literal["SAA-BC", "SAA-BD"]


@dataclass(frozen=True)
class SAAConfig:
    method: MethodName
    replications: int
    sample_size: int
    sample_time_limit_seconds: int
    seed: int = 0


@dataclass(frozen=True)
class FullOmegaEvaluation:
    total_cost: float
    consistency_penalty: float
    recourse_cost: float
    travel_cost: float
    skipping_cost: float
    scenario_costs: dict[int, float]
    skipped_customer_events: int
    total_customer_events: int
    skipped_customers_percent: float


@dataclass(frozen=True)
class SAAReplicationResult:
    replication: int
    sample_membership: tuple[int, ...]
    sample_status: int
    sample_objective: float | None
    sample_lower_bound: float | None
    full_omega_evaluation: FullOmegaEvaluation | None
    y_values: dict[tuple[int, int], int]
    lambda_values: dict[int, float]


@dataclass(frozen=True)
class SAAStatistics:
    sample_lower_bound_mean: float | None
    sample_lower_bound_variance: float | None
    incumbent_variance: float | None
    saa_gap: float | None
    saa_gap_variance: float | None
    opt_gap_percent: float | None
    sample_gap_percent: float | None
    evaluated_replications: int
    sample_gap_count: int


@dataclass(frozen=True)
class SAAResult:
    method: MethodName
    config: SAAConfig
    replications: tuple[SAAReplicationResult, ...]
    best_replication: int | None
    best_total_cost: float | None
    best_time_seconds: float | None
    statistics: SAAStatistics | None


SAA_BC_CONFIG = SAAConfig(method="SAA-BC", replications=20, sample_size=5, sample_time_limit_seconds=30 * 60)
SAA_BD_CONFIG = SAAConfig(method="SAA-BD", replications=20, sample_size=15, sample_time_limit_seconds=30 * 60)


def make_sample_plan(
    instance: Instance,
    *,
    replications: int,
    sample_size: int,
    seed: int,
) -> tuple[tuple[int, ...], ...]:
    scenario_ids = [scenario.id for scenario in instance.scenarios]
    if sample_size > len(scenario_ids):
        raise ValueError(f"sample_size {sample_size} exceeds scenario count {len(scenario_ids)}")
    rng = random.Random(seed)
    return tuple(tuple(sorted(rng.sample(scenario_ids, sample_size))) for _ in range(replications))


def sample_instance(instance: Instance, sample_membership: tuple[int, ...]) -> Instance:
    selected = set(sample_membership)
    scenarios = tuple(
        Scenario(id=scenario.id, probability=1.0 / len(sample_membership), demands=dict(scenario.demands))
        for scenario in instance.scenarios
        if scenario.id in selected
    )
    if len(scenarios) != len(sample_membership):
        raise ValueError("sample membership contains unknown scenario ids")
    metadata = dict(instance.metadata)
    metadata["full_omega"] = instance.omega
    metadata["omega"] = len(sample_membership)
    metadata["sample_membership"] = list(sample_membership)
    return Instance(
        path=Path(f"{instance.path.stem}__sample{len(sample_membership)}.json"),
        set_name=instance.set_name,
        name=instance.name,
        capacity=instance.capacity,
        depot=instance.depot,
        customers=instance.customers,
        D=instance.D,
        vehicles=instance.vehicles,
        penalties_skip=instance.penalties_skip,
        penalties_consistency=instance.penalties_consistency,
        coordinates=instance.coordinates,
        scenarios=scenarios,
        distances=instance.distances,
        metadata=metadata,
    )


def evaluate_first_stage_on_full_omega(
    instance: Instance,
    y_values: dict[tuple[int, int], int],
    *,
    lambda_values: dict[int, float] | None = None,
    output_flag: int = 0,
) -> FullOmegaEvaluation:
    consistency_penalty = 0.0
    for i in instance.customers:
        if lambda_values is None:
            assigned = sum(int(round(float(y_values[i, k]))) for k in instance.vehicles)
            lambda_value = max(0, assigned - instance.D)
        else:
            lambda_value = float(lambda_values[i])
        consistency_penalty += instance.penalties_consistency[i] * lambda_value

    scenario_costs: dict[int, float] = {}
    recourse_cost = 0.0
    travel_cost = 0.0
    skipping_cost = 0.0
    skipped_customer_events = 0
    total_customer_events = 0
    for scenario in instance.scenarios:
        evaluation = evaluate_scenario_subproblem(
            instance,
            scenario,
            y_values,
            name=f"saa_eval_{instance.name}_{scenario.id}",
            output_flag=output_flag,
        )
        if evaluation.status != GRB.OPTIMAL:
            raise RuntimeError(f"scenario {scenario.id} evaluation failed with status {evaluation.status}")
        scenario_costs[scenario.id] = evaluation.objective
        recourse_cost += scenario.probability * evaluation.objective
        travel_cost += scenario.probability * evaluation.travel_cost
        skipping_cost += scenario.probability * evaluation.skipping_cost
        skipped_customer_events += evaluation.skipped_customer_events
        total_customer_events += evaluation.total_customer_events

    return FullOmegaEvaluation(
        total_cost=float(consistency_penalty + recourse_cost),
        consistency_penalty=float(consistency_penalty),
        recourse_cost=float(recourse_cost),
        travel_cost=float(travel_cost),
        skipping_cost=float(skipping_cost),
        scenario_costs=scenario_costs,
        skipped_customer_events=skipped_customer_events,
        total_customer_events=total_customer_events,
        skipped_customers_percent=0.0
        if total_customer_events == 0
        else float(100.0 * skipped_customer_events / total_customer_events),
    )


def run_saa(
    instance: Instance,
    config: SAAConfig,
    *,
    sample_plan: tuple[tuple[int, ...], ...] | None = None,
    output_flag: int = 0,
) -> SAAResult:
    memberships = sample_plan or make_sample_plan(
        instance,
        replications=config.replications,
        sample_size=config.sample_size,
        seed=config.seed,
    )
    replications: list[SAAReplicationResult] = []
    best_replication: int | None = None
    best_total_cost = float("inf")
    best_time_seconds: float | None = None
    started = time.time()

    for index, membership in enumerate(memberships):
        sampled = sample_instance(instance, membership)
        if config.method == "SAA-BC":
            built = solve_branch_and_cut(
                sampled,
                name=f"saa_bc_{instance.name}_{index}",
                time_limit=config.sample_time_limit_seconds,
                output=bool(output_flag),
            )
            status = built.model.Status
            sample_objective = float(built.model.ObjVal) if built.model.SolCount else None
            sample_lower_bound = float(built.model.ObjBound) if built.model.SolCount else None
            y_values = solution_first_stage_y(built) if built.model.SolCount else {}
            lambda_values = {customer: float(built.lam[customer].X) for customer in instance.customers} if built.model.SolCount else {}
        elif config.method == "SAA-BD":
            result = solve_benders_like(
                sampled,
                name=f"saa_bd_{instance.name}_{index}",
                max_iterations=50,
                time_limit=config.sample_time_limit_seconds,
                output_flag=output_flag,
            )
            status = result.status
            sample_objective = result.upper_bound if result.upper_bound != float("inf") else None
            sample_lower_bound = result.lower_bound if result.lower_bound != float("inf") else None
            y_values = result.best_y_values or {}
            lambda_values = result.best_lambda_values or {}
        else:
            raise ValueError(f"unknown SAA method {config.method}")

        full_eval = (
            evaluate_first_stage_on_full_omega(
                instance,
                y_values,
                lambda_values=lambda_values,
                output_flag=output_flag,
            )
            if y_values
            else None
        )
        if full_eval is not None and full_eval.total_cost < best_total_cost:
            best_total_cost = full_eval.total_cost
            best_replication = index
            best_time_seconds = time.time() - started
        replications.append(
            SAAReplicationResult(
                replication=index,
                sample_membership=tuple(membership),
                sample_status=status,
                sample_objective=sample_objective,
                sample_lower_bound=sample_lower_bound,
                full_omega_evaluation=full_eval,
                y_values=y_values,
                lambda_values=lambda_values,
            )
        )

    replications_tuple = tuple(replications)
    statistics = compute_saa_statistics(
        instance,
        config=config,
        replications=replications_tuple,
        best_replication=best_replication,
    )

    return SAAResult(
        method=config.method,
        config=config,
        replications=replications_tuple,
        best_replication=best_replication,
        best_total_cost=None if best_replication is None else float(best_total_cost),
        best_time_seconds=best_time_seconds,
        statistics=statistics,
    )


def compute_saa_statistics(
    instance: Instance,
    *,
    config: SAAConfig,
    replications: tuple[SAAReplicationResult, ...],
    best_replication: int | None,
) -> SAAStatistics:
    lower_bound_values = [
        value
        for replication in replications
        if (value := _sample_lower_bound_value(replication)) is not None
    ]
    sample_lower_bound_mean = _mean(lower_bound_values)
    sample_lower_bound_variance = _sample_mean_variance(lower_bound_values)

    best_eval = None
    if best_replication is not None:
        for replication in replications:
            if replication.replication == best_replication:
                best_eval = replication.full_omega_evaluation
                break

    incumbent_variance = _incumbent_variance(instance, best_eval)
    saa_gap = None
    saa_gap_variance = None
    opt_gap_percent = None
    if best_eval is not None and sample_lower_bound_mean is not None:
        saa_gap = float(best_eval.total_cost - sample_lower_bound_mean)
        if incumbent_variance is not None and sample_lower_bound_variance is not None:
            saa_gap_variance = float(incumbent_variance + sample_lower_bound_variance)
        if abs(best_eval.total_cost) > 1e-12:
            opt_gap_percent = float(100.0 * saa_gap / abs(best_eval.total_cost))

    sample_gaps = []
    for replication in replications:
        if replication.sample_objective is None or replication.sample_lower_bound is None:
            continue
        if abs(replication.sample_objective) <= 1e-12:
            continue
        sample_gaps.append(
            100.0
            * max(0.0, replication.sample_objective - replication.sample_lower_bound)
            / abs(replication.sample_objective)
        )

    return SAAStatistics(
        sample_lower_bound_mean=sample_lower_bound_mean,
        sample_lower_bound_variance=sample_lower_bound_variance,
        incumbent_variance=incumbent_variance,
        saa_gap=saa_gap,
        saa_gap_variance=saa_gap_variance,
        opt_gap_percent=opt_gap_percent,
        sample_gap_percent=_mean(sample_gaps),
        evaluated_replications=sum(1 for replication in replications if replication.full_omega_evaluation is not None),
        sample_gap_count=len(sample_gaps),
    )


def _sample_lower_bound_value(replication: SAAReplicationResult) -> float | None:
    if replication.sample_lower_bound is not None:
        return float(replication.sample_lower_bound)
    if replication.sample_objective is not None:
        return float(replication.sample_objective)
    return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def _sample_mean_variance(values: list[float]) -> float | None:
    count = len(values)
    if count < 2:
        return None
    mean = sum(values) / count
    return float(sum((value - mean) ** 2 for value in values) / (count * (count - 1)))


def _incumbent_variance(instance: Instance, evaluation: FullOmegaEvaluation | None) -> float | None:
    if evaluation is None:
        return None
    scenario_ids = [scenario.id for scenario in instance.scenarios]
    count = len(scenario_ids)
    if count < 2:
        return None
    if any(scenario_id not in evaluation.scenario_costs for scenario_id in scenario_ids):
        return None
    scenario_total_values = [
        evaluation.consistency_penalty + evaluation.scenario_costs[scenario_id]
        for scenario_id in scenario_ids
    ]
    return float(
        sum((value - evaluation.total_cost) ** 2 for value in scenario_total_values)
        / (count * (count - 1))
    )
