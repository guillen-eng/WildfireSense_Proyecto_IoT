"""Hybrid RESISTO-anchored data provenance and offline regression tests."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from historical import ResistoReference, make_resisto_reading
from run import run_experiment, enforce_historical_coverage

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
# Docker mounts scenario/data read-only; local source tree fallback.
DOCKER_CSV = Path("/app/historical-data/resisto_sample.csv")
LOCAL_CSV = ROOT.parent / "scenario/data/resisto_sample.csv"
CSV = DOCKER_CSV if DOCKER_CSV.exists() else LOCAL_CSV


class HistoricalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = ResistoReference(CSV, CFG["steps"])

    def test_data_source_is_partial_humidity(self):
        audit = self.ref.audit
        self.assertEqual(audit["historical_sensors"], 5)
        self.assertEqual(audit["observed_temperature_samples"], 360)
        self.assertLess(audit["observed_humidity_samples"], 360)
        self.assertFalse(audit["humidity_reference_used_in_generator"])

    def test_virtual_timegrid_provenance_in_normal_mode(self):
        for i in range(1, 6):
            first = make_resisto_reading(CFG, i, 0, "normal", set(), self.ref)
            self.assertEqual(first["reference_temperature_origin"], "observed")
            self.assertTrue(first["reference_source_times"])
            last = make_resisto_reading(CFG, i, 71, "normal", set(), self.ref)
            self.assertEqual(last["reference_temperature_origin"], "synthetic_extension")
            self.assertIsNone(last["source_time"])
            self.assertEqual(last["reference_source_times"], [])
        self.assertGreater(self.ref.audit["temperature_point_origins"]["interpolated"], 0)
        self.assertGreater(self.ref.audit["temperature_point_origins"]["synthetic_extension"], 0)

    def test_additional_nodes_are_explicit_synthetic_replicas(self):
        first = make_resisto_reading(CFG, 51, 21, "normal", set(), self.ref)
        second = make_resisto_reading(CFG, 51, 21, "normal", set(), self.ref)
        self.assertEqual(first, second)
        self.assertTrue(first["historical_trace_reused"])
        self.assertIn("synthetic", first["measurement_provenance"]["air_temperature_c"])
        for key in ("relative_humidity_pct", "pm25_ug_m3", "co_ppm"):
            self.assertIn("synthetic", first["measurement_provenance"][key])

    def test_labels_never_enter_sensor_payload(self):
        msg = make_resisto_reading(CFG, 1, 48, "mixed_proxy", {"scale_0001"}, self.ref)
        serialized = json.dumps(msg).lower()
        for forbidden in ("synthetic_event", "affected_sensors", "fire_alarm", "event_start_step"):
            self.assertNotIn(forbidden, serialized)
        self.assertTrue(msg["test_only"])

    def test_mixed_signal_changes_four_variables(self):
        original = make_resisto_reading(CFG, 1, 48, "normal", set(), self.ref)["measurements"]
        changed = make_resisto_reading(CFG, 1, 48, "mixed_proxy", {"scale_0001"}, self.ref)["measurements"]
        self.assertGreater(changed["air_temperature_c"], original["air_temperature_c"])
        self.assertLess(changed["relative_humidity_pct"], original["relative_humidity_pct"])
        self.assertGreater(changed["pm25_ug_m3"], original["pm25_ug_m3"])
        self.assertGreater(changed["co_ppm"], original["co_ppm"])

    def test_offline_experiment_audit_and_no_mqtt(self):
        with tempfile.TemporaryDirectory() as temp:
            result, directory = run_experiment(CFG, 5, "normal", Path(temp), historical=self.ref)
            self.assertEqual(result["generated_messages"], 360)
            self.assertEqual(result["baseline"], "resisto_temperature")
            self.assertFalse(result["mqtt_publish_attempted"])
            self.assertFalse(result["mqtt_delivery_to_edge_verified"])
            audit = json.loads((directory / "historical_audit.json").read_text())
            self.assertEqual(audit["sha256"], self.ref.sha256)
            first = json.loads((directory / "readings.jsonl").read_text().splitlines()[0])
            self.assertIn("measurement_provenance", first)
            self.assertTrue((directory / "ground_truth.json").exists())

    def test_nonexistent_steps_rejected(self):
        with self.assertRaises(ValueError):
              def test_quality_gate_rejects_120_second_excessive_extension(self):
        with self.assertRaisesRegex(ValueError, "Too much synthetic extension"):
            enforce_historical_coverage(self.ref, 0.20)

    def test_30_second_cadence_uses_less_synthetic_extension(self):
        reference = ResistoReference(CSV, CFG["steps"], virtual_step_seconds=30,
                                     max_gap_seconds=300, seed=int(CFG["seed"]))
        self.assertEqual(reference.audit["temperature_point_origins"], {
            "observed": 10, "interpolated": 282, "synthetic_extension": 68
        })
        self.assertLessEqual(enforce_historical_coverage(reference, 0.20), 0.20)
        custom_cfg = dict(CFG, virtual_step_seconds=30)
        with tempfile.TemporaryDirectory() as temp:
            result, _ = run_experiment(custom_cfg, 5, "normal", Path(temp), historical=reference)
            self.assertEqual(result["virtual_step_seconds"], 30)
            self.assertEqual(result["historical_extension_fraction"], round(68 / 360, 5))

  ResistoReference(CSV, 73)

    def test_50_nodes_are_not_50_historical_sensors(self):
        with tempfile.TemporaryDirectory() as temp:
            result, directory = run_experiment(CFG, 50, "dust_control", Path(temp), historical=self.ref)
            self.assertEqual(result["generated_messages"], 3600)
            self.assertEqual(result["historical_template_sensors"], 5)
            self.assertTrue(result["additional_virtual_sensors_are_synthetic"])
            self.assertFalse(json.loads((directory / "ground_truth.json").read_text())["synthetic_event"])


if __name__ == "__main__":
    unittest.main()
