"""Join unlabeled MQTT-like telemetry JSONL with external per-reading truth CSV.

Ground truth NEVER enters MQTT. This join is strictly offline.
"""
import argparse
import csv
import json
from pathlib import Path
from edge.features import FEATURE_NAMES, RollingFeatures

KEY = ("run_id", "node_id", "seq")
TRUTH_FIELDS = KEY + ("label", "group_id", "split")


def build(readings_path, truth_path, output_path, window=6, min_samples=3):
    truth = {}
    with Path(truth_path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not set(TRUTH_FIELDS).issubset(reader.fieldnames or ()):
            raise ValueError(f"Truth CSV must include {TRUTH_FIELDS}")
        for row in reader:
            key = (row["run_id"], row["node_id"], str(int(row["seq"])))
            if key in truth:
                raise ValueError(f"Duplicate truth row for {key}")
            if row["label"] not in ("0", "1") or row["split"] not in ("train", "test") or not row["group_id"]:
                raise ValueError("Invalid truth label/split/group_id")
            truth[key] = row
    extractor = RollingFeatures(window=window, min_samples=min_samples)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    accepted = 0
    with Path(readings_path).open(encoding="utf-8") as fin, output.open("w", newline="", encoding="utf-8") as fout:
        writer = csv.DictWriter(fout, fieldnames=list(KEY) + list(FEATURE_NAMES) + ["label", "group_id", "split"])
        writer.writeheader()
        for number, line in enumerate(fin, 1):
            if not line.strip():
                continue
            message = json.loads(line)
            features = extractor.add(message)
            if features is None:
                continue
            key = (message["run_id"], message["node_id"], str(message["seq"]))
            if key not in truth:
                raise ValueError(f"No external truth for eligible reading {key} at JSONL line {number}")
            meta = truth[key]
            writer.writerow({**dict(zip(KEY, key)), **features, "label": meta["label"],
                             "group_id": meta["group_id"], "split": meta["split"]})
            accepted += 1
    return {"feature_rows": accepted,
            "duplicates_or_out_of_order": extractor.out_of_order_or_duplicate,
            "sequence_gaps": extractor.sequence_gaps}


def main():
    p = argparse.ArgumentParser(description="Prepare causal features with external truth labels")
    p.add_argument("--readings", required=True, help="MQTT-like telemetry JSONL, chronological per node")
    p.add_argument("--truth", required=True, help="External per-reading truth CSV")
    p.add_argument("--output", default="ml/data/labeled_features.csv")
    p.add_argument("--window", type=int, default=6)
    p.add_argument("--min-samples", type=int, default=3)
    args = p.parse_args()
    print(json.dumps(build(args.readings, args.truth, args.output, args.window, args.min_samples), indent=2))


if __name__ == "__main__":
    main()
