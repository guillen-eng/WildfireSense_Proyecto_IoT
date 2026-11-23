"""Pre-registered synthetic study for isolated-node escalation, OPTION B.

Compare an OFF baseline with gated escalation on VALIDATION seeds only.
Do not select on previous TEST seeds (201-230) or stress seeds (401-406).
Generate CSV for manual review; never activate the gateway or promote weights.

Usage:
  python -m lab.isolated_policy_study --out resultados/isolated_policy_dev
"""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from edge.logic import DetectionPolicy
from edge.model import Forest, ROOT
from .episodes import make_scene
from .ood_stress import transform
from .threshold_sensitivity import evaluate_policy, write_csv


DEV_SEEDS = tuple(range(301, 307))
TRAIN = frozenset(range(101, 125))
LEGACY_TEST = frozenset(range(201, 231))
OLD_STRESS = frozenset(range(401, 407))


def isolated_source(mode):
    """One true emitter, all adjacent nodes offline; no invented confirmations."""
    if mode not in ("regular", "high_background"):
        raise ValueError("unsupported dev scene")

    def source(seed, scene):
        original, nodes, t0 = make_scene(seed, scene)
        target = nodes[0]

        def stream():
            for node, t, values, label in original:
                if node == target:
                    yield node, t, transform(values, mode if mode != "regular" else "baseline"), label

        return stream(), (target,), t0
    return source


def policies():
    yield "off_baseline", DetectionPolicy()
    # Pre-specified engineering search region; score and rise refer to
    # uncalibrated model output and causal filtered PM fast-minus-slow.
    # Phase 2 hypothesis, proposed AFTER Phase 1 exposed high-background
    # false alarms: require a concurrent temperature trend (fast minus slow).
    # Thresholds remain provisional until fresh, sealed evaluation.
    for seconds in (120, 180):
        for pmrise in (4.0, 8.0):
            for temp_rise in (0.0, 0.25, 0.5, 1.0):
                label = f"B_p{seconds}_s0.80_d{pmrise:g}_t{temp_rise:g}"
                yield label, replace(
                    DetectionPolicy(), isolated_enabled=True,
                    isolated_persist_s=seconds,
                    isolated_min_fire_score=0.80,
                    isolated_min_pm25_rise=pmrise,
                    isolated_min_temperature_rise=temp_rise,
                )


def study(seeds, forest=None):
    seeds = tuple(seeds)
    if (not seeds or len(seeds) != len(set(seeds))
            or (set(seeds) & (TRAIN | LEGACY_TEST | OLD_STRESS))
            or any(s < 301 for s in seeds)):
        raise ValueError("Use unique development-only seeds, excluding training/test/stress")
    model = Forest(forest)
    rows, episodes = [], []
    for label, policy in policies():
        for mode in ("regular", "high_background"):
            metrics, items = evaluate_policy(
                model, policy, seeds, scene_source=isolated_source(mode))
            rows.append(dict(
                candidate=label, mode=mode, model=model.version,
                isolated_enabled=policy.isolated_enabled,
                persist_s=policy.isolated_persist_s,
                score=policy.isolated_min_fire_score,
                rise=policy.isolated_min_pm25_rise,
                temperature_rise=policy.isolated_min_temperature_rise,
                **metrics,
            ))
            episodes.extend(dict(candidate=label, mode=mode, **item)
                            for item in items)
    return rows, episodes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", nargs="+", type=int, default=DEV_SEEDS)
    p.add_argument("--model", type=Path)
    p.add_argument("--out", type=Path, default=ROOT / "resultados/isolated_policy_dev")
    a = p.parse_args()
    summary, episodes = study(a.seeds, a.model)
    a.out.mkdir(parents=True, exist_ok=True)
    write_csv(a.out / "candidates.csv", summary)
    write_csv(a.out / "episodes.csv", episodes)
    reference = [x for x in summary if x["candidate"] == "off_baseline"]
    metadata = dict(
        model=summary[0]["model"], dev_seeds=a.seeds,
        modes=["regular", "high_background"],
        baseline=reference,
        candidate_count=len({x["candidate"] for x in summary}) - 1,
        decision="NOT SELECTED; review negative alarms, pre-onset alerts, latency and recall manually.",
        caveats=[
            "Same synthetic generator family; not an external field validation",
            "Very high global particulate background is an adversarial negative control",
            "Only genuine unconfirmed alerts count in isolated_detected",
            "Do not change production threshold without another new, sealed evaluation",
        ],
    )
    (a.out / "study.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    print("candidate,mode,detected,negative_false,pre_onset,by_15m,delay_p95")
    for row in summary:
        print(",".join(str(row[k]) for k in (
            "candidate", "mode", "isolated_detected", "isolated_false_episodes",
            "isolated_pre_ignition_episodes", "isolated_detected_by_15m",
            "isolated_delay_p95_s",
        )))


if __name__ == "__main__":
    main()
