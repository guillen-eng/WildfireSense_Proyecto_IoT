import csv
import json
import tempfile
import unittest
from pathlib import Path
from ml.build_features import build


def sample(seq):
    return {
        "schema_version": 1, "run_id": "test_01", "node_id": "node_0001", "seq": seq,
        "type": "reading", "timebase": "simulated",
        "timestamp": f"2026-11-16T12:00:{seq * 10:02d}Z",
        "measurements": {
            "pm25_ug_m3": 10, "pm10_ug_m3": 20,
            "air_temperature_c": 25, "relative_humidity_pct": 45,
        },
    }


class BuildTests(unittest.TestCase):
    def test_requires_external_ground_truth(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            readings, truth, out = folder / "readings.jsonl", folder / "truth.csv", folder / "features.csv"
            readings.write_text("\n".join(json.dumps(sample(i)) for i in range(4)) + "\n")
            with truth.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["run_id", "node_id", "seq", "label", "group_id", "split"])
                w.writeheader()
                for seq in range(4):
                    w.writerow({"run_id": "test_01", "node_id": "node_0001", "seq": seq,
                                "label": int(seq >= 2), "group_id": "episode_a", "split": "train"})
            metrics = build(readings, truth, out)
            self.assertEqual(metrics["feature_rows"], 2)
            with out.open(newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f))), 2)

    def test_missing_truth_fails(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            readings, truth = folder / "readings.jsonl", folder / "truth.csv"
            readings.write_text("\n".join(json.dumps(sample(i)) for i in range(3)) + "\n")
            truth.write_text("run_id,node_id,seq,label,group_id,split\n")
            with self.assertRaisesRegex(ValueError, "No external truth"):
                build(readings, truth, folder / "out.csv")
