"""Pruebas unitarias independientes para el nuevo comparador CUSUM."""
import unittest
from cusum import CUSUMDetector


class CUSUMTests(unittest.TestCase):
    def setUp(self):
        self.detector = CUSUMDetector()

    @staticmethod
    def reading(node, value):
        return {"node_id": node, "measurements": {"air_temperature_c": value}}

    def warmup(self, node="A", value=20.0):
        for _ in range(20):
            self.assertIsNone(self.detector.evaluate(self.reading(node, value)))

    def test_no_alarm_during_warmup(self):
        self.warmup()
        self.assertAlmostEqual(self.detector.baseline["A"], 20.0)

    def test_gradual_small_deviations_accumulate(self):
        self.warmup()
        # 2 grados sobre la referencia producen 1.5 puntos por lectura.
        for _ in range(5):
            self.assertIsNone(self.detector.evaluate(self.reading("A", 22.0)))
        alert = self.detector.evaluate(self.reading("A", 22.0))
        self.assertIsNotNone(alert)
        self.assertEqual(alert["detector"], "cusum_experimental")
        self.assertEqual(alert["node_id"], "A")

    def test_no_alert_with_stable_baseline(self):
        self.warmup()
        for _ in range(100):
            self.assertIsNone(self.detector.evaluate(self.reading("A", 20.0)))

    def test_sensors_have_independent_state(self):
        self.warmup("A")
        self.warmup("B")
        for _ in range(5):
            self.detector.evaluate(self.reading("A", 22.0))
        self.assertIsNotNone(self.detector.evaluate(self.reading("A", 22.0)))
        self.assertIsNone(self.detector.evaluate(self.reading("B", 20.0)))

    def test_no_repeat_alert(self):
        self.warmup()
        for i in range(10):
            alarm = self.detector.evaluate(self.reading("A", 22.0))
            if i == 5:
                self.assertIsNotNone(alarm)
            else:
                self.assertIsNone(alarm)

    def test_invalid_readings_ignored(self):
        self.warmup()
        for value in (None, "30", True, float("nan"), float("inf")):
            self.assertIsNone(self.detector.evaluate(self.reading("A", value)))
        self.assertEqual(self.detector.scores["A"], 0.0)


if __name__ == "__main__":
    unittest.main()
