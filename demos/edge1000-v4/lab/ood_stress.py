"""Documented synthetic distribution-shift probes; NOT independent field validation.

Do not use results to adjust production thresholds. This tests model brittleness
when conditions differ from its training generator, including zero neighbours.
Run: python -m lab.ood_stress --seeds 401 402 --out resultados/ood_stress
"""

import argparse
import csv
import json
from pathlib import Path

from edge.logic import DetectionPolicy
from edge.model import Forest, ROOT
from .episodes import make_scene
from .threshold_sensitivity import evaluate_policy, write_csv


MODES = (
    "baseline",
    "high_background",
    "coarse_mixture",
    "high_humidity",
    "pm25_underread",
    "single_node",
)
STRESS_SEEDS = tuple(range(401, 407))


def transform(values, mode):
    """Hypothetical stress transforms, never claimed to be calibrated physics."""
    pm25, pm10, temp, rh = values
    if mode == "high_background":
        pm25, pm10 = pm25 + 25.0, pm10 + 30.0
    elif mode == "coarse_mixture":
        # Tests whether a smoke + coarse particulate mixture is rejected.
        pm10 = max(pm10, pm25 * 3.5)
    elif mode == "high_humidity":
        rh = max(rh, 97.0)
    elif mode == "pm25_underread":
        pm25 *= 0.70
    elif mode in ("baseline", "single_node"):
        pass
    else:
        raise ValueError("Unknown stress transform")
    pm25 = max(0.0, pm25)
    pm10 = max(pm25, pm10)
    return (round(pm25, 2), round(pm10, 2), temp, min(100.0, rh))


def source_for(mode):
    if mode not in MODES:
        raise ValueError("Unknown stress mode")

    def source(seed, scene):
        stream, nodes, t0 = make_scene(seed, scene)
        chosen = nodes[0]

        def readings():
            for node, t, values, label in stream:
                if mode == "single_node" and node != chosen:
                    continue
                yield node, t, transform(values, mode), label

        return readings(), nodes, t0
    return source


def probe(seeds, model=None):
    seeds = tuple(seeds)
    if not seeds or len(set(seeds)) != len(seeds) or min(seeds) < 401:
        raise ValueError("Use unique stress seeds >= 401, not training/validation/test seeds")
    forest = Forest(model)
    policies = DetectionPolicy()
    summary, details = [], []
    for mode in MODES:
        metrics, episodes = evaluate_policy(
            forest, policies, seeds, scene_source=source_for(mode)
        )
        summary.append(dict(mode=mode, model=forest.version, **metrics))
        details.extend(dict(mode=mode, **episode) for episode in episodes)
    return summary, details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=STRESS_SEEDS)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "resultados/ood_stress")
    args = parser.parse_args()
    summaries, episodes = probe(args.seeds, args.model)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "stress_summary.csv", summaries)
    write_csv(args.out / "stress_episodes.csv", episodes)
    meta = dict(
        scope="Synthetic perturbation study, NOT an independently labelled wildfire dataset",
        model=summaries[0]["model"], seeds=args.seeds,
        transforms={
            "baseline": "Same generator, new seeds only",
            "high_background": "Add PM2.5 +25 and PM10 +30 ug/m3 globally",
            "coarse_mixture": "Raise PM10 to at least 3.5 x PM2.5",
            "high_humidity": "Clamp relative humidity to at least 97%",
            "pm25_underread": "Multiply PM2.5 by 0.70 (synthetic biased sensor)",
            "single_node": "Only one node online, so no healthy neighbour can corroborate",
        },
        baseline=summaries[0],
        warning="Do not tune thresholds or claim real-fire sensitivity using these stress results.",
    )
    (args.out / "stress.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
