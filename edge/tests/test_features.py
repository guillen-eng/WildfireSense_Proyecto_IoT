import unittest
from features import FEATURE_NAMES, RollingFeatures, parse_reading


def sample(seq, node="node_0001", run="test_01", pm25=10.0, pm10=20.0, temperature=25.0, humidity=45.0):
    return {
        "schema_version": 1, "run_id": run, "node_id": node, "seq": seq,
        "type": "reading", "timebase": "simulated",
        "timestamp": f"2026-11-16T12:00:{seq * 10:02d}Z",
        "test_only": True,
        "measurements": {
            "pm25_ug_m3": pm25, "pm10_ug_m3": pm10,
            "air_temperature_c": temperature, "relative_humidity_pct": humidity,
        },
    }


class FeatureTests(unittest.TestCase):
    def test_three_samples_warmup_and_trend(self):
        feat = RollingFeatures(window=6, min_samples=3)
        self.assertIsNone(feat.add(sample(0, pm25=10)))
        self.assertIsNone(feat.add(sample(1, pm25=15)))
        row = feat.add(sample(2, pm25=25, pm10=35, temperature=28, humidity=38))
        self.assertEqual(set(row), set(FEATURE_NAMES))
        self.assertAlmostEqual(row["pm25_mean"], 50 / 3)
        self.assertEqual(row["pm25_delta"], 10.0)
        self.assertEqual(row["pm25_slope_per_min"], 45.0)
        self.assertAlmostEqual(row["pm25_pm10_ratio"], 25 / 35)

    def test_nodes_are_isolated(self):
        f = RollingFeatures()
        for seq in (0, 1, 2):
            f.add(sample(seq, node="a"))
        self.assertIsNone(f.add(sample(0, node="b")))
        self.assertIsNone(f.add(sample(1, node="b")))
        self.assertIsNotNone(f.add(sample(2, node="b")))

    def test_duplicate_out_of_order_and_gaps(self):
        f = RollingFeatures(min_samples=3)
        f.add(sample(0))
        f.add(sample(1))
        self.assertIsNone(f.add(sample(1)))
        f.add(sample(3))
        self.assertEqual(f.out_of_order_or_duplicate, 1)
        self.assertEqual(f.sequence_gaps, 1)

    def test_reject_leakage_and_nonfinite(self):
        bad = sample(0)
        bad["ground_truth"] = True
        with self.assertRaises(ValueError):
            parse_reading(bad)
        bad = sample(0, pm25=float("nan"))
        with self.assertRaises(ValueError):
            parse_reading(bad)
        bad = sample(0)
        bad["schema_version"] = True
        with self.assertRaises(ValueError):
            parse_reading(bad)

    def test_zero_pm10_has_explicit_flag(self):
        f = RollingFeatures()
        for seq in (0, 1):
            f.add(sample(seq, pm25=0, pm10=0))
        row = f.add(sample(2, pm25=0, pm10=0))
        self.assertEqual(row["pm10_is_zero"], 1.0)

    def test_virtual_run_has_independent_history(self):
        f = RollingFeatures()
        for seq in (0, 1, 2):
            f.add(sample(seq, run="A"))
        self.assertIsNone(f.add(sample(0, run="B")))


if __name__ == "__main__":
    unittest.main()
