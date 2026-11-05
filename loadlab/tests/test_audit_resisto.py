"""Regression tests for RESISTO descriptive audit."""
import csv
import tempfile
import unittest
from pathlib import Path
from audit_resisto import audit_csv


class AuditTests(unittest.TestCase):
    def test_replay_contains_irregular_times_and_little_humidity(self):
        local = Path(__file__).resolve().parents[2] / "scenario/data/resisto_sample.csv"
        path = local if local.exists() else Path("/app/historical-data/resisto_sample.csv")
        result = audit_csv(path)
        self.assertEqual(result["rows"], 360)
        self.assertEqual(result["valid_humidity_rows"], 16)
        self.assertEqual(result["unique_sensor_site_pairs"], 5)
        self.assertGreater(result["temporal"]["source_gaps_over_limit"], 0)
        self.assertLess(result["temporal"]["longest_contiguous_span_minutes"], 36)
        self.assertIsNone(result["status_counts"])

    def test_original_device_flag_is_not_real_fire_ground_truth(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "resisto_original.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["time", "sensor_ns_id", "site_id",
                                   "temperature_c", "humidity_percent", "fire_alert_status"])
                writer.writeheader()
                writer.writerow({"time": "2024-05-01 10:00:00+02:00", "sensor_ns_id": "a",
                                 "site_id": "x", "temperature_c": "22",
                                 "humidity_percent": "-1", "fire_alert_status": "0"})
                writer.writerow({"time": "2024-05-01 10:02:00+02:00", "sensor_ns_id": "a",
                                 "site_id": "x", "temperature_c": "23",
                                 "humidity_percent": "40", "fire_alert_status": "2"})
            result = audit_csv(path)
            self.assertEqual(result["status_counts"], {"0": 1, "2": 1})
            self.assertIn("not verified wildfire", result["device_status_note"])
            self.assertEqual(result["valid_humidity_rows"], 1)
            self.assertEqual(result["temporal"]["source_gaps_positive"], 0)


if __name__ == "__main__":
    unittest.main()
