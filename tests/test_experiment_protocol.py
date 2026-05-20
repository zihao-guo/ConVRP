from __future__ import annotations

import unittest

from scripts.submit_full import time_limit_for_method


class ExperimentProtocolTests(unittest.TestCase):
    def test_paper_time_limits_are_locked(self) -> None:
        self.assertEqual(time_limit_for_method("BC"), 10 * 60 * 60)
        self.assertEqual(time_limit_for_method("BD"), 10 * 60 * 60)
        self.assertEqual(time_limit_for_method("SAA-BC"), 30 * 60)
        self.assertEqual(time_limit_for_method("SAA-BD"), 30 * 60)


if __name__ == "__main__":
    unittest.main()
