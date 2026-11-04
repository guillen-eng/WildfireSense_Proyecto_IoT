import copy
import json
import tempfile
import unittest
from pathlib import Path

from generator import affected_ids, make_reading, validate_config
from rules import ExperimentalFusion
from run import run_experiment

BASE = json.loads((Path(__file__).resolve().parents[1] / 'config.json').read_text())


class LoadLabTests(unittest.TestCase):
    def test_5_50_100_500_nodes_are_allowed(self):
        for n in (5, 50, 100, 500):
            with self.subTest(n=n):
                validate_config(BASE, n, 'mixed_proxy')

    def test_affected_selection_scales_and_is_deterministic(self):
        for n in (5, 50, 100, 500):
            picked = affected_ids(BASE, n, 'smoke_proxy')
            self.assertEqual(picked, affected_ids(BASE, n, 'smoke_proxy'))
            self.assertEqual(len(picked), min(n, max(2, round(n * 0.04))))
            self.assertEqual(len(picked), len(set(picked)))

    def test_message_has_units_and_no_hidden_label(self):
        r = make_reading(BASE, 1, 45, 'smoke_proxy', {'scale_0001'})
        self.assertEqual(set(r['measurements']), {
            'air_temperature_c', 'relative_humidity_pct', 'pm25_ug_m3', 'co_ppm'})
        self.assertNotIn('fire_alarm', json.dumps(r).lower())
        self.assertNotIn('affected', json.dumps(r).lower())
        self.assertTrue(r['test_only'])

    def test_deterministic_readings(self):
        a = make_reading(BASE, 10, 49, 'mixed_proxy', {'scale_0010'})
        b = make_reading(BASE, 10, 49, 'mixed_proxy', {'scale_0010'})
        self.assertEqual(a, b)

    def test_unaffected_sensor_has_identical_baseline(self):
        a = make_reading(BASE, 1, 48, 'normal', set())
        b = make_reading(BASE, 1, 48, 'mixed_proxy', {'scale_0002'})
        self.assertEqual(a['measurements'], b['measurements'])

    def test_smoke_changes_pm_and_co_not_temperature(self):
        target = {'scale_0001'}
        normal = make_reading(BASE, 1, 49, 'normal', set())
        smoke = make_reading(BASE, 1, 49, 'smoke_proxy', target)
        self.assertEqual(normal['measurements']['air_temperature_c'], smoke['measurements']['air_temperature_c'])
        self.assertEqual(normal['measurements']['relative_humidity_pct'], smoke['measurements']['relative_humidity_pct'])
        self.assertGreater(smoke['measurements']['pm25_ug_m3'], normal['measurements']['pm25_ug_m3'])
        self.assertGreater(smoke['measurements']['co_ppm'], normal['measurements']['co_ppm'])

    def test_experimental_fusion_has_warmup(self):
        det = ExperimentalFusion(BASE['experimental_fusion'])
        r = make_reading(BASE, 1, 49, 'smoke_proxy', {'scale_0001'})
        for _ in range(BASE['experimental_fusion']['baseline_samples']):
            self.assertIsNone(det.evaluate(r))

    def test_dust_is_negative_case(self):
        with tempfile.TemporaryDirectory() as temp:
            summary, path = run_experiment(BASE, 50, 'dust_control', Path(temp))
            self.assertEqual(summary['synthetic_event_sensors'], 0)
            self.assertEqual(summary['unexpected_detection_sensors'], 0)
            self.assertEqual(summary['generated_messages'], 50 * 72)
            self.assertFalse(json.loads((path/'ground_truth.json').read_text())['synthetic_event'])

    def test_smoke_detects_synthetic_signals_only(self):
        with tempfile.TemporaryDirectory() as temp:
            summary, path = run_experiment(BASE, 5, 'smoke_proxy', Path(temp))
            self.assertEqual(summary['generated_messages'], 360)
            self.assertEqual(summary['detected_event_sensors'], 2)
            self.assertEqual(summary['unexpected_detection_sensors'], 0)
            self.assertEqual(len((path/'readings.jsonl').read_text().splitlines()), 360)
            truth = json.loads((path/'ground_truth.json').read_text())
            self.assertEqual(len(truth['affected_sensors']), 2)

    def test_normal_has_no_false_alarm_in_this_synthetic_case(self):
        with tempfile.TemporaryDirectory() as temp:
            summary, _ = run_experiment(BASE, 5, 'normal', Path(temp))
            self.assertEqual(summary['experimental_rule_detections'], 0)

    def test_threshold_config_changes_results(self):
        altered = copy.deepcopy(BASE)
        altered['experimental_fusion']['thresholds']['pm25_increase_ug_m3'] = 10000.0
        with tempfile.TemporaryDirectory() as temp:
            summary, _ = run_experiment(altered, 5, 'smoke_proxy', Path(temp))
            self.assertEqual(summary['detected_event_sensors'], 0)

    def test_mqtt_topics_and_no_label_even_in_publish(self):
        attempts = []
        with tempfile.TemporaryDirectory() as temp:
            summary, _ = run_experiment(
                BASE, 5, 'smoke_proxy', Path(temp),
                publisher=lambda topic, payload: attempts.append((topic, json.loads(payload))))
        self.assertEqual(len(attempts), 360)
        self.assertTrue(all(x[0].startswith('wildfiresense/readings/scale_') for x in attempts))
        self.assertTrue(all('synthetic_event' not in x[1] and 'affected_sensors' not in x[1] for x in attempts))
        self.assertTrue(summary['mqtt_publish_attempted'])
        self.assertFalse(summary['mqtt_delivery_to_edge_verified'])

    def test_bad_config_is_rejected(self):
        altered = copy.deepcopy(BASE)
        altered['event']['ramp_steps'] = 0
        with self.assertRaises(ValueError):
            validate_config(altered, 5, 'normal')


if __name__ == '__main__':
    unittest.main()
