import unittest
from runner import fire_delta

class NormalControlTests(unittest.TestCase):
    def test_no_event_for_any_sensor_or_step(self):
        event = {"enabled": False, "start_step": 42, "duration_steps": 16,
                 "affected_sensors": ["replay_001", "replay_002"],
                 "second_sensor_delay_steps": 3,
                 "max_temperature_increase_c": 20.0}
        for step in range(72):
            for sensor in ("replay_001", "replay_002", "replay_003"):
                self.assertEqual(fire_delta(step, sensor, event, 8), 0.0)
