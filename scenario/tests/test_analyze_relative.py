import unittest
from datetime import datetime, timedelta, timezone
from tools.analyze_relative import analyse_rows


def rows(temps, group='g', offset=0):
    base = datetime(2024, 5, 8, 12, tzinfo=timezone.utc)
    result = []
    for i, measured in enumerate(temps):
        t = (base + timedelta(minutes=2*i)).isoformat()
        for sensor, value in measured.items():
            result.append({'group':group,'virtual_sensor':sensor,'aligned_time_utc':t,
                           'temperature_c':str(value),'offset_seconds':str(offset),
                           'interpolated':'False'})
    return result


class RelativeAnalysisTests(unittest.TestCase):
    def test_common_warming_cancels(self):
        original = [{'a':20+i, 'b':22+i, 'c':24+i} for i in range(10)]
        data, summary = analyse_rows(rows(original), 'test')
        self.assertEqual(len(data),30)
        self.assertTrue(all(abs(r['change_from_baseline_c']) < 1e-6 for r in data))

    def test_local_warming_changes_relative(self):
        values = [{'a':20+ (6 if i>=6 else 0), 'b':20, 'c':20} for i in range(10)]
        data, summary = analyse_rows(rows(values), 'test')
        a = [r for r in data if r['sensor']=='a']
        self.assertEqual(a[-1]['change_from_baseline_c'],6)
        self.assertEqual(a[0]['change_from_baseline_c'],0)

    def test_pair_not_attributable(self):
        values = [{'a':20, 'b':20+(5 if i>=6 else 0)} for i in range(10)]
        data, summary = analyse_rows(rows(values),'test')
        self.assertTrue(all(r['pair_only_ambiguous'] for r in data))
        self.assertEqual({s['sensor']:s['final_change_c'] for s in summary},{'a':-5,'b':5})

    def test_incomplete_tick_rejected(self):
        vals = rows([{'a':20,'b':22} for i in range(10)])
        vals.pop()
        with self.assertRaises(ValueError): analyse_rows(vals,'test')

    def test_interpolation_rejected(self):
        vals=rows([{'a':20,'b':22} for i in range(10)])
        vals[0]['interpolated']='True'
        with self.assertRaises(ValueError): analyse_rows(vals,'test')

    def test_not_enough_slots(self):
        _, summary=analyse_rows(rows([{'a':20,'b':22} for i in range(4)]),'test')
        self.assertEqual(summary[0]['status'],'insuficiente')

    def test_empty_file_not_claim_detection(self):
        data, summary=analyse_rows([], 'test')
        self.assertEqual(data, [])
        self.assertEqual(summary, [])


if __name__ == '__main__': unittest.main()
