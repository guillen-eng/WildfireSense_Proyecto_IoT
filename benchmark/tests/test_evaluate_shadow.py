import json
import tempfile
import unittest
from pathlib import Path
from evaluate_shadow import load, compare

CTRL = '20261102T212100123456Z'
EVENT = '20261102T212101123456Z'


def write_json(path, object):
    path.write_text(json.dumps(object), encoding='utf-8')


def write_jsonl(path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')


class ShadowEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, perturbed in ((CTRL, False), (EVENT, True)):
            folder = self.root / name
            folder.mkdir()
            write_json(folder / 'ground_truth.json', {'virtual_step_seconds': 120, 'event_enabled': perturbed})
            write_json(folder / 'summary.json', {'run_id': name, 'published': 3})
            write_json(folder / 'shadow_summary.json', {'run_id': name, 'session_closed': True,
                                                       'readings_received': 3,
                                                       'detections_by_candidate': {'sensible': int(perturbed), 'conservador': 0}})
            rows = []
            for tick in range(3):
                increase = 4.0 if perturbed and tick >= 1 else 0.0
                rows.append({'tick': tick, 'injected_temperature_increase_c': increase,
                             'message': {'node_id': 'A', 'timestamp': f'2024-11-09T00:0{tick}:00Z',
                                         'measurements': {'air_temperature_c': 20 + increase}}})
            write_jsonl(folder / 'readings_sent.jsonl', rows)
            events = [{'candidate': 'sensible', 'node_id': 'A',
                       'reading_timestamp': '2024-11-09T00:01:00Z',
                       'shadow_only': True, 'run_id': name}] if perturbed else []
            write_jsonl(folder / 'shadow_events.jsonl', events)

    def test_deteccion_adelantada_en_evento(self):
        rows = compare(load(CTRL, self.root), load(EVENT, self.root))
        self.assertEqual(rows[0]['detected_in_window'], 1)
        self.assertEqual(rows[0]['earlier_than_control'], 1)
        self.assertEqual(rows[0]['delay_virtual_min_by_sensor'], {'A': 0})
        self.assertEqual(rows[1]['detected_in_window'], 0)

    def test_detecta_replay_no_pareado(self):
        p = self.root / EVENT / 'readings_sent.jsonl'
        items = [json.loads(x) for x in p.read_text().splitlines()]
        items[0]['message']['measurements']['air_temperature_c'] = 99
        write_jsonl(p, items)
        with self.assertRaises(ValueError):
            compare(load(CTRL, self.root), load(EVENT, self.root))

    def test_detecta_resumen_incoherente(self):
        p = self.root / EVENT / 'shadow_summary.json'
        report = json.loads(p.read_text())
        report['detections_by_candidate']['sensible'] = 2
        write_json(p, report)
        with self.assertRaises(ValueError):
            load(EVENT, self.root)
