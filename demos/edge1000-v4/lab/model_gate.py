"""Offline candidate gate: compare model versions on held-out *validation* episodes.

This intentionally does not deploy or retrain by default. It validates the
candidate's structure/hash and compares it with the deployed model on seeds
reserved for candidate selection, NOT the published final test seeds 201..230.

This is a synthetic quality-control gate, not evidence of field validity.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from datetime import datetime, timezone

from edge.model import ROOT
from lab.promote import promote, validate_candidate
from lab.evaluate import evaluate

VALIDATION_SEEDS = tuple(range(301, 307))


def run_gate(candidate: Path, baseline: Path, *, seeds=VALIDATION_SEEDS,
             max_macro_f1_drop=0.01, max_accuracy_drop=0.01, max_delay_increase_s=10.0):
    """Return a comparable, machine-readable decision; do not deploy anything."""
    if not seeds or any(seed not in VALIDATION_SEEDS for seed in seeds):
        raise ValueError("Only held-out candidate-validation seeds may be used")
    if max_macro_f1_drop < 0 or max_accuracy_drop < 0 or max_delay_increase_s < 0:
        raise ValueError("Allowed regressions must be nonnegative")
    previous = validate_candidate(baseline)
    proposed = validate_candidate(candidate)

    def measure(path, directory):
        # evaluate() writes full per-episode evidence, but the temporary files
        # are not required once their aggregate is captured in gate_report.json.
        with redirect_stdout(io.StringIO()):
            evaluate(directory, model=path, seeds=seeds)
        return json.loads((directory / "validacion.json").read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old = measure(baseline, root / "baseline")
        new = measure(candidate, root / "candidate")
    reasons = []
    if new["macro_f1"] + max_macro_f1_drop < old["macro_f1"]:
        reasons.append("macro_f1_regression")
    if new["accuracy"] + max_accuracy_drop < old["accuracy"]:
        reasons.append("accuracy_regression")
    if new["ml"]["detected"] < old["ml"]["detected"]:
        reasons.append("fewer_fire_episodes_detected")
    if new["ml"]["false_positive_episodes"] > old["ml"]["false_positive_episodes"]:
        reasons.append("more_false_positive_episodes")
    if old["ml"]["mean_delay_s"] is not None:
        if new["ml"]["mean_delay_s"] is None or (
            new["ml"]["mean_delay_s"] > old["ml"]["mean_delay_s"] + max_delay_increase_s
        ):
            reasons.append("fire_detection_delay_regression")
    return {
        "gate": "synthetic_validation_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "validation_seeds": list(seeds),
        "baseline_model": previous.version,
        "candidate_model": proposed.version,
        "same_version": previous.version == proposed.version,
        "baseline": old,
        "candidate": new,
        "thresholds": dict(max_macro_f1_drop=max_macro_f1_drop,
                           max_accuracy_drop=max_accuracy_drop,
                           max_delay_increase_s=max_delay_increase_s,
                           no_drop_in_fire_episode_recall=True,
                           no_increase_in_false_positive_episodes=True),
        "approved": not reasons,
        "reasons": reasons,
        "scope": ("Only the synthetic validation family. Does not establish performance "
                  "on independent physical wildfire sensor datasets."),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path, default=Path("/exchange/candidate.json"))
    p.add_argument("--baseline", type=Path, default=ROOT / "models/forest.json")
    p.add_argument("--out", type=Path, default=Path("/exchange/gate_report.json"))
    p.add_argument("--promote", action="store_true", help="Explicitly promote only after passing gate")
    p.add_argument("--max-macro-f1-drop", type=float, default=0.01)
    p.add_argument("--max-accuracy-drop", type=float, default=0.01)
    p.add_argument("--max-delay-increase-s", type=float, default=10)
    a = p.parse_args()
    report = run_gate(a.candidate, a.baseline,
                      max_macro_f1_drop=a.max_macro_f1_drop,
                      max_accuracy_drop=a.max_accuracy_drop,
                      max_delay_increase_s=a.max_delay_increase_s)
    report["promoted"] = False
    # Always save the result, including a failed gate, before terminating.
    if a.promote and report["approved"] and not report["same_version"]:
        promote(a.candidate, a.baseline)
        report["promoted"] = True
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("approved", "reasons", "baseline_model", "candidate_model", "same_version", "promoted")},
                     ensure_ascii=False, indent=2))
    if not report["approved"]:
        raise SystemExit("Candidate REJECTED by synthetic validation gate; baseline unchanged")


if __name__ == "__main__":
    main()
