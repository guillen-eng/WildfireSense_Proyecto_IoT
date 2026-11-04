"""Reproduce los extractos de holdout a partir del archivo CSV original.
Uso: python scenario/tools/build_holdouts.py RUTA_AL_CSV_ORIGINAL
No se usa en Docker, los CSV pequeños se suministran ya preparados.
"""
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

CASE = {
    'mayo': ('2024-05-08','437c652a-4884-4a85-ac3f-e5c2f4b22881','17:00:00','20:00:00'),
    'octubre': ('2024-10-31','59eb92f3-2ce1-40e2-b9f7-b','10:00:00','13:00:00'),
}

def build(source, folder):
    source=Path(source)
    folder=Path(folder)
    manifest=json.loads((folder/'holdout_manifest.json').read_text(encoding='utf-8'))
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != manifest['source_sha256']:
        raise ValueError('El archivo de origen no coincide con el SHA-256 documentado')
    grouped={n:defaultdict(list) for n in CASE}
    with source.open(newline='',encoding='utf-8') as inp:
        for row in csv.DictReader(inp):
            for name,(day,site,start,end) in CASE.items():
                if row['time'][:10]!=day or row['site_id']!=site or not(start<=row['time'][11:19]<end) or row['fire_alert_status']!='0': continue
                try: t=float(row['temperature_c'])
                except ValueError: continue
                if 0<=t<=55: grouped[name][row['sensor_ns_id']].append(row)
    for name, sensors in grouped.items():
        selected=[]
        for sensor, recs in sensors.items():
            seq=[]; seen=set()
            for row in sorted(recs,key=lambda r:(r['time'],int(r['id']))):
                if row['time'] in seen: continue
                seen.add(row['time']);seq.append(row)
            if len(seq)>=72:selected.append((sensor,seq[:72]))
        selected=sorted(selected,key=lambda x:x[0])[:5]
        if len(selected)!=5:raise ValueError('No hay cinco sensores aptos')
        dest=folder/f'zenodo_holdout_{name}.csv'
        with dest.open('w',newline='',encoding='utf-8') as out:
            w=csv.DictWriter(out,fieldnames=['virtual_sensor','source_sensor','source_time','temperature_c','humidity_percent','latitude','longitude']);w.writeheader()
            for i,(sensor,seq) in enumerate(selected,start=1):
                for row in seq:
                    h=float(row['humidity_percent'])
                    w.writerow(dict(virtual_sensor=f'replay_{i:03d}',source_sensor=sensor,source_time=row['time'],temperature_c=row['temperature_c'],humidity_percent=row['humidity_percent'] if 0<=h<=100 else '',latitude=row['latitude'],longitude=row['longitude']))
        if hashlib.sha256(dest.read_bytes()).hexdigest()!=manifest['cases'][name]['csv_sha256']:
            raise ValueError(f'El extracto {name} no coincide con el original documentado')
        print(f'{name}: {dest} - 360 lecturas, hash verificado')
if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit('Uso: python scenario/tools/build_holdouts.py <fuente.csv>')
    build(sys.argv[1],Path(__file__).resolve().parents[1]/'data')
