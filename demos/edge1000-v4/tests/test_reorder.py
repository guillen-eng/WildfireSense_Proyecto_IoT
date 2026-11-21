import unittest

from edge.logic import SOS, READINGS
from edge.reorder import BoundedEventBuffer
from lab.robustness import evaluate


class ReorderingTests(unittest.TestCase):
    @staticmethod
    def make_msg(seq, sec=0):
        return dict(v=1, id=1, ts=(1800000000 + sec)*1000, seq=seq,
                    kind='periodic', values={'PM2.5': 10., 'PM10': 20.,
                                             'temperature': 23., 'humidity': 48.})

    @staticmethod
    def canonical(seq, sec):
        from edge.logic import adapt
        return adapt(ReorderingTests.make_msg(seq, sec))

    def test_orders_out_of_order_samples(self):
        b=BoundedEventBuffer(lateness_s=15)
        order=[]
        for arrival, seq, t in [(0,1,0), (10,3,20), (11,2,10), (21,4,30)]:
            order.extend(b.push(arrival, READINGS+'node_0001', self.canonical(seq,t)))
        order.extend(b.finish(30))
        self.assertEqual([x[2]['seq'] for x in order], [1,2,3,4])
        self.assertEqual(b.metrics()['late_beyond_window'], 0)

    def test_sos_bypasses_pending(self):
        b=BoundedEventBuffer(lateness_s=90)
        self.assertEqual(b.push(1, READINGS+'node_0001',self.canonical(1,0)),[])
        emergency=self.canonical(2,10)
        emergency['type']='sos'
        result=b.push(2,SOS,emergency)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0][0],2)
        self.assertEqual(result[0][1],SOS)
        self.assertEqual(b.metrics()['sos_bypassed'],1)

    def test_duplicates_and_missing_inbuffer(self):
        raws=[self.make_msg(i+1, i*10) for i in range(18)]
        direct=evaluate(raws, duplicates=0.4, jitter_s=16, seed=2)
        buffered=evaluate(raws, duplicates=0.4, jitter_s=16, seed=2, reorder_window_s=20)
        self.assertEqual(buffered['accepted_readings'],18)
        self.assertEqual(buffered['rejected_order_or_duplicate'],buffered['duplicated'])
        self.assertGreaterEqual(buffered['accepted_readings'], direct['accepted_readings'])

    def test_too_small_window_and_memory_limit_recorded(self):
        b=BoundedEventBuffer(100, max_pending=2)
        for i in range(6):
            b.push(i,READINGS+'node_0001',self.canonical(i+1,i*10))
        self.assertGreater(b.metrics()['buffer_overflows'],0)
        with self.assertRaises(ValueError):
            BoundedEventBuffer(-1)
        with self.assertRaises(ValueError):
            BoundedEventBuffer(10, max_pending=0)


if __name__=='__main__':
    unittest.main()
