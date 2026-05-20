from __future__ import annotations

import unittest
from pathlib import Path

from alv.data import Instance, Scenario
from alv.model import build_extensive_form, objective_accounting


def tiny_instance() -> Instance:
    return Instance(
        path=Path("tiny__omega1__alpha100.json"),
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
        scenarios=(Scenario(id=0, probability=1.0, demands={1: 1, 2: 1}),),
        distances={(0, 1): 1, (0, 2): 1, (1, 2): 1},
        metadata={"omega": 1, "alpha": 1.0, "epsilon": 0.5},
    )


def tiny_sparse_instance() -> Instance:
    return Instance(
        path=Path("tiny_sparse__omega2__alpha50.json"),
        set_name="A",
        name="tiny_sparse",
        capacity=2,
        depot=0,
        customers=(1, 2),
        D=1,
        vehicles=(0, 1),
        penalties_skip={1: 6.0, 2: 6.0},
        penalties_consistency={1: 0.2, 2: 0.2},
        coordinates=((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)),
        scenarios=(
            Scenario(id=0, probability=0.5, demands={1: 1}),
            Scenario(id=1, probability=0.5, demands={2: 1}),
        ),
        distances={(0, 1): 1, (0, 2): 1, (1, 2): 1},
        metadata={"omega": 2, "alpha": 0.5, "epsilon": 0.5},
    )


class ModelCoreTests(unittest.TestCase):
    def test_builds_expected_variable_blocks(self) -> None:
        built = build_extensive_form(tiny_instance(), name="tiny_model_core")

        self.assertEqual(len(built.y), 4)
        self.assertEqual(len(built.s), 2)
        self.assertEqual(len(built.lam), 2)
        self.assertEqual(len(built.z), 4)
        self.assertEqual(len(built.x), 6)
        self.assertEqual(built.model.Params.Threads, 1)
        self.assertAlmostEqual(built.model.Params.MIPGap, 1e-5)

    def test_can_suppress_solver_output_before_parameter_setup(self) -> None:
        built = build_extensive_form(tiny_instance(), name="tiny_model_core_quiet", output=False)

        self.assertEqual(built.model.Params.OutputFlag, 0)

    def test_second_stage_variables_exist_only_for_present_customers_and_edges(self) -> None:
        built = build_extensive_form(tiny_sparse_instance(), name="tiny_sparse_model_core")

        self.assertIn((1, 0, 0), built.z)
        self.assertNotIn((2, 0, 0), built.z)
        self.assertIn((2, 0, 1), built.z)
        self.assertNotIn((1, 0, 1), built.z)
        self.assertIn((0, 1, 0, 0), built.x)
        self.assertNotIn((0, 2, 0, 0), built.x)
        self.assertIn((0, 2, 0, 1), built.x)
        self.assertNotIn((0, 1, 0, 1), built.x)

    def test_solves_tiny_instance_and_accounts_objective(self) -> None:
        built = build_extensive_form(tiny_instance(), name="tiny_model_core_solve")
        built.model.Params.OutputFlag = 0
        built.model.optimize()

        self.assertEqual(built.model.Status, 2)
        accounting = objective_accounting(built)
        self.assertAlmostEqual(accounting["total_cost"], built.model.ObjVal, places=6)
        self.assertAlmostEqual(
            accounting["total_cost"],
            accounting["travel_cost"]
            + accounting["consistency_penalty"]
            + accounting["skipping_cost"],
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
