import tempfile
import unittest
from pathlib import Path
import pandas as pd
from edge.features import FEATURE_NAMES
from ml.train_random_forest import train_dataset


class TrainingTests(unittest.TestCase):
    def make_data(self):
        rows = []
        for group in range(8):
            for label in (0, 1):
                for rep in range(8):
                    row = {k: float(label * 15 + rep + group * 0.01) for k in FEATURE_NAMES}
                    row.update(label=label, group_id=f"episode-{group}", split="train" if group < 6 else "test")
                    rows.append(row)
        return pd.DataFrame(rows)

    def test_train_with_disjoint_episode_groups(self):
        with tempfile.TemporaryDirectory() as path:
            folder = Path(path)
            csv = folder / "labeled.csv"
            self.make_data().to_csv(csv, index=False)
            result = train_dataset(csv, folder / "model.joblib", folder / "report.json")
            self.assertTrue((folder / "model.joblib").is_file())
            self.assertTrue((folder / "report.json").is_file())
            self.assertEqual(result["train_groups"], 6)
            self.assertEqual(result["test_groups"], 2)

    def test_reject_group_leakage(self):
        with tempfile.TemporaryDirectory() as path:
            folder = Path(path)
            data = self.make_data()
            data.loc[0, "group_id"] = "episode-6"
            csv = folder / "bad.csv"
            data.to_csv(csv, index=False)
            with self.assertRaisesRegex(ValueError, "disjoint"):
                train_dataset(csv, folder / "model.joblib", folder / "report.json")
