"""Train offline; holdout seeds never enter sampling, fit or model selection."""

import hashlib
import json
import random
from pathlib import Path
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from edge.features import Filters, NAMES
from edge.model import CLASSES, Forest, ROOT
from .episodes import make_scene, SCENES

TRAIN = tuple(range(101, 125))
TEST = tuple(range(201, 231))


def reviewed_history(path):
    """One labelled observation per line. Groups are assigned to training explicitly."""
    from edge.contract import parse_reading

    histories = {}
    streams = {}
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        group = row["group"]
        if (
            not isinstance(group, str)
            or not group.startswith("reviewed-train-")
            or row["class"] not in CLASSES
        ):
            raise ValueError("Expected a reviewed-train-* group and known class")
        msg = row["message"]
        run, node, seq, timestamp, values = parse_reading(msg)
        if run in streams and streams[run] != group:
            raise ValueError("One run cannot belong to two groups")
        streams[run] = group
        key = (group, run, node, msg.get("boot_id", "default"))
        feature, last = histories.get(key, (Filters(), -1))
        if seq <= last:
            raise ValueError("Duplicate or out of order in reviewed data")
        histories[key] = feature, seq
        yield feature.update(timestamp.timestamp(), values), row["class"]


def train(output, extra=None):
    x, y = [], []
    sampler = random.Random(81)
    for seed in TRAIN:
        groups = {c: [] for c in CLASSES}
        for scene in SCENES:
            rows, nodes, _ = make_scene(seed, scene)
            filters = {n: Filters() for n in nodes}
            for n, t, v, label in rows:
                groups[label].append(filters[n].update(t, v))
        for label, items in groups.items():
            chosen = sampler.sample(items, min(1100, len(items)))
            x.extend(chosen)
            y.extend([label] * len(chosen))
    if extra:
        for sample, label in reviewed_history(extra):
            x.append(sample)
            y.append(label)
    model = RandomForestClassifier(
        n_estimators=19,
        max_depth=8,
        min_samples_leaf=14,
        random_state=118,
        n_jobs=1,
        class_weight="balanced",
    )
    model.fit(x, y)
    assert tuple(model.classes_) == CLASSES
    trees = []
    for estimator in model.estimators_:
        t = estimator.tree_
        nodes = []
        for i in range(t.node_count):
            if t.children_left[i] != -1:
                nodes.append(
                    [
                        int(t.feature[i]),
                        float(t.threshold[i]),
                        int(t.children_left[i]),
                        int(t.children_right[i]),
                    ]
                )
            else:
                weights = t.value[i, 0]
                nodes.append((weights / weights.sum()).tolist())
        trees.append(nodes)
    payload = dict(
        features=NAMES,
        classes=CLASSES,
        trees=trees,
        training_rows=len(x),
        train_seeds=TRAIN,
    )
    if extra:
        payload["reviewed_data_sha256"] = hashlib.sha256(extra.read_bytes()).hexdigest()
    raw = json.dumps(payload, separators=(",", ":")).encode()
    payload["version"] = "rf-" + hashlib.sha256(raw).hexdigest()[:12]
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    portable = Forest(tmp)
    sample = np.asarray(x[::43], dtype=np.float32)
    expected = model.predict_proba(sample)
    for row, scores in zip(sample, expected):
        cls, p = portable.predict(row.tolist())
        assert (
            cls == CLASSES[int(scores.argmax())]
            and abs(p - scores[2] - scores[5]) < 1e-7
        )
    tmp.replace(output)
    print(payload["version"], len(x), output.stat().st_size, "bytes; export parity OK")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=ROOT / "models/forest.json")
    ap.add_argument(
        "--extra", type=Path, help="JSONL de histórico etiquetado y revisado"
    )
    args = ap.parse_args()
    train(args.output, args.extra)
