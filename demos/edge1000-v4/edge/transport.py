import json
import math
import sqlite3
from pathlib import Path
from .logic import HEALTH

SUMMARY = "wildfiresense/cloud/analysis"
ACK = "wildfiresense/cloud/ack"
PING = "wildfiresense/edge/ping"
PONG = "wildfiresense/cloud/pong"
STATS = "wildfiresense/edge/status"
READY = "wildfiresense/edge/status/request"


def wire(obj):
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def aggregate(samples):
    return dict(
        n=len(samples),
        mean_pm25=round(sum(samples) / len(samples), 3),
        max_pm25=max(samples),
    )


def publish_size(topic, payload_bytes, qos):
    # MQTT 3.1.1 PUBLISH only. Remaining Length uses base-128 encoding.
    remaining = 2 + len(topic.encode()) + (2 if qos else 0) + payload_bytes
    length_bytes = 1
    v = remaining
    while v >= 128:
        length_bytes += 1
        v //= 128
    return 1 + length_bytes + remaining


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[math.ceil(q * len(ordered)) - 1], 3)


class Journal:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, topic TEXT, payload TEXT, confirmed INTEGER DEFAULT 0)"
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS pending ON events(confirmed)")

    def save(self, topic, event):
        with self.db:
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO events VALUES(?,?,?,?)",
                (event["event_id"], topic, wire(event), int(topic == HEALTH)),
            )
        return cursor.rowcount == 1

    def confirm(self, ident):
        with self.db:
            self.db.execute("UPDATE events SET confirmed=1 WHERE id=?", (ident,))

    def pending(self):
        return self.db.execute(
            "SELECT topic,payload FROM events WHERE confirmed=0 ORDER BY rowid LIMIT 150"
        ).fetchall()

    def backlog(self):
        return self.db.execute(
            "SELECT count(*) FROM events WHERE confirmed=0"
        ).fetchone()[0]
