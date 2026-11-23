"""Verified labels, scenario truth, training export, nodes and zone summaries."""

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cloud.app import AlertStore, BrokerStatus, TOPIC, build_handler
from cloud.labels import BASE_MS
from cloud import readings as rd
from tests.test_readings import alert, batch

try:  # CI installs only the vendored MQTT client (no numpy/scikit-learn)
    from lab.train import reviewed_history
except ImportError:
    reviewed_history = None

T0_S = 3600  # fire start, seconds since scenario clock origin
ALARM_MIN = {"node_0496": 0, "node_0497": 4}


def iso_minute(minute):
    return f"2026-11-20T19:{minute:02d}:00+00:00"


class LabelsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AlertStore(Path(self.temp.name) / "c.sqlite")
        for ident, node, minute in (("a", "node_0496", 0), ("b", "node_0497", 4)):
            self.store.ingest(TOPIC, alert(ident, node, minute))
        self.incident = self.store.incidents()["incidents"][0]["incident_id"]

    def tearDown(self):
        self.temp.cleanup()

    def server(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(self.store, BrokerStatus()))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_port}"

    def post(self, base, path, body):
        req = Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urlopen(req) as r:
            return json.load(r)

    def test_manual_label_validation_and_override(self):
        base = self.server()
        for bad in (
            {"incident_id": self.incident, "label": "correct"},
            {"incident_id": self.incident, "label": "incorrect", "true_class": "slow_fire"},
            {"incident_id": self.incident, "label": "maybe"},
        ):
            with self.assertRaises(HTTPError) as err:
                self.post(base, "/api/labels", bad)
            self.assertEqual(err.exception.code, 400)
        with self.assertRaises(HTTPError) as err:
            self.post(base, "/api/labels", {"incident_id": "nope", "label": "incorrect"})
        self.assertEqual(err.exception.code, 404)
        self.post(base, "/api/labels", {"incident_id": self.incident, "label": "incorrect"})
        item = self.store.incidents()["incidents"][0]
        self.assertEqual(item["label"], {"label": "incorrect", "true_class": "normal", "source": "manual"})

    def test_scenario_truth_labels_and_manual_wins(self):
        base_ms = rd._ts_ms(iso_minute(0))
        dust = {"escenario": "polvo_tractor", "alarma_esperada": False, "t0_s": 0}
        self.assertEqual(self.store.load_truth("r1", dust), 1)
        label = self.store.incidents()["incidents"][0]["label"]
        self.assertEqual((label["label"], label["true_class"], label["source"]), ("incorrect", "dust", "scenario"))
        t0 = (base_ms - BASE_MS) // 1000 - 60  # fire starts before the first alarm
        fire = {"escenario": "fuego_lento", "alarma_esperada": True, "t0_s": t0}
        self.store.load_truth("r1", fire)
        label = self.store.incidents()["incidents"][0]["label"]
        self.assertEqual((label["label"], label["true_class"]), ("correct", "slow_fire"))
        early = {"escenario": "fuego_lento", "alarma_esperada": True, "t0_s": t0 + 3600}
        self.store.load_truth("r1", early)  # alarm before the fire existed
        label = self.store.incidents()["incidents"][0]["label"]
        self.assertEqual((label["label"], label["true_class"]), ("incorrect", "normal"))
        self.store.set_label(self.incident, "correct", "fast_fire")
        label = self.store.incidents()["incidents"][0]["label"]
        self.assertEqual((label["true_class"], label["source"]), ("fast_fire", "manual"))

    def test_export_is_accepted_by_train_and_excludes_ambiguous_gap(self):
        base = rd._ts_ms(iso_minute(0))
        items = []
        for n in (496, 497):
            for seq, minute in enumerate((-20, -15, -5, 1, 3, 5)):
                items.append(
                    {
                        "id": n, "ts": base + minute * 60_000, "seq": seq, "boot_id": "b",
                        "kind": "periodic",
                        "values": {"PM2.5": 90.0, "PM10": 140.0, "temperature": 30.0, "humidity": 40.0},
                    }
                )
        self.store.ingest_readings(batch(items))
        self.store.set_label(self.incident, "correct", "slow_fire")
        out = Path(self.temp.name) / "reviewed.jsonl"
        n = self.store.export_training(out)
        rows = [json.loads(line) for line in out.read_text().splitlines()]
        self.assertEqual(n, len(rows))
        classes = {}
        for row in rows:
            key = (row["message"]["node_id"], row["message"]["timestamp"][11:16])
            classes[key] = row["class"]
        self.assertEqual(classes[("node_0496", "18:40")], "normal")  # -20 min: clean context
        self.assertNotIn(("node_0496", "18:55"), classes)  # -5 min: ambiguous gap
        self.assertEqual(classes[("node_0496", "19:01")], "slow_fire")
        if reviewed_history is not None:  # train.py parser accepts the export
            self.assertEqual(len(list(reviewed_history(out))), len(rows))

    def test_unlabelled_incidents_are_not_exported(self):
        out = Path(self.temp.name) / "none.jsonl"
        self.assertEqual(self.store.export_training(out), 0)

    def test_nodes_zones_and_zone_summary(self):
        nodes = self.store.nodes()
        self.assertEqual(len(nodes), 1024)
        self.assertEqual(rd.grid_position("node_0496"), ("z_3_3", 15, 15))
        self.assertEqual(rd.grid_position(1025), None)
        good = {
            "event_id": "z1", "generated_at": "2026-11-20T19:00:00+00:00",
            "computed_by": "edge", "zone": "z_3_3", "from_ts": 1, "to_ts": 2,
            "n": 10, "mean_pm25": 20.0, "max_pm25": 80.0, "max_node_id": "node_0496",
        }
        self.assertEqual(self.store.ingest_summary(json.dumps(good).encode())[0], "inserted")
        cloud = {**good, "event_id": "z2", "computed_by": "cloud", "zone": "z_0_0",
                 "samples": [{"node_id": 1, "pm25": 5.0}, {"node_id": 2, "pm25": 9.0}]}
        for k in ("n", "mean_pm25", "max_pm25", "max_node_id"):
            cloud.pop(k)
        self.assertEqual(self.store.ingest_summary(json.dumps(cloud).encode())[0], "inserted")
        zones = {z["zone"]: z for z in self.store.zones()}
        self.assertEqual(zones["z_0_0"]["max_node_id"], "node_0002")
        self.assertEqual(zones["z_3_3"]["max_pm25"], 80.0)
        bad = {**good, "event_id": "z3", "zone": "bogus"}
        self.assertEqual(self.store.ingest_summary(json.dumps(bad).encode())[0], "invalid")
        legacy = {"event_id": "l1", "generated_at": "x", "computed_by": "edge",
                  "n": 3, "mean_pm25": 1.0, "max_pm25": 2.0}
        self.assertEqual(self.store.ingest_summary(json.dumps(legacy).encode())[0], "inserted")


if __name__ == "__main__":
    unittest.main()
