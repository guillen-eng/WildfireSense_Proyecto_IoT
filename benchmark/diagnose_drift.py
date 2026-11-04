"""Diagnóstico descriptivo de tendencia ambiental con escenarios pareados.

No altera detectores ni MQTT. Compara temperaturas enviadas al Edge en
controles y eventos sintéticos, y distingue tendencia natural de inyección.

Uso: python diagnose_drift.py RUN_CONTROL RUN_EVENTO [RUN_CONTROL RUN_EVENTO ...]
"""
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

RESULTS = Path('/app/results')


def load_run(root, run_id):
    folder = root / run_id
    with (folder / 'summary.json').open(encoding='utf-8') as file:
        summary = json.load(file)
    with (folder / 'ground_truth.json').open(encoding='utf-8') as file:
        truth = json.load(file)
    with (folder / 'readings_sent.jsonl').open(encoding='utf-8') as file:
        readings = [json.loads(line) for line in file if line.strip()]
    by_sensor = defaultdict(dict)
    for entry in readings:
        node = str(entry['message']['node_id'])
        tick = int(entry['tick'])
        if tick in by_sensor[node]:
            raise ValueError(f'{run_id}: lectura duplicada {node}, paso {tick}')
        by_sensor[node][tick] = {
            'temp': float(entry['message']['measurements']['air_temperature_c']),
            'injection': float(entry.get('injected_temperature_increase_c', 0)),
        }
    if len(readings) != int(summary['published']):
        raise ValueError(f'{run_id}: total de lecturas inconsistente')
    return {'id': run_id, 'summary': summary, 'truth': truth, 'by_sensor': dict(by_sensor)}


def compare_pair(control, event, baseline_end=20):
    if control['summary'].get('event_enabled') is not False:
        raise ValueError('Primer RUN debe ser un CONTROL sin evento')
    if event['summary'].get('event_enabled') is not True:
        raise ValueError('Segundo RUN debe tener evento habilitado')
    if control['by_sensor'].keys() != event['by_sensor'].keys():
        raise ValueError('Sensores no coinciden entre control y evento')
    if control['truth'].get('dataset') != event['truth'].get('dataset'):
        raise ValueError('Datasets distintos: no son escenarios pareados')
    if control['truth'].get('virtual_step_seconds') != event['truth'].get('virtual_step_seconds'):
        raise ValueError('Intervalos virtuales distintos')

    rows = []
    for sensor in sorted(control['by_sensor']):
        c = control['by_sensor'][sensor]
        e = event['by_sensor'][sensor]
        if set(c) != set(e) or len(c) < 60:
            raise ValueError(f'{sensor}: pasos incompletos o distintos')
        if any(abs(v['injection']) > 1e-9 for v in c.values()):
            raise ValueError('El control contiene una inyección')
        for step in c:
            if not math.isclose(e[step]['temp'] - c[step]['temp'], e[step]['injection'], abs_tol=.002):
                raise ValueError(f'{sensor} tick {step}: evento no coincide con control + inyección')
        injected = [t for t in sorted(e) if e[t]['injection'] > 0]
        # Usar la misma duración de ventana por sensor, trasladada cuando haya retraso.
        window_start = min(injected) if injected else int(event['truth']['start_step'])
        window_length = int(event['truth']['duration_steps'])
        window = list(range(window_start, window_start + window_length))
        if any(t not in c for t in window) or any(t not in c for t in range(baseline_end)):
            raise ValueError(f'{sensor}: faltan lecturas en ventana de análisis')
        baseline = statistics.mean(c[t]['temp'] for t in range(baseline_end))
        control_window = statistics.mean(c[t]['temp'] for t in window)
        event_window = statistics.mean(e[t]['temp'] for t in window)
        mean_injection = statistics.mean(e[t]['injection'] for t in window)
        rows.append({
            'sensor': sensor,
            'afectado': bool(injected),
            'inicio_ventana': window_start,
            'baseline_control_c': round(baseline, 3),
            'control_ventana_c': round(control_window, 3),
            'tendencia_control_c': round(control_window - baseline, 3),
            'inyeccion_media_c': round(mean_injection, 3),
            'inyeccion_max_c': round(max(e[t]['injection'] for t in window), 3),
            'evento_ventana_c': round(event_window, 3),
            'evento_vs_baseline_c': round(event_window - baseline, 3),
        })
    return rows


def save(root, rows):
    suffix = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    csv_path = root / f'diagnostico_tendencias_{suffix}.csv'
    json_path = root / f'diagnostico_tendencias_{suffix}.json'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps({
        'method': 'Media de pasos 0-19 frente a ventana de 16 pasos desde inicio del evento por sensor',
        'scope': 'Replays sintéticos pareados; no son incendios reales ni temperaturas sincronizadas de campo',
        'rows': rows,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    return csv_path, json_path


def main(args, root=RESULTS):
    if len(args) < 2 or len(args) % 2:
        print('USO: python diagnose_drift.py CONTROL EVENTO [CONTROL EVENTO ...]', file=sys.stderr)
        return 2
    rows = []
    for i in range(0, len(args), 2):
        control = load_run(root, args[i])
        event = load_run(root, args[i+1])
        result = compare_pair(control, event)
        period = control['truth']['dataset']
        print(f'\nPERIODO {period}')
        print(f'Control {args[i]} | Evento {args[i+1]}')
        print('Sensor      | Control vs baseline | Inyección media | Evento vs baseline')
        for r in result:
            if not r['afectado']:
                continue
            print(f"{r['sensor']:11} | {r['tendencia_control_c']:+7.2f} °C           | "
                  f"{r['inyeccion_media_c']:5.2f} °C        | {r['evento_vs_baseline_c']:+7.2f} °C")
        print(f"Control: {sum(r['tendencia_control_c']>0 for r in result)}/5 sensores "
              'aumentan de temperatura respecto a la referencia inicial durante la ventana.')
        rows.extend(dict(periodo=period, control_run=args[i], evento_run=args[i+1], **r) for r in result)
    paths = save(root, rows)
    print('\nCSV: results/' + paths[0].name)
    print('JSON: results/' + paths[1].name)
    print('ATENCIÓN: análisis de tendencias descriptivo, no prueba de detección de incendios reales.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, FileNotFoundError, KeyError, TypeError, ZeroDivisionError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
