"""Reproduce original teammate scenes and groups corroborated alerts without MQTT."""

import argparse
import json
from pathlib import Path

from cloud.incidents import group_suspected_fire
from edge.logic import Engine, READINGS, SOS, adapt


def evaluate_scene(path: Path):
    engine = Engine()
    events = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            raw = json.loads(line)
            msg = adapt(raw, run=path.stem)
            topic = SOS if msg["type"] == "sos" else READINGS + msg["node_id"]
            _, generated = engine.handle(topic, msg)
            events.extend(generated)
    suspects = [event for event in events if event["decision"] == "suspected_fire"]
    incident_groups = group_suspected_fire(suspects)
    return {
        "scenario": path.stem,
        "readings": engine.accepted,
        "suspected_fire_events": len(suspects),
        "grouped_incidents": len(incident_groups),
        "incident_event_counts": [g["alert_count"] for g in incident_groups],
        "note": "Agrupacion hipotetica espacial y temporal, no verdad de campo",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenarios", nargs="+", default=["fuego_lento", "fuego_rapido"])
    p.add_argument("--out", type=Path, default=Path("resultados/agrupacion_escenarios.json"))
    a = p.parse_args()
    folder = Path(__file__).resolve().parents[1] / "data" / "scenarios"
    rows = [evaluate_scene(folder / f"{name}.jsonl") for name in a.scenarios]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
