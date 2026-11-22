"""High-background robustness: never invent corroboration from shared high PM."""

import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from edge.logic import DetectionPolicy, Engine
from edge.main import Gateway


class AlwaysFire:
    version = "test-always-fire"

    def predict(self, features):
        # Artificial high fire scores ensure the temporal gate itself is tested;
        # this deliberately does NOT model actual wildfire physics.
        return "slow_fire", 0.96


def replay(policy, *, trend=False, warming=False, nodes=("node_0001", "node_0002")):
    engine = Engine(forest=AlwaysFire(), policy=policy)
    events = []
    for i in range(65):
        for node in nodes:
            # Shared constant high PM: legacy model would confuse it with fire.
            pm = 50.0 + (i * 5.0 if trend else 0)
            _, made = engine.evaluate(
                "gate-test", node, "boot", i + 1, i * 10.0,
                (pm, 1.5 * pm, 25.0 + (0.6 * i if warming else 0.0), 55.0), period=10,
            )
            events.extend(made)
    return [e for e in events if e["decision"] == "suspected_fire"]


class CorroborationTrendTests(unittest.TestCase):
    def test_default_is_exactly_legacy_for_constant_high_pm(self):
        baseline = replay(DetectionPolicy(), trend=False)
        self.assertGreater(len(baseline), 0)
        self.assertEqual(
            [e["event_id"] for e in baseline],
            [e["event_id"] for e in replay(DetectionPolicy(), trend=False)],
        )

    def test_opt_in_blocks_corroborated_alarm_on_constant_high_pm(self):
        policy = DetectionPolicy(corroboration_trend_enabled=True)
        self.assertEqual(replay(policy, trend=False), [])

    def test_opt_in_detects_rising_pm_at_two_neighbours(self):
        policy = DetectionPolicy(
            corroboration_trend_enabled=True,
            corroboration_min_pm25_rise=4.0,
            corroboration_trend_ttl_s=300.0,
        )
        alarms = replay(policy, trend=True)
        self.assertGreaterEqual(len(alarms), 1)
        self.assertEqual(alarms[0]["corroboration_filter"], "dual_pm25_trend")
        self.assertTrue(alarms[0]["neighbour"])

    def test_temperature_is_independent_conditional_signal(self):
        policy = DetectionPolicy(
            corroboration_trend_enabled=True,
            corroboration_min_pm25_rise=4.0,
            corroboration_min_temp_rise=0.5,
        )
        self.assertEqual(replay(policy, trend=True, warming=False), [])
        self.assertTrue(replay(policy, trend=True, warming=True))

    def test_no_spatial_confirm_with_single_node(self):
        policy = DetectionPolicy(corroboration_trend_enabled=True)
        self.assertEqual(replay(policy, trend=True, nodes=("node_0001",)), [])

    def test_invalid_policy_values_rejected(self):
        for kwargs in (
            {"corroboration_trend_enabled": 1},
            {"corroboration_min_pm25_rise": math.nan},
            {"corroboration_trend_ttl_s": math.inf},
            {"corroboration_trend_enabled": True, "corroboration_min_pm25_rise": 0.0},
            {"corroboration_trend_enabled": True, "corroboration_trend_ttl_s": 0.0},
            {"corroboration_min_temp_rise": -0.5},
            {"corroboration_min_temp_rise": math.nan},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                DetectionPolicy(**kwargs)

    def test_gateway_refuses_unvalidated_filter_and_keeps_v4_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"EDGE_DB": str(Path(tmp)/"edge.sqlite"),
                   "EDGE_CORROBORATION_TREND_GATE": "1",
                   "EDGE_ISOLATED_ESCALATION": "0"}
            with patch.dict(os.environ, env, clear=False):
                with self.assertRaisesRegex(ValueError, "NOT approved"):
                    Gateway()
            with patch.dict(os.environ, {**env,
                                         "EDGE_CORROBORATION_TREND_GATE": "0"},
                            clear=False):
                g = Gateway()
                self.assertFalse(g.engine.policy.corroboration_trend_enabled)
                self.assertFalse(g.engine.policy.isolated_enabled)
                g.client.disconnect()
                g.store.db.close()


if __name__ == "__main__":
    unittest.main()
