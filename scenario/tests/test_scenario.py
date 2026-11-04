import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner import fire_delta, load_replay, make_message

class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.event={"start_step":42,"duration_steps":16,"affected_sensors":["replay_001","replay_002"],"second_sensor_delay_steps":3,"max_temperature_increase_c":20.0}
    def test_normal_then_fire_then_recovery(self):
        self.assertEqual(fire_delta(30,"replay_001",self.event,8),0)
        self.assertGreater(fire_delta(43,"replay_001",self.event,8),0)
        self.assertEqual(fire_delta(66,"replay_001",self.event,8),0)
    def test_other_sensors_not_affected(self):
        self.assertEqual(fire_delta(50,"replay_003",self.event,8),0)
    def test_second_sensor_delay(self):
        self.assertGreater(fire_delta(42,"replay_001",self.event,8),0)
        self.assertEqual(fire_delta(42,"replay_002",self.event,8),0)
        self.assertGreater(fire_delta(45,"replay_002",self.event,8),0)
    def test_message_has_no_fire_label(self):
        row={'virtual_sensor':'replay_001','source_sensor':'fw_123','source_time':'2024-11-09','temperature_c':'19.0','humidity_percent':''}
        msg=make_message(row,step=42,virtual_time='t',temp_increase=10)
        self.assertEqual(msg['measurements']['air_temperature_c'],29.0)
        self.assertNotIn('fire',msg)
        self.assertNotIn('injected_temperature_increase_c',msg)
    def test_dataset_has_five_sensors(self):
        path=Path(__file__).resolve().parents[1]/'data/resisto_sample.csv'
        data=load_replay(str(path),5)
        self.assertEqual(len(data),5)
        self.assertTrue(all(len(x)==72 for x in data.values()))

if __name__=='__main__':unittest.main()
