"""Deterministic replay of application-level communication impairments.

Models losses, duplicates and *arrival order* jitter of JSONL measurements.
It does NOT emulate actual WiFi/LoRa/MQTT QoS or RF propagation. The ground
truth stays outside the inference engine and is consulted only afterwards.
"""

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import random

from edge.logic import Engine, READINGS, SOS, adapt
from edge.reorder import BoundedEventBuffer


def schedule(messages, *, loss=0.0, duplicates=0.0, jitter_s=0.0, seed=42):
    if not (0 <= loss <= 1 and 0 <= duplicates <= 1 and 0 <= jitter_s <= 3600):
        raise ValueError("loss, duplicates in [0,1]; jitter_s in [0,3600]")
    rng = random.Random(seed)
    staged = []
    original = dropped = duplicated = 0
    for original, raw in enumerate(messages, start=1):
        if rng.random() < loss:
            dropped += 1
            continue
        copies = 1 + int(rng.random() < duplicates)
        duplicated += copies - 1
        for _ in range(copies):
            staged.append((raw["ts"] / 1000 + rng.uniform(0, jitter_s), original, raw))
    # For equal timestamps retain original input order. For overlapping delays,
    # order may change; per-node sequence checks in the Engine reject stales.
    staged.sort(key=lambda item: (item[0], item[1]))
    return staged, dict(input_messages=original, dropped=dropped, duplicated=duplicated)


def evaluate(messages, *, loss=0.0, duplicates=0.0, jitter_s=0.0, seed=42, truth_onset=None, reorder_window_s=0.0):
    staged, stats = schedule(messages, loss=loss, duplicates=duplicates, jitter_s=jitter_s, seed=seed)
    engine = Engine()
    events = Counter()
    first_fire_s = None
    first_sos_s = None
    first_fire_available_s = None
    first_sos_available_s = None
    buffer = BoundedEventBuffer(reorder_window_s) if reorder_window_s > 0 else None

    def consume(available_at, topic, msg):
        nonlocal first_fire_s, first_sos_s, first_fire_available_s, first_sos_available_s
        _, produced = engine.handle(topic, msg)
        for event in produced:
            events[event["decision"]] += 1
            if event["decision"] == "suspected_fire" and first_fire_s is None:
                first_fire_s = datetime.fromisoformat(event["reading_timestamp"]).timestamp()
                first_fire_available_s = available_at
            if event["decision"] == "sos_alert" and first_sos_s is None:
                first_sos_s = datetime.fromisoformat(event["reading_timestamp"]).timestamp()
                first_sos_available_s = available_at

    for arrival, number, raw in staged:
        msg = adapt(raw, run="robustness-replay")
        topic = SOS if msg["type"] == "sos" else READINGS + msg["node_id"]
        if buffer:
            for ready in buffer.push(arrival, topic, msg):
                consume(*ready)
        else:
            consume(arrival, topic, msg)
    if buffer and staged:
        for ready in buffer.finish(staged[-1][0]):
            consume(*ready)
    result = dict(
        **stats,
        delivered_messages=len(staged),
        accepted_readings=engine.accepted,
        rejected_order_or_duplicate=engine.rejected_order,
        sequence_gaps=engine.gaps,
        node_states=len(engine.nodes),
        decisions=dict(events),
        first_suspected_fire_timestamp=first_fire_s,
        first_sos_timestamp=first_sos_s,
        first_suspected_fire_available_timestamp=first_fire_available_s,
        first_sos_available_timestamp=first_sos_available_s,
        reorder=(buffer.metrics() if buffer else None),
        settings=dict(loss=loss, duplicates=duplicates, jitter_s=jitter_s,
                      reorder_window_s=reorder_window_s, seed=seed),
    )
    if truth_onset is not None:
        result["suspected_fire_delay_s"] = (
            round(first_fire_s - truth_onset, 2) if first_fire_s is not None else None
        )
        result["first_alarm_available_delay_s"] = (
            round(first_fire_available_s - truth_onset, 2)
            if first_fire_available_s is not None else None
        )
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", type=Path, default=Path("data/scenarios/fuego_rapido.jsonl"))
    p.add_argument("--loss", type=float, default=0.05, help="Probabilidad de perdida [0,1]")
    p.add_argument("--duplicates", type=float, default=0.02, help="Probabilidad de duplicado [0,1]")
    p.add_argument("--jitter-s", type=float, default=90, help="Retardo uniforme [0,jitter_s]")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--reorder-window-s", type=float, default=0,
                   help="Experimental offline event-time buffering; adds detection latency")
    p.add_argument("--out", type=Path, default=Path("resultados/robustez_sintetica.json"))
    a = p.parse_args()
    truth_path = a.file.with_name(a.file.stem + "_verdad.json")
    truth_onset = None
    if truth_path.is_file():
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        truth_onset = 1784073600 + truth["t0_s"]
    with a.file.open(encoding="utf-8") as f:
        result = evaluate((json.loads(line) for line in f), loss=a.loss,
                          duplicates=a.duplicates, jitter_s=a.jitter_s,
                          seed=a.seed, truth_onset=truth_onset,
                          reorder_window_s=a.reorder_window_s)
    result["source_file"] = str(a.file)
    result["scope"] = "Impairment offline de aplicacion; no prueba RF ni MQTT real"
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
