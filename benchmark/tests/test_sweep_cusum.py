"""Comprobaciones de la evaluación pareada de controles y perturbaciones."""
import unittest
from sweep_cusum import assess_event, alarm_ticks


class PairedControlTests(unittest.TestCase):
    @staticmethod
    def samples(values):
        return [dict(tick=i, message={'node_id':'x', 'measurements':{'air_temperature_c':val}})
                for i, val in enumerate(values)]

    def test_cusum_alerts_on_sustained_shift(self):
        alarms = alarm_ticks(self.samples([20.]*20 + [22.]*8), 0.5, 8)
        self.assertEqual(alarms, {'x': 25})

    def test_same_tick_as_control_is_not_attributable(self):
        result = assess_event({'x': 45}, {'x': 45}, {'x': list(range(45, 55))}, 120)
        self.assertEqual(result['in_window'], ['x'])
        self.assertEqual(result['earlier_than_control'], [])

    def test_event_earlier_than_control_is_counted(self):
        result = assess_event({'x': 46}, {'x': 50}, {'x': list(range(45, 55))}, 120)
        self.assertEqual(result['earlier_than_control'], ['x'])
        self.assertEqual(result['virtual_delays_min'], {'x': 2})

    def test_after_event_not_counted(self):
        result = assess_event({'x': 56}, {}, {'x': list(range(45, 55))}, 120)
        self.assertEqual(result['in_window'], [])


if __name__ == '__main__':
    unittest.main()
