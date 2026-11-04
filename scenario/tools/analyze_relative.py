"""Diagnostico exploratorio de diferencias de temperatura entre sensores alineados.

NO detecta incendios ni genera alarmas: la serie relativa de cada sensor es
T_sensor - mediana(T_otros_sensores del mismo grupo), centrada usando las primeras
5 observaciones coincidentes. No interpola ni modifica valores originales.
"""
import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PERIODS = ('noviembre', 'mayo', 'octubre')
FIELDS = ['period', 'group', 'time_utc', 'sensor', 'temperature_c', 'peer_median_c',
          'relative_c', 'baseline_relative_c', 'change_from_baseline_c',
          'num_peers', 'pair_only_ambiguous']


def analyse_rows(rows, period, baseline_slots=5, min_slots=8):
    """Devuelve series y resumen, sin umbrales calibrados ni alarmas."""
    by_group = defaultdict(lambda: defaultdict(dict))
    for row in rows:
        group = row['group']
        sensor = row['virtual_sensor']
        timestamp = row['aligned_time_utc']
        if not group or not sensor:
            raise ValueError('Grupo o sensor vacio')
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            temp = float(row['temperature_c'])
            offset = float(row['offset_seconds'])
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError('Marca temporal, temperatura u offset no valido') from exc
        if dt.tzinfo is None or dt.utcoffset() is None or not math.isfinite(temp):
            raise ValueError('Tiempo sin zona horaria o temperatura invalida')
        if not math.isfinite(offset) or abs(offset) > 60.001:
            raise ValueError('Muestra fuera del margen de alineacion +/-60 segundos')
        if str(row['interpolated']).strip().lower() not in ('false', '0'):
            raise ValueError('No se admiten muestras interpoladas')
        if sensor in by_group[group][timestamp]:
            raise ValueError('Lectura duplicada en el mismo grupo, instante y sensor')
        by_group[group][timestamp][sensor] = temp

    output = []
    summary = []
    for group, times in sorted(by_group.items()):
        ordered = sorted(times, key=lambda t: datetime.fromisoformat(t.replace('Z', '+00:00')))
        sensor_set = set(times[ordered[0]])
        if len(sensor_set) < 2:
            raise ValueError(f'{group}: se requieren al menos 2 sensores')
        for t in ordered:
            if set(times[t]) != sensor_set:
                raise ValueError(f'{group}: instante incompleto o sensores cambiantes')
        if len(ordered) < min_slots:
            summary.append({'period': period, 'group': group, 'sensors': len(sensor_set),
                            'slots': len(ordered), 'status': 'insuficiente',
                            'sensor': '', 'final_change_c': None, 'max_abs_change_c': None,
                            'median_last_half_change_c': None,
                            'note': 'Muestras insuficientes para diagnostico exploratorio'})
            continue
        nbase = min(baseline_slots, max(2, len(ordered)//3))
        if nbase < 2:
            raise ValueError('Periodo de referencia insuficiente')
        for sensor in sorted(sensor_set):
            residuals = []
            for t in ordered:
                peers = [v for n, v in times[t].items() if n != sensor]
                residuals.append(times[t][sensor] - statistics.median(peers))
            baseline = statistics.median(residuals[:nbase])
            changes = [r - baseline for r in residuals]
            for t, rel, change in zip(ordered, residuals, changes):
                peer_median = times[t][sensor] - rel
                output.append({'period': period, 'group': group, 'time_utc': t, 'sensor': sensor,
                               'temperature_c': round(times[t][sensor], 3),
                               'peer_median_c': round(peer_median, 3),
                               'relative_c': round(rel, 3),
                               'baseline_relative_c': round(baseline, 3),
                               'change_from_baseline_c': round(change, 3),
                               'num_peers': len(sensor_set)-1,
                               'pair_only_ambiguous': len(sensor_set) == 2})
            summary.append({'period': period, 'group': group, 'sensors': len(sensor_set),
                            'slots': len(ordered), 'status': 'exploratorio', 'sensor': sensor,
                            'final_change_c': round(changes[-1], 2),
                            'max_abs_change_c': round(max(map(abs, changes)), 2),
                            'median_last_half_change_c': round(statistics.median(changes[len(changes)//2:]), 2),
                            'note': ('Solo dos sensores: no es posible atribuir la causa de la diferencia'
                                     if len(sensor_set) == 2 else
                                     'Proximidad no garantiza microclima equivalente; no hay etiquetas de incendio')})
    return output, summary


def run(results=Path('/app/results')):
    all_rows, all_summaries = [], []
    for period in PERIODS:
        source = results / f'alineado_{period}.csv'
        with source.open(newline='', encoding='utf-8-sig') as f:
            series, summaries = analyse_rows(list(csv.DictReader(f)), period)
        all_rows.extend(series)
        all_summaries.extend(summaries)
        print(f'\n{period.upper()}: {len(series)} valores relativos; {len(summaries)} registros resumen')
        for row in summaries:
            if row['status'] == 'exploratorio':
                print(f'  {row["group"]} {row["sensor"]}: cambio final {row["final_change_c"]:+.2f} °C '
                      f'| max abs {row["max_abs_change_c"]:.2f} °C'
                      + (' | PAR DE SENSORES: atribucion ambigua' if row['sensors'] == 2 else ''))
            else:
                print(f'  {row["group"]}: muestras insuficientes')
    results.mkdir(parents=True, exist_ok=True)
    detail = results / 'diagnostico_relativo_alineado.csv'
    summary = results / 'diagnostico_relativo_resumen.json'
    with detail.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(all_rows)
    summary.write_text(json.dumps({'method': 'sensor - median(peers), minus median(first 5 aligned residuals)',
                'baseline_definition': 'primeros min(5, floor(n/3)) instantes completos',
                'data': all_summaries,
                'limits': ['Sin etiquetas de incendios', 'No se ha inyectado ninguna perturbacion en estos CSV',
                           'No detecta incendios, ni genera alarmas',
                           'Huecos temporales preservados; no se supone muestreo continuo',
                           'En grupos de 2, diferencia relativa no identifica al sensor causante']},
                ensure_ascii=False, indent=2), encoding='utf-8')
    print('\nCSV: results/' + detail.name)
    print('JSON: results/' + summary.name)
    print('ANALISIS DESCRIPTIVO, NO DETECTOR NI PRUEBA DE INCENDIO')


if __name__ == '__main__':
    try:
        run()
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise SystemExit('ERROR: ' + str(exc)) from exc
