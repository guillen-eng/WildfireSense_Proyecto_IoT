"""WildfireSense local central receiver: MQTT QoS 1 -> durable SQLite -> HTTP UI.

This is a local Cloud *emulator* on the Docker network, not an Internet cloud.
No sensor readings are subscribed to or stored; only official Edge alerts.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

LOGGER = logging.getLogger("wildfiresense.cloud")
TOPIC = "wildfiresense/edge/alerts"
ALLOWED_TYPES = frozenset({"environmental_alert", "sos_alert"})
MAX_PAYLOAD_BYTES = 65536


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AlertStore:
    """Separate, short-lived SQLite connections for MQTT and HTTP threads."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_hash TEXT NOT NULL UNIQUE,
                    node_id TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    generated_at TEXT,
                    received_at TEXT NOT NULL,
                    edge_processing_ms REAL,
                    payload_json TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_node ON alerts(node_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type)")

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=10000")
            with conn:
                yield conn
        finally:
            conn.close()

    def ingest(self, topic: str, payload: bytes) -> str:
        """Returns inserted, duplicate or invalid. Hash avoids QoS1 duplicates."""
        if topic != TOPIC or not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_PAYLOAD_BYTES:
            return "invalid"
        try:
            decoded = json.loads(payload.decode("utf-8"))
            if not isinstance(decoded, dict):
                return "invalid"
            typ = decoded.get("type")
            node = decoded.get("node_id")
            if typ not in ALLOWED_TYPES or not isinstance(node, str) or not 0 < len(node) <= 128:
                return "invalid"
            prio = decoded.get("priority", "unknown")
            if not isinstance(prio, str) or len(prio) > 64:
                return "invalid"
            generated = decoded.get("generated_at")
            if generated is not None and (not isinstance(generated, str) or len(generated) > 128):
                return "invalid"
            latency = decoded.get("edge_processing_ms")
            if latency is not None and (isinstance(latency, bool) or not isinstance(latency, (int, float)) or not 0 <= latency < 1e9):
                return "invalid"
            canonical = json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            return "invalid"
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with self.connect() as conn:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO alerts
                   (event_hash,node_id,alert_type,priority,generated_at,received_at,edge_processing_ms,payload_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (digest, node, typ, prio, generated, utc_now(), latency, canonical),
            )
        return "inserted" if cursor.rowcount == 1 else "duplicate"

    def alerts(self, limit: int = 100, node_id: str | None = None, alert_type: str | None = None):
        limit = max(1, min(200, int(limit)))
        where, args = [], []
        if node_id is not None:
            where.append("node_id = ?")
            args.append(node_id)
        if alert_type is not None:
            where.append("alert_type = ?")
            args.append(alert_type)
        query = "SELECT * FROM alerts"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, args).fetchall()
        results = []
        for row in rows:
            obj = dict(row)
            obj["payload"] = json.loads(obj.pop("payload_json"))
            obj.pop("event_hash")
            results.append(obj)
        return results

    def stats(self):
        with self.connect() as conn:
            rows = conn.execute("SELECT alert_type, COUNT(*) n FROM alerts GROUP BY alert_type").fetchall()
            last = conn.execute("SELECT received_at FROM alerts ORDER BY id DESC LIMIT 1").fetchone()
        counts = {r["alert_type"]: r["n"] for r in rows}
        return {
            "total_alerts": sum(counts.values()),
            "environmental_alerts": counts.get("environmental_alert", 0),
            "sos_alerts": counts.get("sos_alert", 0),
            "last_received_at": last["received_at"] if last else None,
        }


class BrokerStatus:
    def __init__(self):
        self.connected = threading.Event()
        self.start_time = utc_now()
        self.last_error = None


