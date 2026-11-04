"""Tests reproducibles del análisis de bytes de payload MQTT."""
import json
import tempfile
import unittest
from pathlib import Path

from traffic_report import analyze_run, mqtt_json_payload_bytes, save_report

RUN_ID = '20261102T211009997139Z'


def create_run(root, run_id=RUN_ID, event=False, alerts=None):
    alerts = alerts or []
    folder = root / run_id
    folder.mkdir()
    messages = [
        {'node_id': 'replay_001', 'measurements': {'air_temperature_c': 21.5}},
        {'node_id': 'replay_001', 'measurements': {'air_temperature_c': 22.0}},
    ]
    (folder / 'readings_sent.jsonl').write_text(
        ''.join(json.dumps({'tick': i, 'injected_temperature_increase_c': 0,
                            'message': m}, ensure_ascii=False) + '\n'
                for i, m in enumerate(messages)), encoding='utf-8')
    (folder / 'alerts_received.jsonl').write_text(
        ''.join(json.dumps({'received_at': 'now', 'alarm': alarm}, ensure_ascii=False) + '\n'
                for alarm in alerts), encoding='utf-8')
    (folder / 'summary.json').write_text(json.dumps({
        'run_id': run_id, 'published': len(messages),
        'alerts_total_received': len(alerts),
        'environmental_alerts_received': sum(a.get('type') == 'environmental_alert' for a in alerts),
    }), encoding='utf-8')
    (folder / 'ground_truth.json').write_text(json.dumps({
        'run_id': run_id, 'event_enabled': event,
        'affected_sensors': ['replay_001'] if event else [],
    }), encoding='utf-8')
    return folder, messages


class TrafficReportTests(unittest.TestCase):
    def test_bytes_are_payload_only_utf8(self):
        m = {'área': 'Málaga', 'temperature': 20}
        self.assertEqual(mqtt_json_payload_bytes(m), len(json.dumps(m, ensure_ascii=False).encode('utf-8')))

    def test_normal_run_no_alerts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder, messages = create_run(root)
            res = analyze_run(RUN_ID, root=root)
            self.assertEqual(res['readings_published'], 2)
            self.assertEqual(res['official_alerts_received'], 0)
            self.assertEqual(res['hypothetical_payload_reduction_pct'], 100)
            self.assertFalse(res['event_without_official_environmental_alert'])
            self.assertEqual(res['readings_payload_bytes'], sum(map(mqtt_json_payload_bytes, messages)))

    def test_event_without_alarm_is_flagged_not_success(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            create_run(root, event=True)
            res = analyze_run(RUN_ID, root=root)
            self.assertTrue(res['event_without_official_environmental_alert'])
            self.assertEqual(res['hypothetical_message_reduction_pct'], 100)

    def test_alert_payload_and_export(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            alarm = {'type': 'environmental_alert', 'node_id': 'replay_001', 'priority': 'high'}
            create_run(root, event=True, alerts=[alarm])
            result = analyze_run(RUN_ID, root=root)
            self.assertEqual(result['official_alerts_received'], 1)
            self.assertEqual(result['environmental_alerts_received'], 1)
            self.assertEqual(result['alerts_payload_bytes'], mqtt_json_payload_bytes(alarm))
            self.assertEqual(result['hypothetical_message_reduction_pct'], 50)
            jpath, cpath = save_report([result], root=root)
            self.assertTrue(jpath.is_file())
            self.assertTrue(cpath.is_file())
            self.assertEqual(json.loads(jpath.read_text(encoding='utf-8'))['results'][0]['run_id'], RUN_ID)

    def test_corrupted_count_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder, _ = create_run(root)
            summary = json.loads((folder / 'summary.json').read_text())
            summary['published'] = 3
            (folder / 'summary.json').write_text(json.dumps(summary))
            with self.assertRaisesRegex(ValueError, 'publicaciones'):
                analyze_run(RUN_ID, root=root)


if __name__ == '__main__':
    unittest.main()
