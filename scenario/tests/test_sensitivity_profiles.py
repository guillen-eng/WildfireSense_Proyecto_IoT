"""Comprobaciones: las configuraciones antiguas no se alteran."""
import json
import unittest
from pathlib import Path
from runner import fire_delta

HERE=Path(__file__).resolve().parents[1]

class SensitivityProfileTests(unittest.TestCase):
    def test_original_default_keeps_legacy_behavior(self):
        old={"start_step":42,"duration_steps":16,"affected_sensors":["replay_001","replay_002"],"second_sensor_delay_steps":3,"max_temperature_increase_c":20.0}
        self.assertAlmostEqual(fire_delta(42,"replay_001",old,8),5.0)
        self.assertAlmostEqual(fire_delta(45,"replay_001",old,8),20.0)

    def test_profiles_have_same_dataset_and_virtual_timing(self):
        profiles=[]
        for name in ('config_fuerte.json','config_suave.json','config_gradual.json'):
            profiles.append(json.loads((HERE/'configs'/name).read_text(encoding='utf8')))
        for item in profiles[1:]:
            self.assertEqual(item['dataset'],profiles[0]['dataset'])
            self.assertEqual(item['num_sensors'],profiles[0]['num_sensors'])
            self.assertEqual(item['total_steps'],profiles[0]['total_steps'])
            self.assertEqual(item['virtual_step_seconds'],profiles[0]['virtual_step_seconds'])

    def test_gradual_has_smaller_first_step_than_mild(self):
        mild=json.loads((HERE/'configs'/'config_suave.json').read_text(encoding='utf8'))
        slow=json.loads((HERE/'configs'/'config_gradual.json').read_text(encoding='utf8'))
        self.assertLess(fire_delta(42,'replay_001',slow['event'],8),fire_delta(42,'replay_001',mild['event'],8))
        self.assertEqual(fire_delta(42,'replay_003',slow['event'],8),0)
        self.assertEqual(fire_delta(71,'replay_001',slow['event'],8),0)

if __name__ == '__main__':
    unittest.main()
