import unittest
from lab.early_detection import analyze


class EarlyDetectionTest(unittest.TestCase):
    def test_respects_deadline_and_fire_episodes(self):
        rows = [
            dict(method="ml",scenario="fast_fire",fire_delay_s="250", alerts_before_onset="0"),
            dict(method="ml",scenario="slow_fire",fire_delay_s="950", alerts_before_onset="0"),
            dict(method="ml",scenario="slow_fire",fire_delay_s="", alerts_before_onset="0"),
            dict(method="ml",scenario="dust",fire_delay_s="", alerts_before_onset="0"),
            dict(method="ml",scenario="normal",fire_delay_s="100", alerts_before_onset="0"),
        ]
        summary = analyze(rows)["ml"]
        self.assertEqual(summary["fire_episodes"], 3)
        self.assertEqual(summary["total_detected"], 2)
        self.assertEqual(summary["horizons_seconds"]["300"]["detected"], 1)
        self.assertEqual(summary["horizons_seconds"]["900"]["detected"], 1)
        self.assertEqual(summary["horizons_seconds"]["1800"]["detected"], 2)
        self.assertEqual(summary["negative_with_suspicion"], 1)


if __name__ == "__main__":
    unittest.main()