def build_handler(store: AlertStore, status: BrokerStatus):
    dashboard = Path(__file__).with_name("dashboard.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        server_version = "WildfireSenseControl/1.0"

        def respond(self, code, body: bytes, content_type="application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                uri = urlparse(self.path)
                query = parse_qs(uri.query)
                if uri.path in {"/", "/index.html"}:
                    return self.respond(200, dashboard, "text/html; charset=utf-8")
                if uri.path == "/api/health":
                    data = {"service": "wildfiresense-cloud-local", "mqtt_connected": status.connected.is_set(), "started_at": status.start_time}
                elif uri.path == "/api/stats":
                    data = {**store.stats(), "mqtt_connected": status.connected.is_set()}
                elif uri.path == "/api/alerts":
                    raw_limit = query.get("limit", ["100"])[0]
                    if len(raw_limit) > 4 or not raw_limit.isdigit() or int(raw_limit) == 0:
                        return self.json_error(400, "limit debe ser entero de 1 a 200")
                    node_id = query.get("node_id", [None])[0]
                    typ = query.get("type", [None])[0]
                    if node_id is not None and len(node_id) > 128:
                        return self.json_error(400, "node_id demasiado largo")
                    if typ is not None and typ not in ALLOWED_TYPES:
                        return self.json_error(400, "type desconocido")
                    data = {"alerts": store.alerts(min(int(raw_limit), 200), node_id, typ)}
                else:
                    return self.json_error(404, "no encontrado")
                return self.respond(200, json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"))
            except (OSError, sqlite3.Error) as exc:
                LOGGER.exception("HTTP database error: %s", exc)
                return self.json_error(503, "base de datos no disponible")

        def json_error(self, code, message):
            return self.respond(code, json.dumps({"error": message}).encode())

        def log_message(self, fmt, *args):
            LOGGER.info("HTTP %s %s", self.address_string(), fmt % args)

    return Handler


def serve_http(store: AlertStore, status: BrokerStatus, host="0.0.0.0", port=8080):
    server = ThreadingHTTPServer((host, port), build_handler(store, status))
    LOGGER.info("HTTP_READY %s:%s", host, server.server_port)
    server.serve_forever()


def run_mqtt(store: AlertStore, status: BrokerStatus, host: str, port: int):
    import paho.mqtt.client as mqtt

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            status.connected.clear()
            LOGGER.error("MQTT_CONNECT_FAILED %s", reason_code)
            return
        result, mid = client.subscribe(TOPIC, qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            status.connected.clear()
            LOGGER.error("MQTT_SUBSCRIBE_FAILED rc=%s", result)
            return
        LOGGER.info("MQTT_CONNECTED subscription_requested=%s qos=1", TOPIC)

    def on_subscribe(client, userdata, mid, reason_code_list, properties):
        if any(getattr(reason, "is_failure", False) for reason in reason_code_list):
            status.connected.clear()
            LOGGER.error("MQTT_SUBACK_FAILED %s", reason_code_list)
            return
        status.connected.set()
        LOGGER.info("MQTT_SUBSCRIBED topic=%s qos=1", TOPIC)

    def on_disconnect(client, userdata, flags, reason_code, properties):
        status.connected.clear()
        LOGGER.warning("MQTT_DISCONNECTED %s", reason_code)

    def on_message(client, userdata, msg):
        try:
            result = store.ingest(msg.topic, msg.payload)
            if result == "inserted":
                LOGGER.info("ALERT_STORED topic=%s bytes=%s", msg.topic, len(msg.payload))
            elif result == "invalid":
                LOGGER.warning("ALERT_REJECTED topic=%s", msg.topic)
        except sqlite3.Error:
            LOGGER.exception("ALERT_STORE_ERROR database write failed")
            # Paho will still ACK QoS1; do not claim this is lossless under DB failure.

    while True:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="wildfiresense-central-receiver")
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_subscribe = on_subscribe
        client.on_message = on_message
        try:
            LOGGER.info("MQTT_CONNECTING %s:%s", host, port)
            client.connect(host, port, keepalive=60)
            client.loop_forever(retry_first_connection=True)
        except (OSError, ValueError) as exc:
            status.connected.clear()
            LOGGER.error("MQTT_RETRY %s", exc)
            time.sleep(3)
        finally:
            status.connected.clear()
            try:
                client.disconnect()
            except OSError:
                pass


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = AlertStore(os.environ.get("CLOUD_DB_PATH", "/app/data/alerts.sqlite3"))
    status = BrokerStatus()
    mqtt_thread = threading.Thread(
        target=run_mqtt,
        args=(store, status, os.environ.get("MQTT_HOST", "mosquitto"), int(os.environ.get("MQTT_PORT", "1883"))),
        daemon=True,
        name="mqtt-subscriber",
    )
    mqtt_thread.start()
    serve_http(store, status, port=int(os.environ.get("HTTP_PORT", "8080")))


if __name__ == "__main__":
    main()
