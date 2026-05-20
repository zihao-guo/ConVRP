from __future__ import annotations

import unittest
from pathlib import Path

from alv.data import Instance, Scenario
from alv.saa import (
    FullOmegaEvaluation,
    SAA_BC_CONFIG,
    SAA_BD_CONFIG,
    SAAConfig,
    SAAReplicationResult,
    compute_saa_statistics,
    evaluate_first_stage_on_full_omega,
    make_sample_plan,
    sample_instance,
)


def tiny_full_instance() -> Instance:
    return Instance(
        path=Path("tiny__omega4__alpha100.json"),
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
            Scenario(id=0, probability=0.25, demands={1: 1}),
            Scenario(id=1, probability=0.25, demands={2: 1}),
            Scenario(id=2, probability=0.25, demands={1: 1, 2: 1}),
            Scenario(id=3, probability=0.25, demands={1: 1}),
        ),
        distances={(0, 1): 1, (0, 2): 1, (1, 2): 1},
        metadata={"omega": 4, "alpha": 1.0, "epsilon": 0.5},
    )


class SAATests(unittest.TestCase):
    def test_protocol_defaults_match_paper_contract(self) -> None:
        self.assertEqual(SAA_BC_CONFIG.replications, 20)
        self.assertEqual(SAA_BC_CONFIG.sample_size, 5)
        self.assertEqual(SAA_BC_CONFIG.sample_time_limit_seconds, 30 * 60)
        self.assertEqual(SAA_BD_CONFIG.replications, 20)
        self.assertEqual(SAA_BD_CONFIG.sample_size, 15)
        self.assertEqual(SAA_BD_CONFIG.sample_time_limit_seconds, 30 * 60)

    def test_sample_memberships_are_reproducible_and_method_comparable(self) -> None:
        instance = tiny_full_instance()

        left = make_sample_plan(instance, replications=4, sample_size=2, seed=123)
        right = make_sample_plan(instance, replications=4, sample_size=2, seed=123)

        self.assertEqual(left, right)
        self.assertEqual(len(left), 4)
        self.assertTrue(all(len(membership) == 2 for membership in left))

    def test_sample_instance_reweights_probabilities(self) -> None:
        instance = tiny_full_instance()
        sampled = sample_instance(instance, (1, 3))

        self.assertEqual([scenario.id for scenario in sampled.scenarios], [1, 3])
        self.assertEqual({scenario.probability for scenario in sampled.scenarios}, {0.5})
        self.assertEqual(sampled.metadata["sample_membership"], [1, 3])

    def test_evaluate_first_stage_on_full_omega_accounts_costs(self) -> None:
        instance = tiny_full_instance()
        y_values = {(1, 0): 1, (1, 1): 0, (2, 0): 1, (2, 1): 0}

        evaluation = evaluate_first_stage_on_full_omega(instance, y_values)

        self.assertEqual(set(evaluation.scenario_costs), {0, 1, 2, 3})
        self.assertAlmostEqual(evaluation.total_cost, evaluation.consistency_penalty + evaluation.recourse_cost)
        self.assertAlmostEqual(evaluation.recourse_cost, evaluation.travel_cost + evaluation.skipping_cost)
        self.assertEqual(evaluation.total_customer_events, 5)
        self.assertEqual(evaluation.skipped_customer_events, 0)
        self.assertAlmostEqual(evaluation.skipped_customers_percent, 0.0)
        self.assertGreaterEqual(evaluation.total_cost, 0.0)

    def test_full_omega_evaluation_uses_sample_lambda_values_from_pdf_solution(self) -> None:
        instance = tiny_full_instance()
        y_values = {(1, 0): 1, (1, 1): 1, (2, 0): 1, (2, 1): 0}
        lambda_values = {1: 5.0, 2: 0.0}

        evaluation = evaluate_first_stage_on_full_omega(instance, y_values, lambda_values=lambda_values)

        self.assertAlmostEqual(evaluation.consistency_penalty, instance.penalties_consistency[1] * 5.0)

    def test_compute_saa_statistics_matches_paper_formulas(self) -> None:
        instance = tiny_full_instance()
        replications = (
            SAAReplicationResult(
                replication=0,
                sample_membership=(0, 1),
                sample_status=2,
                sample_objective=7.0,
                sample_lower_bound=5.0,
                full_omega_evaluation=FullOmegaEvaluation(
                    total_cost=6.0,
                    consistency_penalty=1.0,
                    recourse_cost=5.0,
                    travel_cost=4.0,
                    skipping_cost=1.0,
                    scenario_costs={0: 3.0, 1: 5.0, 2: 7.0, 3: 5.0},
                    skipped_customer_events=1,
                    total_customer_events=5,
                    skipped_customers_percent=20.0,
                ),
                y_values={(1, 0): 1},
                lambda_values={1: 5.0},
            ),
            SAAReplicationResult(
                replication=1,
                sample_membership=(1, 2),
                sample_status=2,
                sample_objective=9.0,
                sample_lower_bound=6.0,
                full_omega_evaluation=None,
                y_values={(1, 0): 1},
                lambda_values={1: 0.0},
            ),
            SAAReplicationResult(
                replication=2,
                sample_membership=(2, 3),
                sample_status=2,
                sample_objective=8.0,
                sample_lower_bound=7.0,
                full_omega_evaluation=None,
                y_values={(1, 0): 1},
                lambda_values={1: 0.0},
            ),
        )

        stats = compute_saa_statistics(
            instance,
            config=SAAConfig(method="SAA-BC", replications=3, sample_size=2, sample_time_limit_seconds=1800),
            replications=replications,
            best_replication=0,
        )

        self.assertAlmostEqual(stats.sample_lower_bound_mean, 6.0)
        self.assertAlmostEqual(stats.sample_lower_bound_variance, 1.0 / 3.0)
        self.assertAlmostEqual(stats.incumbent_variance, 2.0 / 3.0)
        self.assertAlmostEqual(stats.saa_gap, 0.0)
        self.assertAlmostEqual(stats.saa_gap_variance, 1.0)
        self.assertAlmostEqual(stats.opt_gap_percent, 0.0)
        self.assertAlmostEqual(stats.sample_gap_percent, (200.0 / 7.0 + 100.0 / 3.0 + 12.5) / 3.0)


if __name__ == "__main__":
    unittest.main()
