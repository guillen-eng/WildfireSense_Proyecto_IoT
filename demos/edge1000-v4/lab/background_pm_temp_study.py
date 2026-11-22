"""Last pre-registered development study: temporal PM and local temperature.

Only seeds 921-926 for engineering selection. If no policy passes the gate,
the experimental filter remains off. The script never writes Edge config.
"""
import argparse
import json
from dataclasses import replace
from pathlib import Path

from edge.logic import DetectionPolicy
from edge.model import Forest, ROOT
from .ood_stress import source_for
from .threshold_sensitivity import evaluate_policy, write_csv

DEV = tuple(range(921, 927))
PM_RISE = (2.0, 4.0, 8.0)
TEMP_RISE = (0.25, 0.5, 1.0)
TTL = 300.0


def candidate_policies():
    yield "legacy", DetectionPolicy()
    for pm in PM_RISE:
        for temp in TEMP_RISE:
            label = f"pm{pm:g}_temp{temp:g}_ttl300"
            yield label, replace(
                DetectionPolicy(),
                corroboration_trend_enabled=True,
                corroboration_min_pm25_rise=pm,
                corroboration_min_temp_rise=temp,
                corroboration_trend_ttl_s=TTL,
            )


def choose(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row["candidate"], {})[row["mode"]] = row
    original = groups["legacy"]["baseline"]
    candidates = []
    for name, group in groups.items():
        if name == "legacy":
            continue
        normal, high = group["baseline"], group["high_background"]
        if (normal["negative_high_episodes"] == 0
                and high["negative_high_episodes"] == 0
                and normal["pre_ignition_high_episodes"] == 0
                and high["pre_ignition_high_episodes"] == 0
                and normal["high_detected"] >= 10
                and normal["detected_by_15m"] >= original["detected_by_15m"] - 2):
            candidates.append(name)
    candidates.sort(key=lambda name: (
        -groups[name]["baseline"]["detected_by_15m"],
        groups[name]["baseline"]["delay_p95_s"] or float("inf"),
        float(name.split("_")[0][2:]),
        float(name.split("_")[1][4:]),
    ))
    return (candidates[0] if candidates else None), candidates


def study(seeds, model=None):
    seeds = tuple(seeds)
    if (not seeds or len(set(seeds)) != len(seeds)
            or any(x < 921 or x >= 1000 for x in seeds)):
        raise ValueError("Only new development seeds 921-999 allowed")
    forest = Forest(model)
    summary, episodes = [], []
    for label, policy in candidate_policies():
        for mode in ("baseline", "high_background"):
            metrics, details = evaluate_policy(
                forest, policy, seeds, scene_source=source_for(mode))
            summary.append(dict(
                candidate=label, mode=mode, model=forest.version,
                pm_rise=policy.corroboration_min_pm25_rise,
                temp_rise=policy.corroboration_min_temp_rise,
                ttl_s=policy.corroboration_trend_ttl_s,
                **metrics,
            ))
            episodes.extend(dict(candidate=label, mode=mode, **e)
                            for e in details)
    selected, permitted = choose(summary)
    return summary, episodes, dict(
        model=forest.version,
        development_seeds=seeds,
        accepted_candidates=permitted,
        candidate_for_one_sealed_test=selected,
        note="The result can be None. NEVER change active Edge on a failed gate.",
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", nargs="+", type=int, default=DEV)
    p.add_argument("--model", type=Path)
    p.add_argument("--out", type=Path, default=ROOT / "resultados/background_pm_temp_dev")
    a = p.parse_args()
    data, episodes, metadata = study(a.seeds, a.model)
    a.out.mkdir(exist_ok=True, parents=True)
    write_csv(a.out / "candidates.csv", data)
    write_csv(a.out / "episodes.csv", episodes)
    (a.out / "selection.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))
    print("candidate,mode,fire_detected,negative_high,preignition,by15,p95_s")
    for row in data:
        print(",".join(str(row[x]) for x in (
            "candidate", "mode", "high_detected", "negative_high_episodes",
            "pre_ignition_high_episodes", "detected_by_15m", "delay_p95_s"
        )))


if __name__ == "__main__":
    main()
