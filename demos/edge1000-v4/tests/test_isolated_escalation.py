"""Option B: isolated node produces an unconfirmed high risk ONLY with strong temporal evidence."""

import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cloud.app import AlertStore, TOPIC
from edge.logic import ALERTS, DetectionPolicy, Engine
from edge.main import Gateway
from edge.transport import Journal


class ConstantForest:
    version = "fixture-fire-forest"

    def predict(self, x):
        return "slow_fire", 0.95


def simulate_isolated(policy, *, neighbours=False, rising=True, steps=45):
    engine = Engine(forest=ConstantForest(), policy=policy)
    result = []
    for i in range(steps):
        t = i * 10.0
        pm = 8.0 + (4.0 * i if rising else 0.0)
        x = (pm, max(pm, pm * 1.6), 23.0 + i * 0.03, 55.0)
        _pred, produced = engine.evaluate(
            "study", "node_0001", "boot", i + 1, t, x, period=10
        )
        result.extend(produced)
        if neighbours:
            _pred, produced = engine.evaluate(
                "study", "node_0002", "boot", i + 1, t,
                (8.0 + 0.02*i, 20.0 + 0.03*i, 23.0 + 0.01*i, 55.0), period=10
            )
            result.extend(produced)
    return result


class IsolatedPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = DetectionPolicy(isolated_enabled=True)

    def test_opt_in_never_changes_baseline(self):
        base = simulate_isolated(DetectionPolicy())
        self.assertNotIn("unconfirmed_fire_risk", [e["decision"] for e in base])

    def test_isolated_rising_evidence_yields_one_explicitly_unconfirmed_alert(self):
        events = simulate_isolated(self.policy)
        unconfirmed = [e for e in events if e["decision"] == "unconfirmed_fire_risk"]
        self.assertEqual(len(unconfirmed), 1)
        self.assertEqual(unconfirmed[0]["type"], "environmental_alert")
        self.assertEqual(unconfirmed[0]["priority"], "high")
        self.assertEqual(unconfirmed[0]["confirmation"], "unconfirmed")
        self.assertEqual(unconfirmed[0]["reason"], "no_fresh_healthy_neighbour")
        self.assertNotIn("neighbour", unconfirmed[0])
        self.assertNotIn("suspected_fire", [e["decision"] for e in events])

    def test_fresh_healthy_neighbour_without_fire_blocks_isolated_escalation(self):
        events = simulate_isolated(self.policy, neighbours=True)
        self.assertNotIn("unconfirmed_fire_risk", [e["decision"] for e in events])
        self.assertNotIn("suspected_fire", [e["decision"] for e in events])

    def test_no_sustained_drift_no_high_alarm(self):
        events = simulate_isolated(self.policy, rising=False)
        self.assertNotIn("unconfirmed_fire_risk", [e["decision"] for e in events])

    def test_stronger_gates_prevent_escalation(self):
        for cfg in [
            DetectionPolicy(isolated_enabled=True, isolated_min_fire_score=0.99),
            DetectionPolicy(isolated_enabled=True, isolated_min_pm25_rise=100.0),
            DetectionPolicy(isolated_enabled=True, isolated_persist_s=500.0),
        ]:
            with self.subTest(cfg=cfg):
                events = simulate_isolated(cfg)
                self.assertNotIn("unconfirmed_fire_risk", [e["decision"] for e in events])

    def test_invalid_isolation_settings_rejected(self):
        for bad in [
            {"isolated_enabled": 1},
            {"isolated_persist_s": 20},
            {"isolated_min_fire_score": 0.60},
            {"isolated_min_pm25_rise": -1},
            {"isolated_min_pm25_rise": math.nan},
        ]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                DetectionPolicy(**bad)

    def test_output_persists_in_existing_cloud_contract_without_cloud_edits(self):
        alarm = next(e for e in simulate_isolated(self.policy)
                     if e["decision"] == "unconfirmed_fire_risk")
        with tempfile.TemporaryDirectory() as root:
            journal = Journal(Path(root)/"edge.sqlite")
            self.assertTrue(journal.save(ALERTS, alarm))
            self.assertEqual(journal.backlog(), 1)
            store = AlertStore(Path(root)/"cloud.sqlite")
            encoded = json.dumps(alarm).encode()
            self.assertEqual(store.ingest(TOPIC, encoded), "inserted")
            self.assertEqual(store.alerts()[0]["payload"]["confirmation"], "unconfirmed")
            journal.confirm(alarm["event_id"])
            self.assertEqual(journal.backlog(), 0)
            journal.db.close()

    def test_gateway_flag_defaults_off_and_opt_in_works(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, {"EDGE_DB": str(Path(root)/"e.sqlite")},
                            clear=False):
                with patch.dict(os.environ, {"EDGE_ISOLATED_ESCALATION": "0"}):
                    g = Gateway()
                    self.assertFalse(g.engine.policy.isolated_enabled)
                    g.store.db.close()
                    g.client.disconnect()
                with patch.dict(os.environ, {"EDGE_ISOLATED_ESCALATION": "1"}):
                    g = Gateway()
                    self.assertTrue(g.engine.policy.isolated_enabled)
                    g.store.db.close()
                    g.client.disconnect()


if __name__ == "__main__":
    unittest.main()
