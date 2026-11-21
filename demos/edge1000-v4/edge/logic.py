"""One decision engine for unit tests, offline replay and the MQTT gateway."""

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math

from .contract import parse_reading, MEASUREMENTS, BANNED_FIELDS
from .features import Filters
from .model import Forest

READINGS = "wildfiresense/readings/"
SOS = "wildfiresense/events/sos"
ALERTS = "wildfiresense/edge/alerts"
HEALTH = "wildfiresense/edge/health"
RAW = ("PM2.5", "PM10", "temperature", "humidity")
FIRE_SCORE = 0.65
PERSIST = 30
NEIGHBOUR_TTL = 180


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds")


def checked_node(node):
    if isinstance(node, int) and not isinstance(node, bool):
        n = node
    elif (
        isinstance(node, str)
        and node.startswith("node_")
        and node[5:].isascii()
        and node[5:].isdigit()
    ):
        n = int(node[5:])
    else:
        raise ValueError("Invalid grid node")
    if not 1 <= n <= 1024:
        raise ValueError("Node outside 32x32 grid")
    return f"node_{n:04d}"


def adapt(raw, run="raw-live"):
    """Translate teammate wire format without adding any scenario label."""
    if (
        raw.get("v") != 1
        or raw.get("kind") not in ("periodic", "event", "emergency")
        or BANNED_FIELDS.intersection(raw)
    ):
        raise ValueError("Invalid raw telemetry")
    n = checked_node(raw["id"])
    if type(raw["ts"]) is not int:
        raise ValueError("Invalid raw clock")
    msg = dict(
        schema_version=1,
        run_id=run,
        node_id=n,
        seq=raw["seq"],
        timestamp=iso(raw["ts"] / 1000),
        timebase="simulated",
        boot_id=raw.get("boot_id", "default"),
        test_only=True,
    )
    if raw["kind"] == "emergency":
        return {**msg, "type": "sos"}
    return {
        **msg,
        "type": "reading",
        "measurements": {k: raw["values"][v] for k, v in zip(MEASUREMENTS, RAW)},
    }


def neighbours(node):
    n = int(node[5:]) - 1
    x, y = n % 32, n // 32
    for j in range(max(0, y - 1), min(32, y + 2)):
        for i in range(max(0, x - 1), min(32, x + 2)):
            if i != x or j != y:
                yield f"node_{1 + j * 32 + i:04d}"


@dataclass
class Node:
    boot: str
    seq: int = -1
    t: float = -math.inf
    period: float = 60.0
    filters: Filters = field(default_factory=Filters)
    recent: deque = field(default_factory=lambda: deque(maxlen=12))
    identical: int = 0
    last_values: tuple | None = None
    health: str = "OK"
    since: float | None = None
    evidence: float = -math.inf
    risk: bool = False
    alarm: bool = False
    clear_since: float | None = None
    clock: str = "simulated"


