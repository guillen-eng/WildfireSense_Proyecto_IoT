"""Run the Edge engine over the team's nine scenario files and check each *_verdad.json.

External to the training generator: scenarios come from a different generator
family (still synthetic). Used as an extra check for retrained candidates.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from edge.logic import Engine, READINGS, SOS
from edge.model import Forest, ROOT

BASE_MS = 1784073600000
SCENARIOS = (
    "fuego_lento", "fuego_rapido", "polvo_tractor", "niebla", "sol_directo",
    "sos_boton", "fallo_congelado", "fallo_ruido", "fallo_silencio",
)
DEFAULT_DIR = ROOT / "data" / "scenarios"


def _node(n):
    return f"node_{n:04d}"


def run_scenario(name, forest, directory=DEFAULT_DIR):
    truth = json.loads((directory / f"{name}_verdad.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (directory / f"{name}.jsonl").open(encoding="utf-8")]
    rows.sort(key=lambda r: (r["ts"], r["id"], r["seq"]))
    engine, events, rejected = Engine(forest=forest), [], 0
    for raw in rows:
        topic = SOS if raw.get("kind") == "emergency" else READINGS + _node(raw["id"])
        try:
            _, out = engine.handle(topic, raw)
        except ValueError:
            rejected += 1
            continue
        events.extend(out)
    t0 = BASE_MS / 1000 + truth["t0_s"]

    def times(kind, node=None):
        return sorted(
            e["_t"] for e in events
            if e["decision"] == kind and (node is None or e["node_id"] == _node(node))
        )

    for e in events:  # reading_timestamp -> epoch seconds
        from datetime import datetime
        e["_t"] = datetime.fromisoformat(e["reading_timestamp"]).timestamp()
    fires, risks = times("suspected_fire"), times("environmental_risk")
    result = dict(
        scenario=name, messages=len(rows), rejected=rejected,
        suspected_fire=len(fires), environmental_risk=len(risks), checks={},
    )
    if name.startswith("fuego"):
        result["delay_s"] = round(fires[0] - t0, 1) if fires else None
        result["checks"] = {
            "fire_detected": bool(fires),
            "no_alarm_before_start": not any(t < t0 for t in fires),
        }
        # Neighbours must alarm before the (modelled) fire front reaches them.
        lead = {}
        for alias, number in truth.get("alias", {}).items():
            arrival = truth["nodos_detalle"][str(number)]["llega_fuego_s"]
            first = times("suspected_fire", number)
            if alias != "N3" and arrival is not None:
                lead[alias] = round(BASE_MS / 1000 + arrival - first[0], 1) if first else None
        result["front_lead_s"] = lead
        result["checks"]["neighbours_alarm_before_front"] = bool(lead) and all(
            v is not None and v > 0 for v in lead.values()
        )
    elif name == "sos_boton":
        sos = times("sos_alert", truth["nodo_evento"])
        result["delay_s"] = round(sos[0] - t0, 1) if sos else None
        result["checks"] = {"sos_within_5s": bool(sos) and sos[0] - t0 <= 5,
                            "no_fire_alarm": not fires}
    elif name.startswith("fallo"):
        health = [e for e in events if e["decision"] == "node_health"
                  and e["node_id"] == _node(truth["nodo_evento"])]
        want = truth["estado_esperado_nodo"]
        result["checks"] = {
            "node_flagged": any(e.get("health") == want for e in health)
            or (want == "FALLO" and bool(health)),
            "no_fire_alarm": not fires,
        }
    else:
        result["checks"] = {"no_fire_alarm": not fires}
    result["passed"] = all(result["checks"].values())
    return result


def run_all(model_path, directory=DEFAULT_DIR):
    forest = Forest(model_path)
    results = [run_scenario(n, forest, directory) for n in SCENARIOS]
    return dict(
        model=forest.version,
        passed=sum(r["passed"] for r in results),
        total=len(results),
        failed=[r["scenario"] for r in results if not r["passed"]],
        results=results,
    )


def compare(candidate, baseline, directory=DEFAULT_DIR):
    """Candidate must not fail a scenario that the deployed model passes."""
    new, old = run_all(candidate, directory), run_all(baseline, directory)
    regressions = sorted(set(new["failed"]) - set(old["failed"]))
    return dict(approved=not regressions, regressions=regressions, candidate=new, baseline=old)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, default=ROOT / "models/forest.json")
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    args = ap.parse_args()
    report = run_all(args.model, args.dir)
    for r in report["results"]:
        print(f'{r["scenario"]:16s} {"OK " if r["passed"] else "FAIL"} {r["checks"]} '
              f'fire={r["suspected_fire"]} risk={r["environmental_risk"]} delay={r.get("delay_s")}')
    print(f'{report["model"]}: {report["passed"]}/{report["total"]}')
