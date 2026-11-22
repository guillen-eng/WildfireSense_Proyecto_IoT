"""One-factor-at-a-time alarm sensitivity study on held-out simulation seeds.

Does not train, rewrite or promote models, change production thresholds,
or claim generalization to real wildfires. The label is used only for scoring.
Run: python -m lab.threshold_sensitivity --out resultados/threshold_sensitivity
"""

import argparse
import csv
import json
import math
from dataclasses import asdict, replace
from pathlib import Path

from edge.logic import DetectionPolicy, Engine, checked_node
from edge.model import Forest, ROOT
from .episodes import PERIOD, SCENES, make_scene


AXES = {
    "score": ("fire_score", (0.55, 0.65, 0.75)),
    "pm25": ("min_pm25", (12.0, 18.0, 24.0)),
    "fraction": ("min_fine_fraction", (0.25, 0.36, 0.45)),
    "persistence": ("persist_s", (10.0, 30.0, 60.0)),
    "neighbours": ("neighbour_ttl_s", (60.0, 180.0, 300.0)),
    "recovery": ("clear_s", (30.0, 60.0, 120.0)),
}
VALIDATION_SEEDS = tuple(range(301, 307))
RESERVED_TEST_SEEDS = frozenset(range(201, 231))
TRAIN_SEEDS = frozenset(range(101, 125))


def grid(axis="all"):
    """Original V4 policy followed by one-factor-at-a-time alternatives."""
    if axis != "all" and axis not in AXES:
        raise ValueError("Unknown axis")
    base = DetectionPolicy()
    yield "baseline", base
    for name, (field, values) in AXES.items():
        if axis not in ("all", name):
            continue
        for value in values:
            if value == getattr(base, field):
                continue
            yield f"{name}={value:g}", replace(base, **{field: value})


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    weight = pos - low
    return round(ordered[low] * (1 - weight) + ordered[high] * weight, 2)


def evaluate_policy(forest, policy, seeds, scene_source=make_scene):
    """Score alarm events per independent episode, not per individual sample."""
    episodes = []
    for seed in seeds:
        for scene in SCENES:
            stream, _nodes, t0 = scene_source(seed, scene)
            engine = Engine(forest=forest, policy=policy)
            first_fire = first_advisory = None
            pre_onset_high = high_count = advisory_count = 0
            sequences = {}
            for node, t, values, _truth_label in stream:
                node_id = checked_node(node)
                sequences[node_id] = sequences.get(node_id, 0) + 1
                _prediction, events = engine.evaluate(
                    "threshold-study", node_id, "a", sequences[node_id],
                    t, values, period=PERIOD,
                )
                for ev in events:
                    if ev["decision"] == "suspected_fire":
                        high_count += 1
                        if t < t0:
                            pre_onset_high += 1
                        elif first_fire is None:
                            first_fire = t - t0
                    elif ev["decision"] == "environmental_risk":
                        advisory_count += 1
                        if t >= t0 and first_advisory is None:
                            first_advisory = t - t0
            episodes.append(dict(
                seed=seed, scene=scene, is_fire=scene.endswith("_fire"),
                detected=first_fire is not None,
                high_delay_s=round(first_fire, 2) if first_fire is not None else None,
                advisory_delay_s=round(first_advisory, 2) if first_advisory is not None else None,
                pre_ignition_high=pre_onset_high, high_events=high_count,
                advisory_events=advisory_count,
            ))

    fire = [e for e in episodes if e["is_fire"]]
    negatives = [e for e in episodes if not e["is_fire"]]
    delays = [e["high_delay_s"] for e in fire if e["high_delay_s"] is not None]
    result = dict(
        fire_episodes=len(fire), negative_episodes=len(negatives),
        high_detected=len(delays),
        high_missed=len(fire) - len(delays),
        negative_high_episodes=sum(e["high_events"] > 0 for e in negatives),
        negative_advisory_episodes=sum(e["advisory_events"] > 0 for e in negatives),
        pre_ignition_high_episodes=sum(e["pre_ignition_high"] > 0 for e in fire),
        delay_mean_s=round(sum(delays) / len(delays), 2) if delays else None,
        delay_p50_s=percentile(delays, 0.50),
        delay_p95_s=percentile(delays, 0.95),
        detected_by_5m=sum(d <= 300 for d in delays),
        detected_by_15m=sum(d <= 900 for d in delays),
        detected_by_30m=sum(d <= 1800 for d in delays),
        detected_by_60m=sum(d <= 3600 for d in delays),
    )
    return result, episodes


def study(seeds, axis="all", model=None):
    seeds = tuple(seeds)
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Provide distinct nonempty seeds")
    if TRAIN_SEEDS.intersection(seeds) or RESERVED_TEST_SEEDS.intersection(seeds):
        raise ValueError("Training and original held-out test seeds cannot be used for tuning")
    forest = Forest(model)
    summaries = []
    details = []
    for label, policy in grid(axis):
        result, episodes = evaluate_policy(forest, policy, seeds)
        summaries.append(dict(
            config=label, model=forest.version,
            **asdict(policy), **result,
        ))
        details.extend(dict(config=label, **episode) for episode in episodes)
    return summaries, details


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=VALIDATION_SEEDS)
    parser.add_argument("--axis", choices=("all", *AXES), default="all")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "resultados/umbral_sensibilidad")
    args = parser.parse_args()
    summaries, details = study(args.seeds, args.axis, args.model)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "configurations.csv", summaries)
    write_csv(args.out / "episodes.csv", details)
    meta = dict(
        scope="synthetic one-factor-at-a-time sensitivity; NOT field validation",
        model=summaries[0]["model"], seeds=args.seeds, axis=args.axis,
        baseline=summaries[0],
        candidate_count=len(summaries) - 1,
        warning="Do not tune using original held-out seeds 201-230; no automatic model promotion.",
    )
    (args.out / "study.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
