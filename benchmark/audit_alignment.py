"""Auditoría de sincronización de series ambientales reproducidas en WildfireSense.

No altera el Edge ni los datos. Analiza las marcas source_time históricas
conservadas en readings_sent.jsonl, NO los timestamps virtuales de MQTT.

Uso: python audit_alignment.py RUN_ID [RUN_ID ...]
"""
import csv
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

RESULTS = Path('/app/results')
DEFAULT_TOLERANCE_SECONDS = 120


def source_datetime(value):
    if not isinstance(value, str):
        raise ValueError('source_time ausente o no es texto')
    # La fuente original usa, por ejemplo: 2024-05-08 17:20:08.000 +0200
    try:
        result = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f %z')
    except ValueError:
        try:
            result = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f'source_time no válido: {value!r}') from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('source_time sin zona horaria: ' + repr(value))
    return result.astimezone(timezone.utc)


def audit_run(run_id, root=RESULTS, tolerance_seconds=DEFAULT_TOLERANCE_SECONDS):
    if not isinstance(run_id, str) or not run_id or '/' in run_id or '..' in run_id or '\\' in run_id:
        raise ValueError('RUN_ID no válido')
    if tolerance_seconds <= 0:
        raise ValueError('tolerance_seconds debe ser positivo')
    folder = root / run_id
    with (folder / 'summary.json').open(encoding='utf-8') as f:
        summary = json.load(f)
    records = defaultdict(dict)
    virtual = defaultdict(set)
    with (folder / 'readings_sent.jsonl').open(encoding='utf-8') as f:
        count = 0
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            tick = int(item['tick'])
            if tick < 0:
                raise ValueError(f'{run_id}: tick negativo')
            message = item['message']
            node = str(message['node_id'])
            if tick in records[node]:
                raise ValueError(f'{run_id}: duplicado sensor={node}, tick={tick}')
            records[node][tick] = source_datetime(message['source_time'])
            virtual[tick].add(str(message['timestamp']))
            count += 1
    if count != summary['published']:
        raise ValueError(f'{run_id}: número de lecturas distinto de summary.json')
    if len(records) < 2:
        raise ValueError(f'{run_id}: se necesitan al menos dos sensores')
    ticks = set.intersection(*(set(v) for v in records.values()))
    if any(set(v) != ticks for v in records.values()):
        raise ValueError(f'{run_id}: sensores con ticks incompletos o diferentes')
    if not ticks:
        raise ValueError(f'{run_id}: sin lecturas')
    if len(set.union(*(set(v) for v in records.values()))) != len(ticks):
        raise ValueError(f'{run_id}: faltan pasos')
    if any(len(virtual[t]) != 1 for t in ticks):
        raise ValueError(f'{run_id}: timestamp virtual distinto entre sensores del mismo tick')
    sorted_ticks = sorted(ticks)
    spreads = [
        (max(records[n][t] for n in records) - min(records[n][t] for n in records)).total_seconds()
        for t in sorted_ticks
    ]
    gaps = []
    backwards = 0
    for node, samples in records.items():
        for a, b in zip(sorted_ticks, sorted_ticks[1:]):
            diff = (samples[b] - samples[a]).total_seconds()
            gaps.append(diff)
            if diff <= 0:
                backwards += 1
    virtual_dates = [source_datetime(next(iter(virtual[t]))) for t in sorted_ticks]
    virtual_gaps = [
        (b - a).total_seconds() for a, b in zip(virtual_dates, virtual_dates[1:])
    ]
    return {
        'run_id': run_id,
        'num_sensors': len(records),
        'num_ticks': len(sorted_ticks),
        'readings': count,
        'tolerance_seconds': tolerance_seconds,
        'first_tick_spread_min': round(spreads[0] / 60, 2),
        'median_tick_spread_min': round(statistics.median(spreads) / 60, 2),
        'max_tick_spread_min': round(max(spreads) / 60, 2),
        'ticks_within_tolerance': sum(s <= tolerance_seconds for s in spreads),
        'historical_gap_median_seconds': round(statistics.median(gaps), 2),
        'historical_gap_max_min': round(max(gaps) / 60, 2),
        'historical_gaps_non_increasing': backwards,
        'virtual_gap_median_seconds': round(statistics.median(virtual_gaps), 2) if virtual_gaps else None,
        'is_suitable_for_naive_peer_comparison': all(s <= tolerance_seconds for s in spreads) and backwards == 0,
        'scope': 'Tiempos originales de replay; un índice/tick común NO prueba simultaneidad física',
    }


def save_report(results, root=RESULTS):
    suffix = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    root.mkdir(parents=True, exist_ok=True)
    j = root / f'auditoria_temporal_{suffix}.json'
    c = root / f'auditoria_temporal_{suffix}.csv'
    j.write_text(json.dumps({
        'method': 'Diferencia max-min entre source_time históricos a igual tick virtual',
        'tolerance_seconds': DEFAULT_TOLERANCE_SECONDS,
        'results': results,
        'warning': 'No confundir reloj virtual con simultaneidad histórica ni usar series desalineadas para inferir causalidad espacial.'
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    with c.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    return j, c


def main(args, root=RESULTS):
    if not args:
        print('Uso: python audit_alignment.py RUN_ID [RUN_ID ...]', file=sys.stderr)
        return 2
    results = [audit_run(run_id, root=root) for run_id in args]
    print('\nAUDITORÍA TEMPORAL — DATOS HISTÓRICOS FRENTE A RELOJ VIRTUAL')
    print('Tolerancia de simultaneidad experimental: 120 segundos (criterio de auditoría, no estándar físico).')
    for r in results:
        print(f"\n{r['run_id']} | {r['num_sensors']} sensores | {r['readings']} lecturas")
        print('  Dispersión histórica por tick: primero '
              f"{r['first_tick_spread_min']:.2f} min; mediana {r['median_tick_spread_min']:.2f} min; "
              f"máximo {r['max_tick_spread_min']:.2f} min")
        print(f"  Ticks alineados <=120 s: {r['ticks_within_tolerance']}/{r['num_ticks']}")
        print('  Intervalo histórico mediano por sensor: '
              f"{r['historical_gap_median_seconds']:.2f} s; reloj virtual: {r['virtual_gap_median_seconds']:.2f} s")
        print('  Comparación directa entre sensores: '
              + ('CUMPLE el criterio temporal simplificado' if r['is_suitable_for_naive_peer_comparison']
                 else 'NO JUSTIFICADA sin alinear tiempos y revisar ubicaciones'))
    j, c = save_report(results, root=root)
    print('\nJSON: results/' + j.name)
    print('CSV:  results/' + c.name)
    print('IMPORTANTE: no modifica los datos originales ni los detectores.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, KeyError, TypeError, FileNotFoundError, ZeroDivisionError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
