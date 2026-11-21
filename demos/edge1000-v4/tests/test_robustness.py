import unittest
from lab.robustness import evaluate, schedule


class RobustnessTests(unittest.TestCase):
    def setUp(self):
        self.examples = [
            {"v": 1, "id": 1, "ts": (1800000000 + i * 10) * 1000,
             "seq": i+1, "kind": "periodic", "values": {"PM2.5": 12.0,
             "PM10": 22.0, "temperature": 23.0, "humidity": 45.0}}
            for i in range(20)
        ]

    def test_deterministic(self):
        a = schedule(self.examples, loss=0.2, duplicates=0.5, jitter_s=40, seed=11)
        b = schedule(self.examples, loss=0.2, duplicates=0.5, jitter_s=40, seed=11)
        self.assertEqual(a, b)

    def test_without_impairment_preserves_samples(self):
        result = evaluate(self.examples, loss=0, duplicates=0, jitter_s=0)
        self.assertEqual(result["accepted_readings"], 20)
        self.assertEqual(result["rejected_order_or_duplicate"], 0)
        self.assertEqual(result["sequence_gaps"], 0)

    def test_duplicates_rejected_by_engine(self):
        result = evaluate(self.examples, duplicates=1, loss=0, jitter_s=0)
        self.assertEqual(result["duplicated"], 20)
        self.assertEqual(result["accepted_readings"], 20)
        self.assertEqual(result["rejected_order_or_duplicate"], 20)

    def test_all_dropped(self):
        result = evaluate(self.examples, loss=1)
        self.assertEqual(result["delivered_messages"], 0)
        self.assertEqual(result["accepted_readings"], 0)
        self.assertEqual(result["dropped"], 20)


if __name__ == "__main__":
    unittest.main()
