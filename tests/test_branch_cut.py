from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from gurobipy import GRB

from alv.branch_cut import (
    build_primal_heuristic_solution,
    branch_and_cut_callback,
    solve_branch_and_cut,
    violated_fractional_sec_sets,
)
from alv.data import Instance, Scenario
from alv.model import build_extensive_form


def tiny_sec_instance() -> Instance:
    return Instance(
        path=Path("tiny_sec__omega1__alpha100.json"),
        set_name="A",
        name="tiny_sec",
        capacity=3,
        depot=0,
        customers=(1, 2, 3),
        D=1,
        vehicles=(0,),
        penalties_skip={1: 100.0, 2: 100.0, 3: 100.0},
        penalties_consistency={1: 0.2, 2: 0.2, 3: 0.2},
        coordinates=((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)),
        scenarios=(Scenario(id=0, probability=1.0, demands={1: 1, 2: 1, 3: 1}),),
        distances={(0, 1): 1, (0, 2): 1, (0, 3): 1, (1, 2): 1, (1, 3): 1, (2, 3): 1},
        metadata={"omega": 1, "alpha": 1.0, "epsilon": 0.5},
    )


class FakeCallbackModel:
    def __init__(self, x_solution, z_solution):
        self._solutions = []
        self._x_solution = x_solution
        self._z_solution = z_solution
        self.lazy_constraints = []

    def cbGetSolution(self, variables):
        self._solutions.append(variables)
        if variables is self._alv_built.x:
            return self._x_solution
        if variables is self._alv_built.z:
            return self._z_solution
        if variables is self._alv_built.y:
            return {key: 1.0 for key in variables}
        if variables is self._alv_built.s:
            return {key: 1.0 for key in variables}
        raise AssertionError("callback requested an unexpected variable container")

    def cbLazy(self, constraint):
        self.lazy_constraints.append(constraint)

    def cbGet(self, what):
        if what == GRB.Callback.MIPSOL_OBJ:
            return 1.0
        if what == GRB.Callback.RUNTIME:
            return 0.0
        raise AssertionError(f"unexpected cbGet query {what}")

    def cbSetSolution(self, variables, values):
        pass


class BranchCutTests(unittest.TestCase):
    def test_callback_adds_sec_for_integer_incumbent_subtour(self) -> None:
        built = build_extensive_form(tiny_sec_instance(), name="tiny_sec_callback", lazy_constraints=True)
        built.model.Params.OutputFlag = 0
        x_solution = {key: 0.0 for key in built.x}
        z_solution = {key: 0.0 for key in built.z}
        for edge in [(1, 2), (1, 3), (2, 3)]:
            x_solution[edge[0], edge[1], 0, 0] = 1.0
        for customer in [1, 2, 3]:
            z_solution[customer, 0, 0] = 1.0

        fake_model = FakeCallbackModel(x_solution, z_solution)
        fake_model._alv_built = built
        fake_model._alv_enable_primal_heuristic = False

        branch_and_cut_callback(fake_model, GRB.Callback.MIPSOL)

        self.assertEqual(fake_model._solutions, [built.x, built.z])
        self.assertEqual(len(fake_model.lazy_constraints), 1)

    def test_primal_heuristic_is_invoked_for_every_integer_solution_even_repeated_y(self) -> None:
        built = build_extensive_form(tiny_sec_instance(), name="tiny_repeated_y_heuristic", lazy_constraints=True)
        x_solution = {key: 0.0 for key in built.x}
        z_solution = {key: 0.0 for key in built.z}
        fake_model = FakeCallbackModel(x_solution, z_solution)
        fake_model._alv_built = built
        fake_model._alv_enable_primal_heuristic = True
        fake_model._alv_primal_heuristic_attempts = 0
        fake_model._alv_primal_heuristic_solutions = 0
        fake_model._alv_time_limit = None
        fake_model._alv_best_incumbent_obj = float("inf")
        fake_model._alv_best_incumbent_time = None

        with patch("alv.branch_cut.build_primal_heuristic_solution", return_value=None):
            branch_and_cut_callback(fake_model, GRB.Callback.MIPSOL)
            branch_and_cut_callback(fake_model, GRB.Callback.MIPSOL)

        self.assertEqual(fake_model._alv_primal_heuristic_attempts, 2)

    def test_fractional_min_cut_separator_finds_root_sec_violation(self) -> None:
        built = build_extensive_form(tiny_sec_instance(), name="tiny_fractional_cut", lazy_constraints=True)
        x_solution = {key: 0.0 for key in built.x}
        z_solution = {key: 0.0 for key in built.z}
        z_solution[1, 0, 0] = 1.0
        z_solution[2, 0, 0] = 0.8
        z_solution[3, 0, 0] = 0.8
        x_solution[0, 1, 0, 0] = 2.0
        x_solution[1, 2, 0, 0] = 0.2
        x_solution[1, 3, 0, 0] = 0.2
        x_solution[2, 3, 0, 0] = 1.0

        cuts = violated_fractional_sec_sets(built, x_solution, z_solution, vehicle=0, scenario=0)

        self.assertIn(frozenset({2, 3}), cuts)

    def test_primal_heuristic_solves_every_scenario_for_fixed_y(self) -> None:
        built = build_extensive_form(tiny_sec_instance(), name="tiny_primal_heuristic", lazy_constraints=True)
        y_values = {(customer, 0): 1 for customer in tiny_sec_instance().customers}
        s_values = {0: 1}

        heuristic = build_primal_heuristic_solution(built, y_values, s_values, time_limit=10.0)

        self.assertIsNotNone(heuristic)
        assert heuristic is not None
        self.assertEqual(set(heuristic.scenario_costs), {0})
        self.assertGreaterEqual(heuristic.total_cost, 0.0)
        self.assertTrue(all(variable in heuristic.variable_values for variable in built.y.values()))
        self.assertTrue(all(variable in heuristic.variable_values for variable in built.z.values()))

    def test_solve_wrapper_enables_lazy_constraints_and_solves_tiny_instance(self) -> None:
        built = solve_branch_and_cut(tiny_sec_instance(), name="tiny_branch_cut", output=False)

        self.assertEqual(built.model.Params.LazyConstraints, 1)
        self.assertEqual(built.model.Params.PreCrush, 1)
        self.assertGreaterEqual(built.model._alv_primal_heuristic_attempts, 1)
        self.assertIsNotNone(built.model._alv_best_incumbent_time)
        self.assertEqual(built.model.Status, GRB.OPTIMAL)
        self.assertGreaterEqual(built.model.SolCount, 1)


if __name__ == "__main__":
    unittest.main()
