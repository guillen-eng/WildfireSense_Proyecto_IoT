"""The deployed model must pass the team's nine scenarios (external to the training generator)."""

import unittest

from edge.model import ROOT
from lab.scenario_gate import DEFAULT_DIR, SCENARIOS, compare, run_all


@unittest.skipUnless(DEFAULT_DIR.exists(), "scenario files not present")
class ScenarioGateTest(unittest.TestCase):
    def test_deployed_model_passes_all_nine(self):
        report = run_all(ROOT / "models/forest.json")
        self.assertEqual(report["total"], len(SCENARIOS))
        self.assertEqual(report["failed"], [], report["results"])

    def test_neighbours_alarm_before_the_front(self):
        report = run_all(ROOT / "models/forest.json")
        for name in ("fuego_lento", "fuego_rapido"):
            row = next(r for r in report["results"] if r["scenario"] == name)
            self.assertTrue(row["checks"]["neighbours_alarm_before_front"], row["front_lead_s"])
            self.assertEqual(set(row["front_lead_s"]), {"N4", "N5", "N6"})

    def test_same_model_is_not_a_regression(self):
        model = ROOT / "models/forest.json"
        self.assertTrue(compare(model, model)["approved"])



class MissingScenariosTest(unittest.TestCase):
    def test_missing_folder_blocks_promotion_unless_allowed(self):
        import os
        from pathlib import Path
        from unittest import mock

        from cloud.retrain import _scenario_check

        with mock.patch("lab.scenario_gate.DEFAULT_DIR", Path("/nonexistent/scenarios")):
            with mock.patch.dict(os.environ, {"ALLOW_MISSING_SCENARIOS": ""}):
                out = _scenario_check("a", "b")
                self.assertFalse(out["approved"])
                self.assertEqual(out["regressions"], ["scenarios_unavailable"])
            with mock.patch.dict(os.environ, {"ALLOW_MISSING_SCENARIOS": "1"}):
                self.assertTrue(_scenario_check("a", "b")["approved"])


if __name__ == "__main__":
    unittest.main()
