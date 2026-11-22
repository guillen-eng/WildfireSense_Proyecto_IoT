"""Pre-registered high-background corroboration gate development study.

Tests shared PM2.5 backgrounds across neighbouring nodes; original V4 is the
baseline. It may select ONE proposed candidate on development-only seeds.
It does not change forest.json, gateway settings, or deploy any threshold.
"""
import argparse
import json
from dataclasses import replace
from pathlib import Path

from edge.logic import DetectionPolicy
from edge.model import Forest, ROOT
from .ood_stress import source_for
from .threshold_sensitivity import evaluate_policy, write_csv

DEV = tuple(range(901, 907))
CANDIDATES = (2.0, 4.0, 8.0)
TTLS = (180.0, 300.0, 600.0)


def policies():
    yield "legacy", DetectionPolicy()
    for rise in CANDIDATES:
        for ttl in TTLS:
            yield f"rise{rise:g}_ttl{ttl:g}", replace(
                DetectionPolicy(), corroboration_trend_enabled=True,
                corroboration_min_pm25_rise=rise,
                corroboration_trend_ttl_s=ttl,
            )


def choose(rows):
    originals = {r["mode"]: r for r in rows if r["candidate"] == "legacy"}
    by_candidate = {}
    for r in rows:
        by_candidate.setdefault(r["candidate"], {})[r["mode"]] = r
    accepted = []
    for name, cases in by_candidate.items():
        if name == "legacy":
            continue
        normal, high = cases["baseline"], cases["high_background"]
        if (normal["negative_high_episodes"] == 0
                and high["negative_high_episodes"] == 0
                and normal["high_detected"] >= 10
                and normal["detected_by_15m"] >= originals["baseline"]["detected_by_15m"] - 2
                and normal["pre_ignition_high_episodes"] == 0
                and high["pre_ignition_high_episodes"] == 0):
            accepted.append(name)
    if not accepted:
        return None, []
    ranked = sorted(
        accepted,
        key=lambda name: (
            -by_candidate[name]["baseline"]["detected_by_15m"],
            by_candidate[name]["baseline"]["delay_p95_s"] or float("inf"),
            float(name.split("_")[0][4:]),
            float(name.split("_")[1][3:]),
        ),
    )
    return ranked[0], accepted


def evaluate_development(seeds, model=None):
    seeds = tuple(seeds)
    if (not seeds or len(set(seeds)) != len(seeds)
            or any(x < 901 or x >= 1000 for x in seeds)):
        raise ValueError("Use unique, development-only seeds 901-999")
    forest = Forest(model)
    summary, episodes = [], []
    for label, policy in policies():
        for mode in ("baseline", "high_background"):
            totals, items = evaluate_policy(
                forest, policy, seeds, scene_source=source_for(mode))
            summary.append(dict(
                candidate=label, mode=mode, model=forest.version,
                gate_enabled=policy.corroboration_trend_enabled,
                rise=policy.corroboration_min_pm25_rise,
                ttl_s=policy.corroboration_trend_ttl_s,
                **totals,
            ))
            episodes.extend(dict(candidate=label, mode=mode, **episode)
                            for episode in items)
    selected, possible = choose(summary)
    return summary, episodes, dict(
        model=forest.version,
        development_seeds=list(seeds),
        accepted_candidates=possible,
        candidate_for_one_sealed_test=selected,
        note="Synthetic model family only; no automatic promotion or gate activation",
        selection_criteria="See docs/CORROBORACION_FONDO_ALTO.md",
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", nargs="+", type=int, default=DEV)
    ap.add_argument("--model", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "resultados/background_dev")
    args = ap.parse_args()
    rows, episodes, metadata = evaluate_development(args.seeds, args.model)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "candidates.csv", rows)
    write_csv(args.out / "episodes.csv", episodes)
    (args.out / "selection.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    print("candidate,mode,fire,negative_high,pre_ignition,by15m,delay_p95")
    for row in rows:
        print(",".join(str(row[k]) for k in (
            "candidate", "mode", "high_detected", "negative_high_episodes",
            "pre_ignition_high_episodes", "detected_by_15m", "delay_p95_s"
        )))


if __name__ == "__main__":
    main()
