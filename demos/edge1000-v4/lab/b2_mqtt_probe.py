"""MQTT E2E: opt-in B2 isolated alarm, then independent SOS while Cloud is absent.

Selects a fixed development-seed scenario by OFFLINE preflight (not a new
statistical evaluation), then replays its first isolated event over real
Mosquitto MQTT to the resource-limited Edge container. Never sends labels.
The test DOES NOT claim real fire sensitivity.

Run with broker+Edge already started with docker-compose.edge-b2.yml:
  python -m lab.b2_mqtt_probe --host mosquitto --out /app/resultados/b2_mqtt_probe.json
"""
import argparse
import json
from pathlib import Path
import threading
import time
import uuid

import paho.mqtt.client as mqtt
from edge.contract import MEASUREMENTS
from edge.logic import ALERTS, READINGS, SOS, DetectionPolicy, Engine, checked_node, iso
from .episodes import make_scene


def choose_demonstration_stream():
    """Reproducible developer-only fixture; do NOT use for performance claims."""
    for seed in range(301, 307):
        for scene in ("fast_fire", "slow_fire"):
            stream, nodes, onset = make_scene(seed, scene)
            chosen = checked_node(nodes[0])
            engine = Engine(policy=DetectionPolicy(isolated_enabled=True))
            selected = []
            for node, timestamp, values, _truth in stream:
                if checked_node(node) != chosen:
                    continue
                selected.append((timestamp, values))
                _, alerts = engine.evaluate(
                    "preflight", chosen, "b2-probe", len(selected),
                    timestamp, values, period=10
                )
                if any(e["decision"] == "unconfirmed_fire_risk" for e in alerts):
                    return seed, scene, chosen, onset, selected
    raise RuntimeError("No isolated B2 event found in FIXED development scenarios")


def execute(host, port, *, timeout=18):
    seed, scene, node, onset, stream = choose_demonstration_stream()
    run = "b2-mqtt-e2e-" + uuid.uuid4().hex[:12]
    received, subscribed = [], threading.Event()

    subscriber = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id="b2-e2e-s-" + run[-12:]
    )
    publisher = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id="b2-e2e-p-" + run[-12:]
    )

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            return
        client.subscribe(ALERTS, qos=1)

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        if all(not getattr(code, "is_failure", False) for code in reason_codes):
            subscribed.set()

    def on_message(client, userdata, message):
        if message.topic != ALERTS:
            return
        try:
            payload = json.loads(message.payload)
            if payload.get("run_id") == run:
                received.append(payload)
        except (ValueError, TypeError):
            pass

    subscriber.on_connect = on_connect
    subscriber.on_subscribe = on_subscribe
    subscriber.on_message = on_message
    subscriber.connect(host, port, 60)
    subscriber.loop_start()

    try:
        if not subscribed.wait(8):
            raise TimeoutError("MQTT subscription for Edge alerts not confirmed")
        publisher.connect(host, port, 60)
        publisher.loop_start()
        try:
            for seq, (timestamp, values) in enumerate(stream, 1):
                msg = dict(
                    schema_version=1, run_id=run, node_id=node, seq=seq,
                    boot_id="b2-probe", type="reading", period_s=10,
                    timestamp=iso(timestamp), timebase="simulated",
                    measurements=dict(zip(MEASUREMENTS, values)), test_only=True,
                    sent_unix_ns=time.time_ns(),
                )
                info = publisher.publish(
                    READINGS + node, json.dumps(msg, separators=(",", ":")), qos=0
                )
                info.wait_for_publish(timeout=3)
                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    raise RuntimeError(f"MQTT reading PUBLISH failed rc={info.rc}")

            # Send SOS independently of classifier or neighbours. Simulated
            # sequence is unrelated to the sensor's fire decision pipeline.
            sos = dict(
                schema_version=1, run_id=run, node_id=node, seq=len(stream) + 1,
                boot_id="b2-probe", type="sos", timestamp=iso(stream[-1][0] + 1),
                timebase="simulated", test_only=True, sent_unix_ns=time.time_ns(),
            )
            sos_info = publisher.publish(
                SOS, json.dumps(sos, separators=(",", ":")), qos=1
            )
            sos_info.wait_for_publish(timeout=5)
            limit = time.monotonic() + timeout
            while time.monotonic() < limit:
                types = {e.get("decision") for e in received}
                if {"unconfirmed_fire_risk", "sos_alert"} <= types:
                    break
                time.sleep(0.15)
        finally:
            publisher.loop_stop()
            publisher.disconnect()
    finally:
        subscriber.loop_stop()
        subscriber.disconnect()

    fires = [e for e in received if e.get("decision") == "unconfirmed_fire_risk"]
    sos_events = [e for e in received if e.get("decision") == "sos_alert"]
    if len(fires) != 1 or len(sos_events) != 1:
        raise AssertionError(
            f"Expected one unconfirmed and one SOS event, got "
            f"{len(fires)} unconfirmed and {len(sos_events)} SOS"
        )
    if (fires[0].get("confirmation") != "unconfirmed"
            or fires[0].get("priority") != "high"
            or fires[0].get("neighbour") is not None
            or fires[0].get("model") != "rf-a288fc78989a"
            or sos_events[0].get("priority") != "critical"):
        raise AssertionError("Event semantics differ from B2/SOS contract")
    if any(e.get("decision") == "suspected_fire" for e in received):
        raise AssertionError("A single node cannot produce corroborated fire")

    return dict(
        scope="MQTT E2E of synthetic B2 event and independent SOS; Cloud not required",
        seed=seed, scenario=scene, node=node, run_id=run,
        ignition_timestamp=iso(onset),
        sensor_readings_published=len(stream),
        events=[dict(event_id=e["event_id"], decision=e["decision"],
                     priority=e["priority"], confirmation=e.get("confirmation"))
                for e in received],
        model=fires[0]["model"],
        warning="Reproduces a designed synthetic event; no field accuracy claim",
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="mosquitto")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    result = execute(a.host, a.port)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
