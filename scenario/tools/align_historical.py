"""Alineacion OBSERVACIONAL de muestras historicas por tiempo y proximidad.

NO modifica los datos fuente, el reloj virtual, MQTT ni algoritmos.
Elige muestras reales cercanas en tiempo (sin interpolacion) y grupos
con distancia espacial maxima entre CUALQUIER par de sensores.
Los datos alineados NO representan incendios medidos.
"""
import argparse
import bisect
import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATASETS = {
    'noviembre': 'resisto_sample.csv',
    'mayo': 'zenodo_holdout_mayo.csv',
    'octubre': 'zenodo_holdout_octubre.csv',
}


def parse_time(s):
    try:
        d = datetime.strptime(s, '%Y-%m-%d %H:%M:%S.%f %z')
    except ValueError:
        d = datetime.fromisoformat(s)
    if not d.tzinfo or d.utcoffset() is None:
        raise ValueError('Marca temporal sin zona horaria')
    return d.astimezone(timezone.utc)


def distance_m(a, b):
    """Haversine; proximidad aproximada, NO equivalencia ambiental."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    s = math.sin((lat2 - lat1) / 2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000 * 2 * math.atan2(math.sqrt(s), math.sqrt(max(0, 1 - s)))


def read_source(path):
    by = defaultdict(list)
    with Path(path).open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            node = row['virtual_sensor']
            temp = float(row['temperature_c'])
            lat, lon = float(row['latitude']), float(row['longitude'])
            if not math.isfinite(temp) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError('Dato fisico no valido')
            by[node].append({
                'sensor': node,
                'source_sensor': row['source_sensor'],
                'time': parse_time(row['source_time']),
                'temp': temp,
                'latlon': (lat, lon),
            })
    if len(by) < 2:
        raise ValueError('Se necesitan al menos dos sensores')
    for node, series in by.items():
        series.sort(key=lambda row: row['time'])
        if len({r['source_sensor'] for r in series}) != 1:
            raise ValueError(f'{node}: mezcla de sensores fisicos')
        if any(distance_m(series[0]['latlon'],r['latlon']) > 25 for r in series):
            raise ValueError(f'{node}: ubicacion varía >25 m; revisar movilidad')
        if any(a['time'] == b['time'] for a,b in zip(series,series[1:])):
            raise ValueError(f'{node}: timestamp historico duplicado')
    return dict(by)


def partition_spatial_groups(by, max_distance_m=500):
    """Fusion aglomerativa complete-link: TODOS los pares dentro del umbral.

    Devuelve grupos sin solapes; grupos unitarios se mantienen como excluidos.
    """
    names = sorted(by)
    coords = {n: by[n][0]['latlon'] for n in names}
    groups = [[n] for n in names]
    while True:
        possibilities=[]
        for i in range(len(groups)):
            for j in range(i+1,len(groups)):
                dmax = max(distance_m(coords[x], coords[y]) for x in groups[i] for y in groups[j])
                if dmax <= max_distance_m:
                    possibilities.append((dmax,i,j))
        if not possibilities: break
        _,i,j = min(possibilities)
        groups[i] = sorted(groups[i] + groups[j])
        del groups[j]
    groups.sort(key=lambda group: group[0])
    return groups


def nearest_index(times, timestamp, tolerance_s, forbidden):
    ix = bisect.bisect_left(times, timestamp)
    possible = []
    for k in range(max(0,ix-2), min(len(times), ix+3)):
        if k not in forbidden:
            dt = abs((times[k]-timestamp).total_seconds())
            if dt <= tolerance_s:
                possible.append((dt,k))
    return min(possible)[1] if possible else None


def align_group(by, sensors, step_s=120, tolerance_s=60):
    if step_s <= 0 or tolerance_s <= 0 or tolerance_s > step_s/2:
        # Evita asignar una misma muestra a dos instantes en rejillas adyacentes.
        raise ValueError('Exigir 0 < tolerance_s <= step_s/2')
    if len(sensors) < 2:
        return [], 0
    earliest = max(by[n][0]['time'] for n in sensors)
    latest = min(by[n][-1]['time'] for n in sensors)
    # Interseccion de ventanas historicas, NO de ticks virtuales.
    earliest_epoch = earliest.timestamp()
    first_slot = int(math.ceil(earliest_epoch / step_s) * step_s)
    last_slot = int(latest.timestamp() // step_s * step_s)
    if first_slot > last_slot: return [], 0
    time_vectors = {n: [r['time'] for r in by[n]] for n in sensors}
    used = {n: set() for n in sensors}
    rows=[]
    total_slots=0
    for epoch in range(first_slot, last_slot+1, step_s):
        slot = datetime.fromtimestamp(epoch,timezone.utc)
        total_slots += 1
        indexes = {n: nearest_index(time_vectors[n], slot, tolerance_s, used[n]) for n in sensors}
        if any(v is None for v in indexes.values()):
            continue  # No inventar/interpolar un valor faltante.
        for n in sensors:
            idx = indexes[n]
            r = by[n][idx]
            used[n].add(idx)
            rows.append({
                'aligned_time_utc':slot.isoformat(),
                'virtual_sensor':n,
                'source_sensor':r['source_sensor'],
                'original_time_utc':r['time'].isoformat(),
                'offset_seconds':round((r['time']-slot).total_seconds(), 3),
                'temperature_c':r['temp'],
                'latitude':r['latlon'][0],
                'longitude':r['latlon'][1],
                'interpolated':False,
            })
    return rows, total_slots


def run_one(name, data_dir, out_dir, max_distance_m=500, step_s=120, tolerance_s=60):
    by = read_source(data_dir / DATASETS[name])
    groups = partition_spatial_groups(by, max_distance_m=max_distance_m)
    group_reports=[]
    output=[]
    for k, sensors in enumerate(groups, 1):
        group_name = f'{name}_group_{k:02d}'
        dmax=max((distance_m(by[x][0]['latlon'],by[y][0]['latlon']) for i,x in enumerate(sensors) for y in sensors[i+1:]), default=0)
        aligned, slots = align_group(by, sensors,step_s,tolerance_s)
        for row in aligned:
            output.append({'group':group_name, **row})
        group_reports.append({
            'group':group_name,
            'sensors':sensors,
            'num_sensors':len(sensors),
            'max_pair_distance_m':round(dmax,1),
            'candidate_slots':slots,
            'complete_slots':len(aligned)//len(sensors),
            'coverage_pct':round(100*(len(aligned)//len(sensors))/slots,1) if slots else 0,
            'max_abs_offset_s':max((abs(r['offset_seconds']) for r in aligned),default=None),
            'suitable_for_exploratory_comparison':len(sensors)>=2 and len(aligned)>0,
        })
    out_dir.mkdir(parents=True,exist_ok=True)
    outfile=out_dir/f'alineado_{name}.csv'
    fields=['group','aligned_time_utc','virtual_sensor','source_sensor','original_time_utc','offset_seconds','temperature_c','latitude','longitude','interpolated']
    with outfile.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    return {'period':name,'source_file':DATASETS[name], 'max_group_distance_m':max_distance_m,
            'step_seconds':step_s,'tolerance_seconds':tolerance_s, 'groups':group_reports,
            'csv':outfile.name, 'output_rows':len(output),
            'warning':'Solo emparejamiento observacional; proximidad no asegura mismo microclima. Los eventos de replay NO se trasladan a esta rejilla.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('periods', nargs='*', choices=list(DATASETS), default=None)
    parser.add_argument('--data-dir',type=Path,default=Path('/app/data'))
    parser.add_argument('--out-dir',type=Path,default=Path('/app/results'))
    parser.add_argument('--max-distance-m',type=float,default=500)
    parser.add_argument('--tolerance-s',type=float,default=60)
    parser.add_argument('--step-s',type=int,default=120)
    args=parser.parse_args()
    if args.max_distance_m<=0 or args.tolerance_s<=0 or args.step_s<2*args.tolerance_s:
        parser.error('Distancia > 0 y tolerancia <= mitad del intervalo')
    report=[]
    for name in (args.periods or ['noviembre','mayo','octubre']):
        r=run_one(name,args.data_dir,args.out_dir,args.max_distance_m,args.step_s,args.tolerance_s)
        report.append(r)
        print(f'\n{name.upper()} — {r["source_file"]}')
        for group in r['groups']:
            print('  '+group['group']+': '+','.join(group['sensors'])
                  +f' | dist. máx. {group["max_pair_distance_m"]} m | '
                  +f'{group["complete_slots"]}/{group["candidate_slots"]} instantes completos')
        print('  Salida: results/'+r['csv'])
    csv_summary=args.out_dir/'alineacion_historica_summary.csv'
    with csv_summary.open('w',newline='',encoding='utf-8-sig') as f:
        fields=['period','group','sensors','num_sensors','max_pair_distance_m','candidate_slots','complete_slots','coverage_pct','max_abs_offset_s','suitable_for_exploratory_comparison']
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        for case in report:
            for group in case['groups']:
                writer.writerow({**group,'period':case['period'],'sensors':','.join(group['sensors'])})
    dest=args.out_dir/'alineacion_historica_summary.json'
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('\nResumen: results/'+dest.name+' y results/'+csv_summary.name)
    print('IMPORTANTE: original intacto; no se interpolan datos ni se alteran los detectores.')


if __name__=='__main__': main()
