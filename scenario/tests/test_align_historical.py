"""Alineación temporal-espacial: sin inventar muestras ni borrar originales."""
import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tools.align_historical import (
    parse_time, distance_m, partition_spatial_groups,
    align_group, read_source, run_one,
)

BASE=datetime(2024,5,8,12,0,tzinfo=timezone.utc)


def sample(node, seconds, lat, lon):
    return {'sensor':node,'source_sensor':node,'time':BASE+timedelta(seconds=seconds),
            'temp':23.0+seconds/1000,'latlon':(lat,lon)}


class AlignTests(unittest.TestCase):
    def test_timezone_is_respected(self):
        self.assertEqual(parse_time('2024-05-08 17:20:08.000 +0200').hour,15)

    def test_spatial_complete_link_no_chain(self):
        by={'a':[sample('a',0,37.0,-6.000)],
            'b':[sample('b',0,37.0,-5.996)],
            'c':[sample('c',0,37.0,-5.992)]}
        groups=partition_spatial_groups(by,500)
        self.assertEqual(sorted(map(len,groups)),[1,2])
        for group in groups:
            for x in group:
                for y in group:
                    self.assertLessEqual(distance_m(by[x][0]['latlon'],by[y][0]['latlon']),500)

    def test_selects_real_samples_nearest(self):
        by={'a':[sample('a',-20,37,-6),sample('a',100,37,-6),sample('a',220,37,-6),sample('a',340,37,-6)],
            'b':[sample('b',20,37,-6),sample('b',140,37,-6),sample('b',260,37,-6),sample('b',380,37,-6)]}
        rows,candidates=align_group(by,['a','b'],120,60)
        self.assertEqual(candidates,2)  # Interseccion empieza 12:00:20.
        self.assertEqual(len(rows),4)
        self.assertTrue(all(row['interpolated'] is False for row in rows))
        self.assertEqual(len({(r['virtual_sensor'],r['original_time_utc']) for r in rows}),4)
        self.assertTrue(all(abs(r['offset_seconds'])<=60 for r in rows))

    def test_excludes_missing_time_no_imputation(self):
        by={'a':[sample('a',0,37,-6),sample('a',120,37,-6),sample('a',240,37,-6)],
            'b':[sample('b',0,37,-6),sample('b',240,37,-6)]}
        rows,candidates=align_group(by,['a','b'],120,60)
        self.assertEqual(candidates,3)
        self.assertEqual(len(rows),4)
        self.assertEqual({r['aligned_time_utc'] for r in rows}, {BASE.isoformat(),(BASE+timedelta(seconds=240)).isoformat()})

    def test_reject_duplicate_historical_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'data.csv'
            with path.open('w',newline='',encoding='utf8') as f:
                w=csv.writer(f);w.writerow(['virtual_sensor','source_sensor','source_time','temperature_c','latitude','longitude'])
                for node in ('a','b'):
                    for s in (0,0):w.writerow([node,node,(BASE+timedelta(seconds=s)).isoformat(),20,37,-6])
            with self.assertRaisesRegex(ValueError,'duplicado'):
                read_source(path)

    def test_real_sample_source_files_aligned_without_modification(self):
        data=Path(__file__).resolve().parents[1]/'data'
        if not (data/'zenodo_holdout_mayo.csv').exists():
            self.skipTest('CSV del proyecto no disponible')
        with tempfile.TemporaryDirectory() as temp:
            r=run_one('mayo',data,Path(temp))
            self.assertEqual(sum(g['num_sensors'] for g in r['groups']),5)
            self.assertGreater(r['output_rows'],0)
            self.assertTrue((Path(temp)/'alineado_mayo.csv').exists())


if __name__=='__main__':unittest.main()
