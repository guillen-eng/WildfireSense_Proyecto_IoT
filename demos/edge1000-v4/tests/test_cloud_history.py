"""Cloud V4 regression tests: reliable IDs, summary history, and HTTP API.

Uses only the Python standard library and a temporary SQLite database.
Does not start MQTT, change Edge, or require an Internet connection.
"""

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from cloud.app import AlertStore, BrokerStatus, TOPIC, build_handler


def as_wire(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def alert(event_id="alert-1", node="node_0001", **extra):
    return {
        "event_id": event_id,
        "node_id": node,
        "type": "environmental_alert",
        "priority": "high",
        "generated_at": "2026-11-22T12:00:00+00:00",
        **extra,
    }


def summary(event_id="summary-1", samples=None):
    return {
        "event_id": event_id,
        "computed_by": "cloud",
        "samples": [5.0, 9.0] if samples is None else samples,
        "generated_at": "2026-11-22T12:00:00+00:00",
    }


class CloudHistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.directory.name) / "cloud.sqlite3"
        self.store = AlertStore(self.db_path)

    def tearDown(self):
        self.directory.cleanup()

    def test_same_alert_id_and_different_content_is_conflict(self):
        one = alert()
        self.assertEqual(self.store.ingest(TOPIC, as_wire(one)), "inserted")
        self.assertEqual(self.store.ingest(TOPIC, as_wire(one)), "duplicate")
        self.assertEqual(
            self.store.ingest(TOPIC, as_wire(alert(node="node_0020"))),
            "conflict",
        )
        self.assertEqual(self.store.stats()["total_alerts"], 1)
        self.assertEqual(self.store.alerts()[0]["node_id"], "node_0001")
        self.assertEqual(
            AlertStore(self.db_path).ingest(TOPIC, as_wire(one)), "duplicate"
        )

    def test_alert_json_key_order_is_not_a_content_conflict(self):
        one = alert()
        self.assertEqual(self.store.ingest(TOPIC, as_wire(one)), "inserted")
        self.assertEqual(
            self.store.ingest(TOPIC, json.dumps(one, sort_keys=True).encode()),
            "duplicate",
        )

    def test_summary_is_saved_idempotently_with_correct_values(self):
        packet = as_wire(summary())
        self.assertEqual(
            self.store.ingest_summary(packet), ("inserted", "summary-1")
        )
        self.assertEqual(
            self.store.ingest_summary(packet), ("duplicate", "summary-1")
        )
        self.assertEqual(self.store.stats()["total_summaries"], 1)
        self.assertEqual(self.store.summaries()[0]["n"], 2)
        self.assertEqual(self.store.summaries()[0]["mean_pm25"], 7.0)
        self.assertEqual(
            AlertStore(self.db_path).summaries(), self.store.summaries()
        )

    def test_conflicting_summary_id_does_not_replace_original(self):
        self.assertEqual(
            self.store.ingest_summary(as_wire(summary())), ("inserted", "summary-1")
        )
        self.assertEqual(
            self.store.ingest_summary(as_wire(summary(samples=[5.0, 20.0]))),
            ("conflict", "summary-1"),
        )
        self.assertEqual(self.store.summaries()[0]["max_pm25"], 9.0)
        self.assertEqual(self.store.stats()["total_summaries"], 1)

    def test_edge_computed_summary_can_be_persisted(self):
        item = {
            "event_id": "edge-summary",
            "computed_by": "edge",
            "n": 3,
            "mean_pm25": 11.2,
            "max_pm25": 17.0,
            "generated_at": "2026-11-22T12:00:00Z",
        }
        self.assertEqual(
            self.store.ingest_summary(as_wire(item)), ("inserted", "edge-summary")
        )
        self.assertEqual(self.store.summaries()[0]["computed_by"], "edge")

    def test_reject_bad_summaries_without_writing(self):
        invalid = [
            b"not json",
            b"[]",
            b"x" * 65537,
            as_wire({**summary(), "event_id": ""}),
            as_wire({**summary(), "event_id": 42}),
            as_wire({**summary(), "generated_at": 42}),
            as_wire({**summary(), "samples": []}),
            as_wire({**summary(), "samples": [float("nan")]}),
            as_wire({**summary(), "samples": [True]}),
            as_wire({**summary(), "computed_by": "unknown"}),
        ]
        for packet in invalid:
            with self.subTest(packet=packet[:40]):
                self.assertEqual(self.store.ingest_summary(packet), ("invalid", None))
        self.assertEqual(self.store.stats()["total_summaries"], 0)

    def test_summary_history_orders_by_receipt_and_caps_result(self):
        for i in range(4):
            self.assertEqual(
                self.store.ingest_summary(as_wire(summary(f"s-{i}")))[0], "inserted"
            )
        self.assertEqual(
            [x["event_id"] for x in self.store.summaries(limit=2)],
            ["s-3", "s-2"],
        )


class CloudHistoryHttpTests(unittest.TestCase):
    """HTTP tests use an isolated temporary database and server."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.directory.name) / "cloud.sqlite3"
        self.store = AlertStore(self.db_path)
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0), build_handler(self.store, BrokerStatus())
        )
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.httpd.server_port)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.directory.cleanup()

    def get(self, path):
        with urlopen(self.url + path, timeout=5) as response:
            return json.load(response)

    def test_summaries_endpoint_and_stats(self):
        self.store.ingest_summary(as_wire(summary("one")))
        self.store.ingest_summary(as_wire(summary("two")))
        data = self.get("/api/summaries?limit=1")
        self.assertEqual([x["event_id"] for x in data["summaries"]], ["two"])
        self.assertEqual(self.get("/api/stats")["total_summaries"], 2)
        self.assertEqual(self.get("/api/stats")["total_alerts"], 0)

    def test_summaries_query_validation(self):
        for path in ("/api/summaries?limit=0", "/api/summaries?limit=oops"):
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as cm:
                    self.get(path)
                self.assertEqual(cm.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