class Engine:
    def __init__(self, forest=None, mode="ml", capacity=4096):
        self.forest = forest or Forest()
        self.mode = mode
        self.capacity = capacity
        self.nodes = OrderedDict()
        self.seen_sos = OrderedDict()
        self.tick_times = OrderedDict()
        self.gaps = self.rejected_order = self.accepted = self.evictions = 0

    def event(self, run, node, boot, seq, t, kind, **detail):
        key = json.dumps([run, node, boot, seq, kind], separators=(",", ":")).encode()
        return dict(
            event_id=hashlib.sha256(key).hexdigest()[:32],
            run_id=run,
            node_id=node,
            type=(
                "sos_alert"
                if kind == "sos_alert"
                else "node_health"
                if kind == "node_health"
                else "environmental_alert"
            ),
            decision=kind,
            reading_timestamp=iso(t),
            priority={"sos_alert": "critical", "suspected_fire": "high"}.get(
                kind, "advisory"
            ),
            model=self.forest.version,
            test_only=True,
            **detail,
        )

    def expire(self, run, t):
        """Use wall time for live wall clocks and event time per simulated replay."""
        events = []
        if t - self.tick_times.get(run, -math.inf) < 5:
            return events
        self.tick_times[run] = t
        self.tick_times.move_to_end(run)
        if len(self.tick_times) > self.capacity:
            self.tick_times.popitem(last=False)
        for (rid, n), s in self.nodes.items():
            if rid == run and s.health != "FALLO" and t - s.t > max(45, 2.5 * s.period):
                s.health = "FALLO"
                s.evidence = -math.inf
                s.risk = s.alarm = False
                s.since = s.clear_since = None
                events.append(
                    self.event(
                        run,
                        n,
                        s.boot,
                        s.seq,
                        t,
                        "node_health",
                        health=s.health,
                        reason="silence",
                    )
                )
        return events

    def handle(self, topic, msg):
        if not isinstance(msg, dict) or BANNED_FIELDS.intersection(msg):
            raise ValueError("Invalid message")
        if "values" in msg or "v" in msg:
            msg = adapt(msg)
        if topic == SOS:
            if (
                msg.get("type") not in ("sos", "sos_alert", "emergency")
                or msg.get("schema_version") != 1
            ):
                raise ValueError("Invalid SOS")
            run, node, seq, tstamp, _ = parse_reading(
                {
                    **msg,
                    "type": "reading",
                    "measurements": dict.fromkeys(MEASUREMENTS, 0),
                }
            )
            node = checked_node(node)
            boot = msg.get("boot_id", "default")
            if not isinstance(boot, str) or not 0 < len(boot) <= 128:
                raise ValueError("Invalid boot")
            key = (run, node, boot, seq)
            if key in self.seen_sos:
                return None, []
            self.seen_sos[key] = True
            if len(self.seen_sos) > 8192:
                self.seen_sos.popitem(last=False)
            return None, [
                self.event(
                    run,
                    node,
                    boot,
                    seq,
                    tstamp.timestamp(),
                    "sos_alert",
                    reason="manual_button",
                )
            ]
        run, node, seq, stamp, v = parse_reading(msg)
        node = checked_node(node)
        if topic != READINGS + node or v[0] > v[1]:
            raise ValueError("Topic or PM mismatch")
        boot = msg.get("boot_id", "default")
        if not isinstance(boot, str) or not 0 < len(boot) <= 128:
            raise ValueError("Invalid boot")
        period = msg.get("period_s")
        if period is not None and (
            type(period) not in (int, float) or not 1 <= period <= 3600
        ):
            raise ValueError("Invalid period")
        return self.evaluate(
            run, node, boot, seq, stamp.timestamp(), v, msg["timebase"], period
        )

    def evaluate(self, run, node, boot, seq, t, v, clock="simulated", period=None):
        key = (run, node)
        s = self.nodes.get(key)
        if s and (t <= s.t or (boot == s.boot and seq <= s.seq)):
            self.rejected_order += 1
            return None, []
        events = self.expire(run, t)
        if s is None or boot != s.boot:
            if s is None and len(self.nodes) >= self.capacity:
                self.nodes.popitem(last=False)
                self.evictions += 1
            s = self.nodes[key] = Node(boot)
        self.nodes.move_to_end(key)
        if s.seq >= 0:
            self.gaps += max(0, seq - s.seq - 1)
            dt = t - s.t
            if period is None and seq == s.seq + 1 and s.health != "FALLO":
                s.period = dt
            if dt > max(45, 2.5 * s.period) or s.health == "FALLO":
                s.filters = Filters()
                s.recent.clear()
                s.identical = 0
                s.last_values = None
                s.since = s.clear_since = None
                s.risk = s.alarm = False
                s.evidence = -math.inf
        if period is not None:
            s.period = period
        s.seq, s.t, s.clock = seq, t, clock
        s.identical = s.identical + 1 if v == s.last_values else 1
        s.last_values = v
        s.recent.append((v[0], v[2]))

        # Joint PM/temperature variability suppresses many single-channel spikes.
        def jitter(column):
            differences = [
                b[column] - a[column] for a, b in zip(s.recent, list(s.recent)[1:])
            ]
            mean = sum(differences) / len(differences)
            return sum((d - mean) ** 2 for d in differences) / len(differences)

        noise = len(s.recent) == 12 and jitter(1) > 1.05 and jitter(0) > 115
        health = "SOSPECHOSO" if s.identical >= 10 or noise else "OK"
        if health != s.health:
            events.append(
                self.event(
                    run,
                    node,
                    boot,
                    seq,
                    t,
                    "node_health",
                    health=health,
                    reason="frozen"
                    if s.identical >= 10
                    else "noise"
                    if noise
                    else "recovery",
                )
            )
            s.health = health
        x = s.filters.update(t, v)
        if self.mode == "rules":
            cls, score = "rules", None
            fire = x[0] >= 35.5 and x[2] >= 0.30 and (x[5] < 90 or x[4] > 1.5)
        else:
            cls, score = self.forest.predict(x)
            fire = score >= FIRE_SCORE and x[0] >= 18 and x[2] >= 0.36
        if fire:
            s.clear_since = None
            if s.since is None:
                s.since = t
            if t - s.since >= PERSIST:
                if s.health == "OK":
                    s.evidence = t
                else:
                    s.evidence = -math.inf
                info = dict(
                    predicted_class=cls,
                    fire_score=round(score, 4) if score is not None else None,
                    health=s.health,
                    pm25=round(v[0], 1),
                    pm10=round(v[1], 1),
                    method=self.mode,
                )
                if not s.risk:
                    events.append(
                        self.event(
                            run, node, boot, seq, t, "environmental_risk", **info
                        )
                    )
                    s.risk = True
                if not s.alarm:
                    for other in neighbours(node):
                        o = self.nodes.get((run, other))
                        if (
                            o
                            and o.health == "OK"
                            and 0 <= t - o.evidence <= NEIGHBOUR_TTL
                        ):
                            events.append(
                                self.event(
                                    run,
                                    node,
                                    boot,
                                    seq,
                                    t,
                                    "suspected_fire",
                                    neighbour=other,
                                    **info,
                                )
                            )
                            s.alarm = True
                            break
        else:
            s.since = None
            if s.clear_since is None:
                s.clear_since = t
            if t - s.clear_since >= 60:
                s.alarm = s.risk = False
                s.evidence = -math.inf
        self.accepted += 1
        return (cls, score), events
