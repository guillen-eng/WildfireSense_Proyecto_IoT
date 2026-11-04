"""Regression tests for temporal resampling across irregular RESISTO timestamps."""
import unittest
from timegrid import prepare_series, parse_source_time


class TimegridTests(unittest.TestCase):
    def test_observed_interpolated_and_synthetic_extension_are_distinct(self):
        rows = [
            {"source_time": "2024-11-09 10:00:00.000 +0100", "temperature_c": 20.0, "source_sensor": "a"},
            {"source_time": "2024-11-09 10:04:00.000 +0100", "temperature_c": 24.0, "source_sensor": "a"},
            {"source_time": "2024-11-09 12:04:00.000 +0100", "temperature_c": 40.0, "source_sensor": "a"},
            {"source_time": "2024-11-09 12:08:00.000 +0100", "temperature_c": 40.0, "source_sensor": "a"},
        ]
        grid, audit = prepare_series(rows, steps=6, step_seconds=120, max_gap_seconds=300, seed=17)
        self.assertEqual(grid[0]["temperature_origin"], "observed")
        self.assertEqual(grid[1]["temperature_origin"], "interpolated")
        self.assertEqual(grid[1]["temperature_c"], 22.0)
        self.assertEqual(grid[2]["temperature_origin"], "observed")
        self.assertEqual(grid[3]["temperature_origin"], "synthetic_extension")
        self.assertEqual(grid[3]["reference_source_times"], [])
        self.assertLess(abs(grid[3]["temperature_c"] - grid[2]["temperature_c"]), 0.66)
        self.assertEqual(audit["original_source_gap_count_over_max"], 1)
        self.assertEqual(audit["point_origins"], {"observed": 2, "interpolated": 1, "synthetic_extension": 3})

    def test_seed_is_reproducible_and_change_affects_synthetic_only(self):
        rows = [
            {"source_time": "2024-11-09 10:00:00+01:00", "temperature_c": 20.0, "source_sensor": "a"},
            {"source_time": "2024-11-09 10:02:00+01:00", "temperature_c": 21.0, "source_sensor": "a"},
        ]
        a, _ = prepare_series(rows, steps=7, step_seconds=120, max_gap_seconds=300, seed=22)
        b, _ = prepare_series(rows, steps=7, step_seconds=120, max_gap_seconds=300, seed=22)
        c, _ = prepare_series(rows, steps=7, step_seconds=120, max_gap_seconds=300, seed=23)
        self.assertEqual(a, b)
        self.assertEqual(a[:2], c[:2])
        self.assertNotEqual(a[2:], c[2:])

    def test_timestamps_require_explicit_timezone(self):
        with self.assertRaises(ValueError):
            parse_source_time("2024-11-09 12:30:00")
        with self.assertRaises(ValueError):
            parse_source_time("not a date")


if __name__ == "__main__":
    unittest.main()
