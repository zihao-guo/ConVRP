from __future__ import annotations

import unittest
from pathlib import Path

from gurobipy import GRB

from alv.benders import (
    add_integer_optimality_cut,
    build_master,
    evaluate_scenario_subproblem,
    integer_cut_rhs_value,
    initial_scenario_lower_bound,
    solve_benders_branch_and_check,
)
from alv.data import Instance, Scenario


def tiny_two_scenario_instance() -> Instance:
    return Instance(
        path=Path("tiny__omega2__alpha100.json"),
        set_name="A",
        name="tiny",
        capacity=2,
        depot=0,
        customers=(1, 2),
        D=1,
        vehicles=(0, 1),
        penalties_skip={1: 6.0, 2: 6.0},
        penalties_consistency={1: 0.2, 2: 0.2},
        coordinates=((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)),
        scenarios=(
            Scenario(id=0, probability=0.5, demands={1: 1, 2: 1}),
            Scenario(id=1, probability=0.5, demands={1: 1}),
        ),
        distances={(0, 1): 1, (0, 2): 1, (1, 2): 1},
        metadata={"omega": 2, "alpha": 1.0, "epsilon": 0.5},
    )


class BendersTests(unittest.TestCase):
    def test_master_contains_first_stage_theta_and_initial_lower_bound_cuts(self) -> None:
        built = build_master(tiny_two_scenario_instance(), name="tiny_benders_master")

        self.assertEqual(len(built.y), 4)
        self.assertEqual(len(built.s), 2)
        self.assertEqual(len(built.lam), 2)
        self.assertEqual(set(built.theta), {0, 1})
        self.assertEqual(len(built.theta), 2)
        self.assertEqual(built.model.Params.Threads, 1)
        self.assertAlmostEqual(built.model.Params.MIPGap, 1e-5)
        self.assertEqual(built.model.Params.LazyConstraints, 1)
        self.assertIsNotNone(built.model.getConstrByName("theta_lb[0]"))
        self.assertIsNotNone(built.model.getConstrByName("theta_lb[1]"))
        self.assertEqual(built.scenario_lower_bounds, {0: 2.0, 1: 1.0})
        self.assertEqual(
            initial_scenario_lower_bound(tiny_two_scenario_instance(), tiny_two_scenario_instance().scenarios[0]),
            2.0,
        )

    def test_master_can_suppress_solver_output_before_parameter_setup(self) -> None:
        built = build_master(tiny_two_scenario_instance(), name="tiny_benders_quiet", output_flag=0)

        self.assertEqual(built.model.Params.OutputFlag, 0)

    def test_scenario_subproblem_accepts_time_limit(self) -> None:
        instance = tiny_two_scenario_instance()
        y_values = {(1, 0): 1, (1, 1): 0, (2, 0): 1, (2, 1): 0}

        evaluation = evaluate_scenario_subproblem(
            instance,
            instance.scenarios[0],
            y_values,
            time_limit=10.0,
        )

        self.assertEqual(evaluation.status, GRB.OPTIMAL)

    def test_scenario_subproblem_does_not_apply_full_model_vehicle_order_sbc(self) -> None:
        instance = tiny_two_scenario_instance()
        y_values = {(1, 0): 0, (1, 1): 1, (2, 0): 1, (2, 1): 0}

        evaluation = evaluate_scenario_subproblem(
            instance,
            instance.scenarios[1],
            y_values,
            time_limit=10.0,
        )

        self.assertEqual(evaluation.status, GRB.OPTIMAL)
        self.assertAlmostEqual(evaluation.objective, 2.0)

    def test_integer_optimality_cut_matches_candidate_and_relaxes_other_binary_points(self) -> None:
        built = build_master(tiny_two_scenario_instance(), name="tiny_benders_cut")
        y_hat = {
            (1, 0): 1,
            (1, 1): 0,
            (2, 0): 0,
            (2, 1): 1,
        }

        add_integer_optimality_cut(
            built,
            scenario_id=0,
            y_hat=y_hat,
            recourse_cost=8.0,
            lower_bound=2.0,
        )

        self.assertIsNotNone(built.model.getConstrByName("integer_optimality[0,0]"))
        self.assertAlmostEqual(integer_cut_rhs_value(y_hat, y_hat, recourse_cost=8.0, lower_bound=2.0), 8.0)
        other_y = dict(y_hat)
        other_y[(1, 0)] = 0
        self.assertAlmostEqual(integer_cut_rhs_value(other_y, y_hat, recourse_cost=8.0, lower_bound=2.0), 0.0)
        other_y[(1, 1)] = 1
        self.assertAlmostEqual(integer_cut_rhs_value(other_y, y_hat, recourse_cost=8.0, lower_bound=2.0), -8.0)

    def test_branch_and_check_evaluates_every_scenario_for_each_master_incumbent(self) -> None:
        result = solve_benders_branch_and_check(tiny_two_scenario_instance(), name="tiny_benders_branch_check")

        self.assertEqual(result.method, "BD")
        self.assertEqual(result.status, GRB.OPTIMAL)
        self.assertGreaterEqual(len(result.iterations), 1)
        for iteration in result.iterations:
            self.assertEqual(set(iteration.scenario_costs), {0, 1})
            self.assertEqual(set(iteration.lambda_values), {1, 2})
        self.assertEqual(result.iterations[-1].added_cuts, ())
        self.assertGreaterEqual(result.upper_bound, result.lower_bound - 1e-6)
        self.assertIsNotNone(result.best_time_seconds)
        self.assertEqual(set(result.best_y_values or {}), {(1, 0), (1, 1), (2, 0), (2, 1)})
        self.assertEqual(set(result.best_lambda_values or {}), {1, 2})


if __name__ == "__main__":
    unittest.main()
