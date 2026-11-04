import unittest
from diagnose_drift import compare_pair


def run(event, different=False, missing=False):
    c = {"replay_001": {t: {"temp": 20.0 - .1*t, "injection": 0.0} for t in range(72)}}
    for t in range(72):
        if event and 42 <= t < 58:
            c['replay_001'][t]['injection'] = 6.0
            c['replay_001'][t]['temp'] += 6.0
    if missing:
        del c['replay_001'][50]
    return {
        'summary': {'event_enabled': event},
        'truth': {'dataset': 'A' if not different else 'B', 'virtual_step_seconds': 120,
                  'start_step': 42, 'duration_steps': 16},
        'by_sensor': c,
    }


class TrendTests(unittest.TestCase):
    def test_paired_cooling_and_injection(self):
        r = compare_pair(run(False), run(True))[0]
        self.assertTrue(r['afectado'])
        self.assertLess(r['tendencia_control_c'], 0)
        self.assertAlmostEqual(r['inyeccion_media_c'], 6.0)
        self.assertAlmostEqual(r['evento_vs_baseline_c'], r['tendencia_control_c'] + 6, places=3)

    def test_rejects_two_events(self):
        with self.assertRaises(ValueError):
            compare_pair(run(True), run(True))

    def test_rejects_non_paired_datasets(self):
        with self.assertRaises(ValueError):
            compare_pair(run(False), run(True, different=True))

    def test_rejects_missing_steps(self):
        with self.assertRaises(ValueError):
            compare_pair(run(False), run(True, missing=True))


if __name__ == '__main__':
    unittest.main()
