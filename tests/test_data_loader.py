from __future__ import annotations

import unittest
from pathlib import Path

from alv.data import load_all_instances, load_instance, validate_dataset


DATA_ROOT = Path("/mnt/e/currentWORK/AAA_Project/P3/data")


class DataLoaderTests(unittest.TestCase):
    def test_load_single_canonical_instance_fields(self) -> None:
        path = DATA_ROOT / "processed/omega100/A/convrp_10_test_1__omega100__alpha20.json"

        instance = load_instance(path)

        self.assertEqual(instance.set_name, "A")
        self.assertEqual(instance.name, "convrp_10_test_1")
        self.assertEqual(instance.omega, 100)
        self.assertEqual(instance.alpha, 0.2)
        self.assertEqual(instance.capacity, 15)
        self.assertEqual(instance.depot, 0)
        self.assertEqual(instance.D, 1)
        self.assertEqual(instance.customers, tuple(range(1, 11)))
        self.assertEqual(len(instance.scenarios), 100)
        self.assertEqual({scenario.probability for scenario in instance.scenarios}, {0.01})
        self.assertEqual(instance.vehicles, (0, 1))
        self.assertEqual(instance.penalties_skip[1], 78.0)
        self.assertEqual(instance.penalties_consistency[1], 2.6)
        self.assertEqual(instance.distances[(0, 1)], 13)


    def test_validate_dataset_expected_counts_and_parameters(self) -> None:
        instances = load_all_instances(DATA_ROOT)
        validation = validate_dataset(instances)

        self.assertIs(validation["valid"], True)
        self.assertEqual(validation["total_instances"], 138)
        self.assertEqual(validation["base_instance_counts"], {"A": 10, "B": 7, "D": 6})
        self.assertEqual(validation["records_by_set"], {"A": 60, "B": 42, "D": 36})
        self.assertEqual(validation["omegas"], [100, 500])
        self.assertEqual(validation["alphas"], [0.2, 0.5, 0.8])
        self.assertEqual(validation["errors"], [])


if __name__ == "__main__":
    unittest.main()
