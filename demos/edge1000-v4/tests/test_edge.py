import json
import tempfile
import unittest
from pathlib import Path
from cloud.analysis import summarize
from edge.logic import Engine, READINGS, SOS, adapt, neighbours, checked_node
from edge.model import ROOT, Forest
from edge.logic import ALERTS
from edge.transport import Journal, publish_size
from lab.promote import promote
from lab.fleet import fleet


class EdgeTests(unittest.TestCase):
    def setUp(self):
        self.edge = Engine()
        self.raw = dict(
            v=1,
            id=496,
            ts=1784073600000,
            seq=1,
            boot_id="A",
            kind="periodic",
            values={"PM2.5": 8, "PM10": 15, "temperature": 23, "humidity": 57},
        )
        self.topic = READINGS + checked_node(496)

    def test_node_identity_and_causality(self):
        self.assertIsNotNone(self.edge.handle(self.topic, self.raw)[0])
        self.assertIsNone(self.edge.handle(self.topic, self.raw)[0])
        self.assertIsNone(
            self.edge.handle(
                self.topic, {**self.raw, "ts": self.raw["ts"] - 1, "seq": 3}
            )[0]
        )
        self.assertIsNotNone(
            self.edge.handle(
                self.topic, {**self.raw, "ts": self.raw["ts"] + 10000, "boot_id": "B"}
            )[0]
        )
        self.assertEqual(self.edge.accepted, 2)
        self.assertEqual(self.edge.rejected_order, 2)

    def test_label_injection_topic_and_invalid_pm(self):
        for topic, r in [
            (self.topic, {**self.raw, "label": 1}),
            (READINGS + "node_0001", self.raw),
            (
                self.topic,
                {**self.raw, "values": {**self.raw["values"], "PM2.5": float("nan")}},
            ),
        ]:
            with self.assertRaises(ValueError):
                self.edge.handle(topic, r)

    def test_sos_independent_even_before_any_history(self):
        raw = {**self.raw, "kind": "emergency"}
        events = self.edge.handle(SOS, raw)[1]
        self.assertEqual(events[0]["priority"], "critical")
        self.assertEqual(self.edge.handle(SOS, raw)[1], [])
        self.assertFalse(self.edge.nodes)
        self.assertEqual(len(self.edge.handle(SOS, {**raw, "seq": 2})[1]), 1)

    def test_silence_and_recovery(self):
        msg = {**adapt(self.raw), "period_s": 60}
        self.edge.handle(self.topic, msg)
        t = self.raw["ts"] / 1000
        self.assertFalse(self.edge.expire("raw-live", t + 46))
        self.assertEqual(self.edge.expire("raw-live", t + 151)[0]["health"], "FALLO")
        recovered = self.edge.handle(
            self.topic, {**self.raw, "seq": 2, "ts": int((t + 165) * 1000)}
        )[1]
        self.assertEqual(recovered[-1]["health"], "OK")

    def test_grid_edges_and_fire_confirmation(self):
        self.assertNotIn("node_0033", list(neighbours("node_0032")))
        events = []
        for _, m in fleet(nodes=5, cycles=48):
            _, out = self.edge.handle(
                SOS if m["type"] == "sos" else READINGS + m["node_id"], m
            )
            events.extend(out)
        alarms = [e for e in events if e["decision"] == "suspected_fire"]
        self.assertTrue(alarms)
        self.assertTrue(all(e["neighbour"] in neighbours(e["node_id"]) for e in alarms))

    def test_store_and_forward_survives_restart(self):
        event = {"event_id": "abc", "decision": "sos_alert"}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "edge.sqlite"
            j = Journal(path)
            j.save(ALERTS, event)
            j.db.close()
            j = Journal(path)
            j.save(ALERTS, event)
            self.assertEqual(len(j.pending()), 1)
            j.confirm("abc")
            self.assertEqual(j.backlog(), 0)
            j.db.close()

    def test_same_aggregate_for_both_routes(self):
        meta = {"event_id": "x", "generated_at": "now"}
        a = summarize(dict(**meta, computed_by="cloud", samples=[3, 7]))
        b = summarize(dict(**meta, computed_by="edge", mean_pm25=5, max_pm25=7, n=2))
        self.assertEqual(
            [a[k] for k in ("mean_pm25", "max_pm25", "n")],
            [b[k] for k in ("mean_pm25", "max_pm25", "n")],
        )

    def test_mqtt_header_boundary(self):
        self.assertEqual(publish_size("x", 124, 0), 129)
        self.assertEqual(publish_size("x", 125, 0), 131)

    def test_promote_and_reject_corrupt_model(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "forest.json"
            promote(ROOT / "models/forest.json", dest)
            self.assertEqual(Forest(dest).version, self.edge.forest.version)
            bad = json.loads(dest.read_text())
            bad["version"] = "bad"
            other = Path(d) / "bad.json"
            other.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                promote(other, dest)
            self.assertEqual(Forest(dest).version, self.edge.forest.version)
