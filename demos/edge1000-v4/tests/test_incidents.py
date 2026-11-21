"""Incidents are read-only, reproducible and distinct from alerts/SOS."""

import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer
import threading

from cloud.app import AlertStore, TOPIC, BrokerStatus, build_handler
from cloud.incidents import group_suspected_fire


def record(ident, node, minute=0, run="r1", decision="suspected_fire", score=0.9):
    return {
        "event_id": ident,
        "node_id": node,
        "type": "environmental_alert",
        "decision": decision,
        "run_id": run,
        "priority": "high",
        "fire_score": score,
        "generated_at": "2026-11-20T19:00:00+00:00",
        "reading_timestamp": f"2026-11-20T19:{minute:02d}:00+00:00" if minute < 60 else "2026-11-20T20:10:00+00:00",
        "test_only": True,
    }


class IncidentGroupingTest(unittest.TestCase):
    def test_adjacent_nodes_and_same_node_chain(self):
        events = [record("a", "node_0001", 0), record("b", "node_0002", 10), record("c", "node_0034", 20)]
        grouped = group_suspected_fire(events)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["alert_count"], 3)
        self.assertEqual(grouped[0]["node_count"], 3)
        self.assertEqual(grouped, group_suspected_fire(list(reversed(events))))

    def test_different_run_distant_and_late_events_are_separate(self):
        events = [
            record("a", "node_0001", 0, run="one"),
            record("b", "node_0002", 2, run="two"),
            record("c", "node_0999", 2, run="one"),
            record("d", "node_0001", 70, run="one"),
            record("e", "node_0001", 1, run="one", decision="environmental_risk"),
        ]
        self.assertEqual(len(group_suspected_fire(events)), 4)

    def test_missing_run_never_crosses_legacy_events(self):
        a, b = record("x", "node_0001"), record("y", "node_0002")
        del a["run_id"]
        del b["run_id"]
        self.assertEqual(len(group_suspected_fire([a, b])), 2)


class IncidentStorageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "cloud.sqlite"
        self.store = AlertStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_persistent_deduplicated_distinct_from_event_counts(self):
        a = record("a", "node_0049")
        b = record("b", "node_0050", minute=3)
        c = record("c", "node_0003", minute=3)
        pre = record("d", "node_0049", minute=1, decision="environmental_risk")
        for event in (a, b, c, pre):
            self.assertEqual(self.store.ingest(TOPIC, json.dumps(event).encode()), "inserted")
        self.assertEqual(self.store.ingest(TOPIC, json.dumps(a).encode()), "duplicate")
        stats = self.store.stats()
        self.assertEqual(stats["total_alerts"], 4)
        grouping = self.store.incidents()
        self.assertEqual(grouping["total_incidents"], 2)
        self.assertEqual(grouping["suspected_fire_events"], 3)
        self.assertEqual(grouping, AlertStore(self.path).incidents())

    def test_integration_real_engine_alerts(self):
        from edge.logic import Engine, READINGS, SOS
        from edge.transport import wire
        from lab.fleet import fleet
        engine = Engine()
        emitted = []
        for _, msg in fleet(nodes=5, cycles=48):
            topic = SOS if msg["type"] == "sos" else READINGS + msg["node_id"]
            _, events = engine.handle(topic, msg)
            for event in events:
                if event["type"] != "node_health":
                    emitted.append(event)
                    self.assertEqual(self.store.ingest(TOPIC, wire(event).encode()), "inserted")
        grouped = self.store.incidents()
        self.assertEqual(grouped["total_incidents"], 1)
        self.assertEqual(grouped["suspected_fire_events"],
                         sum(e["decision"] == "suspected_fire" for e in emitted))
        self.assertEqual(self.store.stats()["total_alerts"], len(emitted))

    def test_http_endpoint(self):
        self.store.ingest(TOPIC, json.dumps(record("a", "node_0496")).encode())
        status = BrokerStatus()
        server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(self.store, status))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/incidents") as response:
                j = json.load(response)
            self.assertEqual(j["total_incidents"], 1)
            self.assertEqual(j["incidents"][0]["first_node"], "node_0496")
            with self.assertRaises(HTTPError) as e:
                urlopen(f"http://127.0.0.1:{server.server_port}/api/incidents?limit=invalid")
            self.assertEqual(e.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
