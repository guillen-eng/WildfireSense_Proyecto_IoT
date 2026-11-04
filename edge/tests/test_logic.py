import unittest
from logic import ZScoreDetector, decide_sos


class LogicTests(unittest.TestCase):
    def setUp(self):
        self.detector = ZScoreDetector()

    @staticmethod
    def reading(node_id, value):
        return {
            "node_id": node_id,
            "measurements": {"sensible_heat_flux": value},
        }

    def warm_up(self, node_id="sensor_001"):
        for _ in range(20):
            self.assertIsNone(self.detector.evaluate(self.reading(node_id, 100.0)))

    def test_no_alarm_during_initial_history(self):
        for _ in range(19):
            self.assertIsNone(self.detector.evaluate(self.reading("sensor_001", 100.0)))

    def test_single_spike_not_confirmed(self):
        self.warm_up()
        self.assertIsNone(self.detector.evaluate(self.reading("sensor_001", 150.0)))

    def test_two_consecutive_spikes_trigger_alarm(self):
        self.warm_up()
        self.assertIsNone(self.detector.evaluate(self.reading("sensor_001", 150.0)))
        alarm = self.detector.evaluate(self.reading("sensor_001", 150.0))
        self.assertIsNotNone(alarm)
        self.assertEqual(alarm["type"], "environmental_alert")
        self.assertEqual(alarm["priority"], "high")
        self.assertEqual(alarm["node_id"], "sensor_001")

    def test_normal_reading_resets_consecutive_counter(self):
        self.warm_up()
        self.assertIsNone(self.detector.evaluate(self.reading("sensor_001", 150.0)))
        self.assertIsNone(self.detector.evaluate(self.reading("sensor_001", 100.0)))
        self.assertIsNone(self.detector.evaluate(self.reading("sensor_001", 150.0)))
        self.assertIsNotNone(self.detector.evaluate(self.reading("sensor_001", 150.0)))

    def test_sensors_are_independent(self):
        self.warm_up("sensor_001")
        self.warm_up("sensor_002")
        self.assertIsNone(self.detector.evaluate(self.reading("sensor_001", 150.0)))
        self.assertIsNone(self.detector.evaluate(self.reading("sensor_002", 150.0)))
        self.assertIsNotNone(self.detector.evaluate(self.reading("sensor_001", 150.0)))
        self.assertIsNotNone(self.detector.evaluate(self.reading("sensor_002", 150.0)))

   
    def test_invalid_values_are_ignored(self):
        self.warm_up()

        for bad in (True, "150", None, float("nan"), float("inf")):
            self.assertIsNone(
                self.detector.evaluate(
                    self.reading("sensor_001", bad)
                )
            )

        self.assertIsNone(
            self.detector.evaluate({"node_id": "sensor_001"})
        )


    def test_no_alarm_spam_while_anomaly_persists(self):
        self.warm_up()
        self.assertIsNone(self.detector.evaluate(self.reading("sensor_001", 150.0)))
        self.assertIsNotNone(self.detector.evaluate(self.reading("sensor_001", 150.0)))
        self.assertIsNone(self.detector.evaluate(self.reading("sensor_001", 150.0)))

    def test_sos_is_critical_and_immediate(self):
        alarm = decide_sos({"node_id": "SOS01", "zone": "trail_A"})
        self.assertEqual(alarm["type"], "sos_alert")
        self.assertEqual(alarm["priority"], "critical")


if __name__ == "__main__":
    unittest.main()
