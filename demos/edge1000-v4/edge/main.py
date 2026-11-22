"""Run with python -m edge.main. MQTT callbacks and state share one event loop."""

import json
import os
import time
import uuid
from collections import Counter, deque
import paho.mqtt.client as mqtt
from .logic import Engine, DetectionPolicy, ALERTS, HEALTH, READINGS, SOS, iso
from .transport import (
    ACK,
    PING,
    PONG,
    STATS,
    READY,
    SUMMARY,
    Journal,
    aggregate,
    percentile,
    publish_size,
    wire,
)


class Gateway:
    def __init__(self):
        isolated_env = os.getenv("EDGE_ISOLATED_ESCALATION", "0")
        if isolated_env not in ("0", "1"):
            raise ValueError("EDGE_ISOLATED_ESCALATION must be 0 or 1")
        self.engine = Engine(policy=DetectionPolicy(
            isolated_enabled=isolated_env == "1"
        ))
        self.store = Journal(os.getenv("EDGE_DB", "state/edge.sqlite"))
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="wildfiresense-edge"
        )
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.online = False
        self.rtt = None
        self.pongs_at = -1e20
        self.probes = {}
        self.next_ping = self.next_retry = self.next_status = self.next_window = (
            self.next_watch
        ) = 0
        self.samples = []
        self.timing = deque(maxlen=50000)
        self.delivery = deque(maxlen=50000)
        self.count = Counter()
        self.cpu_start = time.process_time()
        self.start = time.monotonic()

    def send(self, topic, payload, qos=0, retain=False):
        info = self.client.publish(topic, payload, qos=qos, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            self.count["send_errors"] += 1
            return
        if topic in (ALERTS, SUMMARY):
            self.count["up_payload_bytes"] += len(payload.encode())
            self.count["up_publish_bytes"] += publish_size(
                topic, len(payload.encode()), qos
            )

    def on_connect(self, client, userdata, flags, reason, properties):
        if not reason.is_failure:
            client.subscribe(
                [(READINGS + "+", 0), (SOS, 1), (ACK, 1), (PONG, 0), (READY, 0)]
            )
            self.online = True
            self.pongs_at = -1e20
            self.next_status = 0

    def save_event(self, event, ms):
        topic = HEALTH if event["type"] == "node_health" else ALERTS
        event.update(edge_processing_ms=round(ms, 3), generated_at=iso(time.time()))
        if not self.store.save(topic, event):
            return
        self.send(topic, wire(event), 1)
        self.count[event["decision"]] += 1
        if event["decision"] in (
            "suspected_fire", "sos_alert", "unconfirmed_fire_risk"
        ):
            print(
                "ALARMA LOCAL",
                event["decision"],
                event["node_id"],
                event.get("neighbour", ""),
                flush=True,
            )

    def on_message(self, client, userdata, msg):
        tic = time.perf_counter()
        rx_ns = time.time_ns()
        try:
            if len(msg.payload) > 65536:
                raise ValueError("oversize")
            data = json.loads(msg.payload)
            if not isinstance(data, dict):
                raise ValueError("object required")
            if msg.topic == PONG:
                sent = self.probes.pop(data.get("nonce"), None)
                if sent is not None:
                    self.pongs_at = time.monotonic()
                    self.rtt = 1000 * (self.pongs_at - sent)
                return
            if msg.topic == ACK:
                self.store.confirm(data["event_id"])
                return
            if msg.topic == READY:
                self.status()
                return
            prediction, events = self.engine.handle(msg.topic, data)
            ms = 1000 * (time.perf_counter() - tic)
            if prediction is not None:
                self.timing.append(ms)
                self.count["in_payload_bytes"] += len(msg.payload)
                self.count["in_publish_bytes"] += publish_size(
                    msg.topic, len(msg.payload), msg.qos
                )
                if self.engine.accepted % 10 == 0:
                    raw = (
                        data["values"]["PM2.5"]
                        if "values" in data
                        else data["measurements"]["pm25_ug_m3"]
                    )
                    self.samples.append(raw)
                    if len(self.samples) >= 512:
                        self.flush()
            for event in events:
                event["rx_ts"] = iso(rx_ns / 1e9)
                if (
                    type(data.get("sent_unix_ns")) is int
                    and rx_ns >= data["sent_unix_ns"]
                ):
                    event["sender_to_rx_ms"] = round(
                        (rx_ns - data["sent_unix_ns"]) / 1e6, 3
                    )
                self.save_event(event, ms)
            if (
                "sent_unix_ns" in data
                and type(data["sent_unix_ns"]) == int
                and (prediction is not None or msg.topic == SOS)
            ):
                delta = (time.time_ns() - data["sent_unix_ns"]) / 1e6
                if delta >= 0:
                    self.delivery.append(delta)
        except (ValueError, KeyError, TypeError, OverflowError, OSError) as exc:
            self.count["invalid"] += 1
            if self.count["invalid"] <= 5:
                print("Rechazado", msg.topic, str(exc), flush=True)

    def uplink(self):
        return (
            time.monotonic() - self.pongs_at <= 6
            and self.rtt is not None
            and self.rtt <= 250
        )

    def flush(self):
        if not self.samples:
            return
        obj = dict(event_id=uuid.uuid4().hex, generated_at=iso(time.time()))
        if self.uplink():
            obj.update(computed_by="cloud", samples=self.samples)
        else:
            obj.update(computed_by="edge", **aggregate(self.samples))
        self.count["windows_" + obj["computed_by"]] += 1
        self.store.save(SUMMARY, obj)
        if self.uplink():
            self.send(SUMMARY, wire(obj), 1)
        self.samples = []

    def status(self):
        eng = self.engine
        snapshot = dict(
            **self.count,
            readings=eng.accepted,
            nodes=len({node for _, node in eng.nodes}),
            run_node_states=len(eng.nodes),
            gaps=eng.gaps,
            rejected_order=eng.rejected_order,
            evictions=eng.evictions,
            model=eng.forest.version,
            isolated_escalation_enabled=eng.policy.isolated_enabled,
            cloud_available=self.uplink(),
            cloud_rtt_ms=self.rtt,
            backlog=self.store.backlog(),
            processing_p95_ms=percentile(self.timing, 0.95),
            processing_p99_ms=percentile(self.timing, 0.99),
            sender_to_decision_p95_ms=percentile(self.delivery, 0.95),
            sender_to_decision_p99_ms=percentile(self.delivery, 0.99),
            measured_deliveries_window=len(self.delivery),
            timing_window=len(self.timing),
            generated_at=iso(time.time()),
            uptime_s=round(time.monotonic() - self.start, 3),
            cpu_s=round(time.process_time() - self.cpu_start, 3),
        )
        try:
            import resource

            snapshot["peak_rss_kib_linux"] = resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss
        except ImportError:
            pass
        self.send(STATS, wire(snapshot), 0, True)

    def tick(self):
        now = time.monotonic()
        if now >= self.next_ping:
            key = uuid.uuid4().hex
            self.probes = {k: t for k, t in self.probes.items() if now - t < 6}
            self.probes[key] = now
            self.send(PING, wire(dict(nonce=key)))
            self.next_ping = now + 2
        if now >= self.next_window:
            self.flush()
            self.next_window = now + 5
        if now >= self.next_watch:
            for rid in {
                rid for (rid, _), s in self.engine.nodes.items() if s.clock == "wall"
            }:
                for ev in self.engine.expire(rid, time.time()):
                    self.save_event(ev, 0)
            self.next_watch = now + 1
        if self.uplink() and now >= self.next_retry:
            for topic, body in self.store.pending():
                self.send(topic, body, 1)
            self.next_retry = now + 2
        if now >= self.next_status:
            self.status()
            self.next_status = now + 2

    def run(self):
        while True:
            try:
                self.client.connect(
                    os.getenv("MQTT_HOST", "localhost"),
                    int(os.getenv("MQTT_PORT", "1883")),
                    60,
                )
                while self.client.loop(timeout=0.08) == mqtt.MQTT_ERR_SUCCESS:
                    if self.online:
                        self.tick()
            except OSError:
                pass
            self.online = False
            time.sleep(1)


if __name__ == "__main__":
    Gateway().run()
