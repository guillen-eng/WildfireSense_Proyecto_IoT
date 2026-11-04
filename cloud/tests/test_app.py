import json
from concurrent.futures import ThreadPoolExecutor
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from app import AlertStore, BrokerStatus, TOPIC, build_handler


def payload(node="replay_001", typ="environmental_alert", **extra):
    return json.dumps({"type": typ, "priority": "high", "node_id": node,
                       "generated_at": "2026-11-02T20:00:00+00:00", **extra}).encode()


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "data" / "alerts.sqlite3"
        self.store = AlertStore(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_store_alarm_and_stats(self):
        self.assertEqual(self.store.ingest(TOPIC, payload()), "inserted")
        stats = self.store.stats()
        self.assertEqual(stats["total_alerts"], 1)
        self.assertEqual(stats["environmental_alerts"], 1)
        self.assertEqual(self.store.alerts()[0]["node_id"], "replay_001")

    def test_store_sos_and_filter(self):
        self.store.ingest(TOPIC, payload("SOS_01", "sos_alert", priority="critical"))
        self.store.ingest(TOPIC, payload())
        self.assertEqual(self.store.stats()["sos_alerts"], 1)
        self.assertEqual(len(self.store.alerts(node_id="SOS_01")), 1)
        self.assertEqual(len(self.store.alerts(alert_type="sos_alert")), 1)

    def test_dedup_qos1_and_json_order(self):
        one = payload()
        two = json.dumps(json.loads(one), sort_keys=True).encode()
        self.assertEqual(self.store.ingest(TOPIC, one), "inserted")
        self.assertEqual(self.store.ingest(TOPIC, one), "duplicate")
        self.assertEqual(self.store.ingest(TOPIC, two), "duplicate")
        self.assertEqual(self.store.stats()["total_alerts"], 1)

    def test_persists_after_store_restart(self):
        self.store.ingest(TOPIC, payload())
        another = AlertStore(self.db)
        self.assertEqual(another.stats()["total_alerts"], 1)

    def test_reject_invalid_topic_and_payload(self):
        bad = [("some/other/topic", payload()), (TOPIC, b"not json"),
               (TOPIC, b"[]"), (TOPIC, b"{}"),
               (TOPIC, b"x" * 65537), (TOPIC, payload(node="")),
               (TOPIC, payload(edge_processing_ms=-10))]
        for topic, body in bad:
            self.assertEqual(self.store.ingest(topic, body), "invalid")
        self.assertEqual(self.store.stats()["total_alerts"], 0)

    def test_limit_and_order(self):
        for i in range(8):
            self.store.ingest(TOPIC, payload(node=f"s{i}"))
        self.assertEqual([a["node_id"] for a in self.store.alerts(limit=2)], ["s7", "s6"])

    def test_realistic_edge_alert_payload(self):
        actual_shape = {
            "type": "environmental_alert", "priority": "high", "node_id": "replay_001",
            "measurement": "air_temperature_c", "unit": "C", "observed_value": 31.0,
            "threshold_exceeded": 25.0, "z_score": 10.0,
            "reason": "two_consecutive_statistical_anomalies", "test_only": True,
            "edge_processing_ms": 0.636, "reading_timestamp": "2024-11-09T01:26:00+00:00",
            "generated_at": "2026-11-02T14:43:27.082475+00:00",
        }
        self.assertEqual(self.store.ingest(TOPIC, json.dumps(actual_shape).encode()), "inserted")
        saved = self.store.alerts()[0]
        self.assertEqual(saved["edge_processing_ms"], 0.636)
        self.assertTrue(saved["payload"]["test_only"])
        self.assertEqual(saved["payload"]["reading_timestamp"], actual_shape["reading_timestamp"])

    def test_concurrent_ingest(self):
        def write(i):
            return self.store.ingest(TOPIC, payload(node=f"sensor_{i}"))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(write, range(80)))
        self.assertEqual(results.count("inserted"), 80)
        self.assertEqual(self.store.stats()["total_alerts"], 80)

    def test_store_robust_to_quotes(self):
        self.store.ingest(TOPIC, payload(node="abc' OR 1=1 --"))
        self.assertEqual(len(self.store.alerts(node_id="abc' OR 1=1 --")), 1)
        self.assertEqual(len(self.store.alerts(node_id="abc")), 0)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AlertStore(Path(self.tmp.name) / "alerts.sqlite3")
        self.status = BrokerStatus()
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(self.store, self.status))
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.http.server_port}"

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def get_json(self, uri):
        with urlopen(self.base + uri, timeout=4) as response:
            return json.load(response)

    def test_dashboard_renders(self):
        with urlopen(self.base + "/", timeout=4) as response:
            self.assertIn("Centro de control", response.read().decode())

    def test_api_health_connection(self):
        self.assertFalse(self.get_json("/api/health")["mqtt_connected"])
        self.status.connected.set()
        self.assertTrue(self.get_json("/api/health")["mqtt_connected"])

    def test_alerts_endpoint_filters_and_stats(self):
        self.store.ingest(TOPIC, payload("node_1"))
        self.store.ingest(TOPIC, payload("SOS_01", "sos_alert"))
        self.assertEqual(self.get_json("/api/stats")["total_alerts"], 2)
        self.assertEqual(len(self.get_json("/api/alerts?type=sos_alert")["alerts"]), 1)
        self.assertEqual(len(self.get_json("/api/alerts?node_id=node_1")["alerts"]), 1)
        self.assertEqual(len(self.get_json("/api/alerts?limit=1")["alerts"]), 1)

    def test_invalid_query_and_missing_path(self):
        for uri, expected in [("/api/alerts?limit=0", 400), ("/api/alerts?limit=abc", 400),
                              ("/api/alerts?type=other", 400), ("/nope", 404)]:
            with self.assertRaises(HTTPError) as cm:
                urlopen(self.base + uri, timeout=4)
            self.assertEqual(cm.exception.code, expected)


if __name__ == "__main__":
    unittest.main()
