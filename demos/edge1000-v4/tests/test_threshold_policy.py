"""Guardrails for experimental threshold studies; production V4 defaults stay fixed."""

import math
import unittest

from edge.logic import DetectionPolicy, Engine
from lab.threshold_sensitivity import grid, percentile, study


class ConstantForest:
    version = "test-forest"

    def __init__(self, score=0.70):
        self.score = score

    def predict(self, x):
        return "slow_fire", self.score


def run_constant(nodes=("node_0001", "node_0002"), policy=None):
    engine = Engine(forest=ConstantForest(), policy=policy)
    events = []
    for sec in range(0, 51, 10):
        for node in nodes:
            _prediction, produced = engine.evaluate(
                "policy-test", node, "boot", sec // 10 + 1,
                float(sec), (40., 60., 25., 50.), period=10,
            )
            events.extend(produced)
    return [e["decision"] for e in events]


class DetectionPolicyTests(unittest.TestCase):
    def test_baseline_defaults_are_the_existing_v4_values(self):
        self.assertEqual(
            DetectionPolicy(),
            DetectionPolicy(0.65, 18.0, 0.36, 30, 180, 60),
        )
        self.assertEqual(run_constant(), run_constant(policy=DetectionPolicy()))

    def test_default_requires_persistence_and_a_healthy_neighbour(self):
        single = run_constant(nodes=("node_0001",))
        together = run_constant()
        self.assertEqual(single.count("environmental_risk"), 1)
        self.assertNotIn("suspected_fire", single)
        self.assertEqual(together.count("environmental_risk"), 2)
        self.assertGreaterEqual(together.count("suspected_fire"), 1)

    def test_higher_score_cutoff_suppresses_alarms_without_model_change(self):
        events = run_constant(policy=DetectionPolicy(fire_score=0.75))
        self.assertNotIn("environmental_risk", events)
        self.assertNotIn("suspected_fire", events)

    def test_longer_persistence_suppresses_short_episode(self):
        events = run_constant(policy=DetectionPolicy(persist_s=60))
        self.assertNotIn("environmental_risk", events)

    def test_thresholds_are_finite_and_within_allowed_ranges(self):
        for policy in (
            lambda: DetectionPolicy(fire_score=math.nan),
            lambda: DetectionPolicy(fire_score=1.01),
            lambda: DetectionPolicy(min_pm25=-1),
            lambda: DetectionPolicy(min_fine_fraction=-0.01),
            lambda: DetectionPolicy(persist_s=-10),
            lambda: DetectionPolicy(neighbour_ttl_s=math.inf),
        ):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                policy()

    def test_one_at_a_time_study_and_percentile_interpolation(self):
        configs = list(grid("score"))
        self.assertEqual([name for name, _ in configs],
                         ["baseline", "score=0.55", "score=0.75"])
        self.assertEqual(percentile([10], 0.95), 10)
        self.assertEqual(percentile([10, 20, 30], 0.5), 20)
        self.assertEqual(percentile([10, 20], 0.5), 15)
        self.assertIsNone(percentile([], 0.95))

    def test_training_or_original_test_seeds_rejected_for_threshold_tuning(self):
        for bad in ([101], [201], [301, 301], []):
            with self.subTest(seeds=bad), self.assertRaises(ValueError):
                study(bad, axis="score")


if __name__ == "__main__":
    unittest.main()
