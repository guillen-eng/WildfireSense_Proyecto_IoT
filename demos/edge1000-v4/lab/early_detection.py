"""Evaluate event-level early detection deadlines from held-out episode CSV.

This does not change or retrain the model and uses no simulated labels as
inference features. The reference ignition time is used only for evaluation.
"""

import argparse
import csv
import json
from pathlib import Path

DEFAULT_HORIZONS_S = (300, 900, 1800, 3600)


def analyze(rows, horizons=DEFAULT_HORIZONS_S):
    results = {}
    for method in sorted({r["method"] for r in rows}):
        fire = [r for r in rows if r["method"] == method and r["scenario"].endswith("_fire")]
        negative = [r for r in rows if r["method"] == method and not r["scenario"].endswith("_fire")]
        delays = [float(r["fire_delay_s"]) for r in fire if r.get("fire_delay_s") not in ("", None)]
        false_positive = sum(
            r.get("fire_delay_s") not in ("", None)
            or int(r.get("alerts_before_onset") or 0) > 0 for r in negative
        )
        horizons_result = {}
        for seconds in horizons:
            detected = sum(0 <= t <= seconds for t in delays)
            horizons_result[str(seconds)] = dict(
                detected=detected,
                total=len(fire),
                recall=round(detected / len(fire), 4) if fire else None,
            )
        results[method] = dict(
            fire_episodes=len(fire),
            total_detected=len(delays),
            negative_episodes=len(negative),
            negative_with_suspicion=false_positive,
            horizons_seconds=horizons_result,
        )
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=Path("resultados/episodios_test.csv"))
    p.add_argument("--output", type=Path, default=Path("resultados/deteccion_temprana.json"))
    args = p.parse_args()
    with args.input.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("No episodes found")
    report = dict(
        source=str(args.input),
        caveat="Semillas sinteticas reservadas; no es validacion de incendios reales",
        methods=analyze(rows),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
