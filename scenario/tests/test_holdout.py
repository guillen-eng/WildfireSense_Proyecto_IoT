"""Tests de nuevos periodos históricos fuera de la muestra usada para ajustar CUSUM."""
import csv
import json
import unittest
from collections import Counter
from pathlib import Path
from runner import load_replay, fire_delta, make_message
ROOT=Path(__file__).resolve().parents[1]

class HoldoutTests(unittest.TestCase):
    def test_both_extracts_have_five_complete_sensors(self):
        for name in ('mayo','octubre'):
            data=load_replay(str(ROOT/'data'/f'zenodo_holdout_{name}.csv'),5)
            self.assertEqual(list(data),sorted(data))
            self.assertEqual(len(data),5)
            self.assertTrue(all(len(seq)==72 for seq in data.values()))
    def test_dates_are_different_from_training_date(self):
        for name,date in [('mayo','2024-05-08'),('octubre','2024-10-31')]:
            rows=load_replay(str(ROOT/'data'/f'zenodo_holdout_{name}.csv'),5)
            self.assertTrue(all(row['source_time'].startswith(date) for seq in rows.values() for row in seq))
    def test_control_does_not_inject_temperature(self):
        for name in ('mayo','octubre'):
            cfg=json.loads((ROOT/'configs'/f'config_holdout_{name}_normal.json').read_text())
            for node in cfg['event']['affected_sensors']:
                self.assertEqual(fire_delta(45,node,cfg['event'],cfg['recovery_steps']),0)
    def test_gradual_does_inject_temperature(self):
        for name in ('mayo','octubre'):
            cfg=json.loads((ROOT/'configs'/f'config_holdout_{name}_gradual.json').read_text())
            self.assertGreater(fire_delta(44,'replay_001',cfg['event'],cfg['recovery_steps']),0)
            self.assertEqual(fire_delta(44,'replay_002',cfg['event'],cfg['recovery_steps']),0)
    def test_mqtt_payload_has_no_ground_truth(self):
        row=load_replay(str(ROOT/'data'/'zenodo_holdout_mayo.csv'),5)['replay_001'][0]
        msg=make_message(row,step=0,virtual_time='2024-05-08T17:00:00+02:00',temp_increase=0,source_label='zenodo_field_replay')
        self.assertEqual(msg['source'],'zenodo_field_replay')
        self.assertNotIn('fire_alert_status',msg)
        self.assertNotIn('event_enabled',msg)
        self.assertNotIn('injected_temperature_increase_c',msg)
    def test_exact_config_references(self):
        for name in ('mayo','octubre'):
            for mode in ('normal','gradual'):
                cfg=json.loads((ROOT/'configs'/f'config_holdout_{name}_{mode}.json').read_text())
                self.assertEqual(cfg['source_label'],'zenodo_field_replay')
                self.assertTrue((ROOT/cfg['dataset']).exists())
                self.assertEqual(cfg['event']['enabled'],mode=='gradual')

if __name__=='__main__': unittest.main()
