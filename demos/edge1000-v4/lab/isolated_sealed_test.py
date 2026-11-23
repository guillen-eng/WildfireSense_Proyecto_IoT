"""One-time, fixed-candidate synthetic verification for isolated-node policy B.

Candidate and seeds PRE-REGISTERED in docs/POLITICA_B_NODO_AISLADO.md.
No training or threshold selection on these seeds; a failed gate means REJECT.
This is NOT validation against external wildfire measurements.

Usage: python -m lab.isolated_sealed_test --out resultados/isolated_sealed
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

SEALED_SEEDS = tuple(range(601, 613))
MODES = (
    "isolated_regular", "isolated_high_background",
    "isolated_coarse_mixture", "isolated_high_humidity",
    "isolated_pm25_underread", "five_nodes",
)
# Fixed BEFORE looking at these sealed episode results. No grid search here.
CANDIDATE = replace(
    DetectionPolicy(),
    isolated_enabled=True,
    isolated_persist_s=120.0,
    isolated_min_fire_score=0.80,
    isolated_min_pm25_rise=8.0,
    isolated_min_temperature_rise=0.0,
)


def scenario(mode):
    if mode not in MODES:
        raise ValueError("Unknown scenario")

    def source(seed, scene):
        stream, nodes, t0 = make_scene(seed, scene)
        if mode == "five_nodes":
            return stream, nodes, t0
        target = nodes[0]
        intervention = mode.removeprefix("isolated_")
        treatment = "baseline" if intervention == "regular" else intervention

        def readings():
            for node, t, values, label in stream:
                if node == target:
                    yield node, t, transform(values, treatment), label

        return readings(), (target,), t0

    return source


def verify(seeds, model=None):
    seeds = tuple(seeds)
    if (not seeds or any(x < 601 for x in seeds)
            or len(seeds) != len(set(seeds))):
        raise ValueError("Sealed test only accepts unique seeds >= 601")
    forest = Forest(model)
    summaries, episodes = [], []
    for label, policy in (
        ("off", DetectionPolicy()),
        ("candidate_B_pre_registered", CANDIDATE),
    ):
        for mode in MODES:
            metrics, items = evaluate_policy(
                forest, policy, seeds, scene_source=scenario(mode)
            )
            summaries.append(dict(
                policy=label, mode=mode, model=forest.version, **metrics
            ))
            episodes.extend(dict(policy=label, mode=mode, **e) for e in items)
    target = {
        r["mode"]: r for r in summaries
        if r["policy"] == "candidate_B_pre_registered"
    }
    critical = ("isolated_regular", "isolated_high_background")
    reasons = []
    for mode in critical:
        row = target[mode]
        if row["isolated_false_episodes"] != 0:
            reasons.append(f"{mode}: negative_unconfirmed_alert")
        if row["isolated_pre_ignition_episodes"] != 0:
            reasons.append(f"{mode}: pre_ignition_unconfirmed_alert")
    if target["isolated_regular"]["isolated_detected"] == 0:
        reasons.append("no_isolated_fire_recovered")
    # Unconfirmed alerts should be absent with a well populated healthy
    # neighbouring network; any occurrences are reported, not hidden.
    if target["five_nodes"]["isolated_false_episodes"] > 0:
        reasons.append("five_nodes: unconfirmed_false_alerts")
    return summaries, episodes, dict(
        approved_for_limited_synthetic_demo=not reasons,
        reasons=reasons,
        model=forest.version,
        candidate=dict(
            isolated_enabled=True, isolated_persist_s=120.0,
            isolated_min_fire_score=0.80,
            isolated_min_pm25_rise=8.0,
            isolated_min_temperature_rise=0.0,
        ),
        seeds=list(seeds),
        caveat="One-time synthetic stress test; NOT wildfire field validation",
        next_step="Only consider manual opt-in after Docker MQTT regression and team approval",
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", nargs="+", type=int, default=SEALED_SEEDS)
    p.add_argument("--model", type=Path)
    p.add_argument("--out", type=Path, default=ROOT / "resultados/isolated_sealed")
    a = p.parse_args()
    summary, episodes, decision = verify(a.seeds, a.model)
    a.out.mkdir(parents=True, exist_ok=True)
    write_csv(a.out / "sealed_summary.csv", summary)
    write_csv(a.out / "sealed_episodes.csv", episodes)
    (a.out / "decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(decision, indent=2, ensure_ascii=False))
    print("policy,mode,isolated_fire,negative_isolated,pre_ignition,by15m,corroborated")
    for row in summary:
        print(",".join(str(row[k]) for k in (
            "policy", "mode", "isolated_detected", "isolated_false_episodes",
            "isolated_pre_ignition_episodes", "isolated_detected_by_15m",
            "high_detected",
        )))


if __name__ == "__main__":
    main()
