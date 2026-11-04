"""Tests del diagnóstico temporal sin cambios a MQTT ni al Edge."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from audit_alignment import audit_run, source_datetime, save_report


def write_run(root, run_id='example', offsets=(0, 0), missing=False, mismatch_virtual=False):
    folder = root / run_id
    folder.mkdir()
    readings = []
    for tick in range(3):
        for n, offset in enumerate(offsets):
            if missing and tick == 2 and n == 1:
                continue
            source = datetime(2024, 5, 8, 10, 0, tzinfo=timezone.utc) + timedelta(seconds=offset + tick * 37)
            virtual = datetime(2024, 5, 8, 12, 0, tzinfo=timezone.utc) + timedelta(seconds=tick * 120)
            if mismatch_virtual and n == 1 and tick == 1:
                virtual += timedelta(seconds=1)
            readings.append({'tick': tick, 'message': {
                'node_id': f'replay_{n+1:03}', 'source_time': source.isoformat(),
                'timestamp': virtual.isoformat(), 'measurements': {'air_temperature_c': 20}
            }})
    (folder / 'readings_sent.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in readings), encoding='utf-8')
    (folder / 'summary.json').write_text(json.dumps({'published': len(readings)}), encoding='utf-8')


class AlignmentTests(unittest.TestCase):
    def test_original_csv_time_zone_format(self):
        value = source_datetime('2024-05-08 17:20:08.000 +0200')
        self.assertEqual(value.isoformat(), '2024-05-08T15:20:08+00:00')

    def test_aligned_control_and_export(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_run(root)
            result = audit_run('example', root)
            self.assertTrue(result['is_suitable_for_naive_peer_comparison'])
            self.assertEqual(result['ticks_within_tolerance'], 3)
            self.assertEqual(result['virtual_gap_median_seconds'], 120)
            self.assertEqual(result['historical_gap_median_seconds'], 37)
            j, c = save_report([result], root)
            self.assertTrue(j.exists() and c.exists())

    def test_misaligned_sensors_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_run(root, offsets=(0, 3600))
            result = audit_run('example', root)
            self.assertFalse(result['is_suitable_for_naive_peer_comparison'])
            self.assertEqual(result['ticks_within_tolerance'], 0)
            self.assertEqual(result['median_tick_spread_min'], 60)

    def test_missing_ticks_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_run(root, missing=True)
            with self.assertRaisesRegex(ValueError, 'incompletos'):
                audit_run('example', root)

    def test_virtual_clock_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_run(root, mismatch_virtual=True)
            with self.assertRaisesRegex(ValueError, 'virtual distinto'):
                audit_run('example', root)

    def test_bad_run_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, 'RUN_ID'):
                audit_run('../secret', Path(td))


if __name__ == '__main__':
    unittest.main()
