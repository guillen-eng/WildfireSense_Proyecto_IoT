import unittest
from datetime import datetime, timezone, timedelta
from tools.benchmark_relative import (inject_one_sensor, indexed_series, first_positive_alert,
                                       is_attributable, analyze_group, split_groups)


def rows(n=16, rising=None, group='g', temperatures=None, time_gaps=False):
    base = datetime(2024,5,8,12,tzinfo=timezone.utc)
    ret=[]
    for i in range(n):
        minute = 2*i if not time_gaps else 2*i + (4 if i>=10 else 0)
        when=(base+timedelta(minutes=minute)).isoformat()
        for sensor, offset in [('a',0),('b',1),('c',2)]:
            temp=20+offset
            if temperatures and sensor in temperatures:
                temp=temperatures[sensor][i]
            if rising == sensor and i>=8:
                temp+=6
            ret.append({'group':group,'virtual_sensor':sensor,'aligned_time_utc':when,
                        'temperature_c':str(temp),'offset_seconds':'0','interpolated':'False'})
    return ret

class DetectorRelativePilotTests(unittest.TestCase):
    def test_only_target_sensor_is_modified(self):
        source=rows()
        modified=inject_one_sensor(source,'a',8)
        self.assertEqual(source[8*3]['temperature_c'],'20')
        self.assertEqual(float(modified[8*3]['temperature_c']),21)
        self.assertEqual(float(modified[13*3]['temperature_c']),26)
        self.assertEqual(modified[13*3+1]['temperature_c'],source[13*3+1]['temperature_c'])

    def test_no_alarm_in_stable_control(self):
        series=indexed_series(rows(),'test')
        self.assertTrue(all(first_positive_alert(s,2) is None for s in series.values()))

    def test_positive_relative_alert_on_single_warming(self):
        series=indexed_series(inject_one_sensor(rows(),'a',8),'test')
        self.assertIsNotNone(first_positive_alert(series['a'],3))
        self.assertIsNone(first_positive_alert(series['b'],3))
        self.assertIsNone(first_positive_alert(series['c'],3))

    def test_complete_group_evaluated(self):
        sums, details, skipped=analyze_group('test','g',rows(),thresholds=(3.,))
        self.assertIsNone(skipped)
        self.assertEqual(sums[0]['single_sensor_injection_trials'],3)
        self.assertEqual(sums[0]['control_sensors_with_alert'],0)
        self.assertEqual(sums[0]['trials_attributable_by_paired_control'],3)
        self.assertEqual(len(details),3)

    def test_same_index_as_control_not_attributable(self):
        self.assertFalse(is_attributable(9,9,8))
        self.assertFalse(is_attributable(7,None,8))
        self.assertTrue(is_attributable(9,11,8))

    def test_pair_only_is_excluded(self):
        paired=[r for r in rows() if r['virtual_sensor'] in ('a','b')]
        sums, details, skip=analyze_group('test','g',paired,thresholds=(3.,))
        self.assertEqual(sums,[])
        self.assertEqual(details,[])
        self.assertIn('menos de 3',skip['skipped'])

    def test_real_elapsed_time_used_with_gaps(self):
        s=rows(time_gaps=True)
        sums, details, _=analyze_group('test','g',s,thresholds=(3.,))
        self.assertEqual(len(details),3)
        found=[d for d in details if d['target_sensor']=='a'][0]
        self.assertTrue(found['paired_attributable'])
        self.assertGreater(found['paired_delay_minutes'],2*(found['event_first_alert_index']-8))

    def test_incomplete_tick_rejected(self):
        incomplete=rows()
        incomplete.pop()
        with self.assertRaises(ValueError): indexed_series(incomplete,'test')

    def test_split_groups(self):
        d=split_groups(rows())
        self.assertEqual(list(d),['g'])
        self.assertEqual(len(d['g']),48)

if __name__=='__main__': unittest.main()
