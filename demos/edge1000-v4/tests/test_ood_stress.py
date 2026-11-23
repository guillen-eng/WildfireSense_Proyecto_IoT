import unittest

from lab.ood_stress import MODES, source_for, transform
from lab.threshold_sensitivity import evaluate_policy
from edge.logic import DetectionPolicy
from edge.model import Forest


class ShiftProbeTests(unittest.TestCase):
    def test_transform_retains_physical_measurement_bounds(self):
        raw = (8., 15., 23., 64.)
        for name in MODES:
            with self.subTest(mode=name):
                pm25, pm10, t, rh = transform(raw, name)
                self.assertGreaterEqual(pm25, 0)
                self.assertGreaterEqual(pm10, pm25)
                self.assertTrue(0 <= rh <= 100)
                self.assertEqual(t, 23.)
        self.assertEqual(transform(raw, "baseline"), raw)
        self.assertGreaterEqual(transform(raw, "coarse_mixture")[1], 3.5 * raw[0])
        self.assertEqual(transform(raw, "pm25_underread")[0], 5.6)

    def test_single_node_source_drops_all_other_nodes(self):
        stream, _nodes, _t0 = source_for("single_node")(401, "slow_fire")
        unique = {n for n, *_ in stream}
        self.assertEqual(len(unique), 1)

    def test_isolated_stress_cannot_claim_neighbour_corrob(self):
        model = Forest()
        result, _episodes = evaluate_policy(
            model, DetectionPolicy(), (401,),
            scene_source=source_for("single_node")
        )
        self.assertEqual(result["high_detected"], 0)
        self.assertEqual(result["negative_high_episodes"], 0)


if __name__ == "__main__":
    unittest.main()
