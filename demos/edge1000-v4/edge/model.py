"""Portable JSON export. No pickle, native binaries or network for inference."""

import json
from pathlib import Path
from .features import NAMES

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ("direct_sun", "dust", "fast_fire", "fog", "normal", "slow_fire")


class Forest:
    def __init__(self, path=None):
        data = json.loads(Path(path or ROOT / "models/forest.json").read_text())
        if data["features"] != list(NAMES) or data["classes"] != list(CLASSES):
            raise ValueError("Model incompatible with this feature contract")
        self.trees = data["trees"]
        self.version = data["version"]

    def predict(self, x):
        scores = [0.0] * len(CLASSES)
        for tree in self.trees:
            node = tree[0]
            while len(node) == 4:
                f, threshold, left, right = node
                node = tree[left if x[f] <= threshold else right]
            for i, score in enumerate(node):
                scores[i] += score
        k = max(range(len(scores)), key=scores.__getitem__)
        return CLASSES[k], (scores[2] + scores[5]) / len(self.trees)
