"""Evalúa detecciones CUSUM Shadow registradas EN VIVO en dos replays pareados.

Uso: python evaluate_shadow.py RUN_CONTROL RUN_EVENTO
No lee datos del broker, no publica alarmas y no modifica los detectores.
"""
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/app/results')
CANDIDATES = ('sensible', 'conservador')


def read_json(path):
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def read_jsonl(path):
    if not path.is_file():
        raise FileNotFoundError(str(path))
    with path.open(encoding='utf-8') as file:
        return [json.loads(line) for line in file if line.strip()]


def load(run_id, root=ROOT):
    folder = root / run_id
    truth = read_json(folder / 'ground_truth.json')
    summary = read_json(folder / 'summary.json')
    shadow = read_json(folder / 'shadow_summary.json')
    source = read_jsonl(folder / 'readings_sent.jsonl')
    detections = read_jsonl(folder / 'shadow_events.jsonl')
    if not shadow.get('session_closed'):
        raise ValueError(f'{run_id}: Shadow no terminó de guardar el escenario')
    if shadow.get('run_id') != run_id or summary.get('run_id') != run_id:
        raise ValueError(f'{run_id}: resumen asociado a otro escenario')
    published = int(summary['published'])
    received = int(shadow['readings_received'])
    if published != len(source):
        raise ValueError(f'{run_id}: lecturas guardadas distintas de published')
    if received > published:
        raise ValueError(f'{run_id}: Shadow recibió más lecturas que las publicadas')

    keys = {}
    windows = defaultdict(list)
    for row in source:
        msg = row['message']
        key = (str(msg['node_id']), int(row['tick']))
        if key in keys:
            raise ValueError(f'{run_id}: lectura duplicada {key}')
        keys[key] = row
        if float(row.get('injected_temperature_increase_c', 0)) > 0:
            windows[key[0]].append(key[1])
    tick_by_time = {(k[0], row['message']['timestamp']): k[1] for k, row in keys.items()}
    if len(tick_by_time) != len(keys):
        raise ValueError(f'{run_id}: fechas repetidas para un mismo sensor')

    alarms = {candidate: defaultdict(list) for candidate in CANDIDATES}
    for d in detections:
        if d.get('run_id') != run_id or d.get('candidate') not in CANDIDATES or not d.get('shadow_only'):
            raise ValueError(f'{run_id}: detección Shadow incorrecta')
        node = str(d['node_id'])
        stamp = d['reading_timestamp']
        if (node, stamp) not in tick_by_time:
            raise ValueError(f'{run_id}: detección sin lectura correspondiente: {node} {stamp}')
        alarms[d['candidate']][node].append(tick_by_time[(node, stamp)])
    for candidate in CANDIDATES:
        observed = sum(len(ticks) for ticks in alarms[candidate].values())
        if observed != int(shadow['detections_by_candidate'][candidate]):
            raise ValueError(f'{run_id}: el contador de {candidate} no cuadra con JSONL')

    return dict(run_id=run_id, truth=truth, summary=summary, shadow=shadow,
                source=source, keys=keys, windows=windows, alarms=alarms,
                published=published, received=received)


def compare(control, event):
    if control['windows']:
        raise ValueError('El RUN_CONTROL contiene perturbaciones')
    if not event['windows']:
        raise ValueError('El RUN_EVENTO no contiene perturbaciones')
    if set(control['keys']) != set(event['keys']):
        raise ValueError('Las ejecuciones no tienen los mismos sensores/pasos')
    if float(control['truth']['virtual_step_seconds']) != float(event['truth']['virtual_step_seconds']):
        raise ValueError('Distinto intervalo temporal entre escenarios')
    for key, base in control['keys'].items():
        altered = event['keys'][key]
        ctrl_temp = float(base['message']['measurements']['air_temperature_c'])
        event_temp = float(altered['message']['measurements']['air_temperature_c'])
        injection = float(altered.get('injected_temperature_increase_c', 0))
        if not math.isclose(event_temp, ctrl_temp + injection, abs_tol=0.002):
            raise ValueError(f'Los replays no son pareados en {key}')
    minutes_per_tick = float(event['truth']['virtual_step_seconds']) / 60
    rows = []
    for candidate in CANDIDATES:
        control_alarms = control['alarms'][candidate]
        event_alarms = event['alarms'][candidate]
        in_window = []
        earlier = []
        delays = {}
        for node, window in sorted(event['windows'].items()):
            event_ticks = [t for t in event_alarms.get(node, []) if window[0] <= t <= window[-1]]
            if not event_ticks:
                continue
            t = min(event_ticks)
            in_window.append(node)
            base_ticks = control_alarms.get(node, [])
            if not base_ticks or t < min(base_ticks):
                earlier.append(node)
                delays[node] = round((t-window[0])*minutes_per_tick, 3)
        rows.append({
            'candidate': candidate,
            'control_run': control['run_id'],
            'event_run': event['run_id'],
            'affected_sensors': len(event['windows']),
            'fp_control_sensors': len(control_alarms),
            'fp_control_ids': sorted(control_alarms),
            'detected_in_window': len(in_window),
            'in_window_ids': in_window,
            'earlier_than_control': len(earlier),
            'earlier_ids': earlier,
            'delay_virtual_min_by_sensor': delays,
            'control_readings_seen': control['received'],
            'event_readings_seen': event['received'],
            'expected_readings': event['published'],
            'complete': control['received'] == control['published'] and event['received'] == event['published'],
        })
    return rows


def save(rows, out_dir=ROOT):
    suffix = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output_json = out_dir / f'shadow_live_comparison_{suffix}.json'
    output_csv = out_dir / f'shadow_live_comparison_{suffix}.csv'
    output_json.write_text(json.dumps({
        'kind': 'mqtt_shadow_control_paired_comparison',
        'notes': 'Los marcadores de ejecución no transmiten ground truth al Edge. Solo escenarios sintéticos.',
        'rows': rows,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    with output_csv.open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file)
        writer.writerow(['candidate', 'fp_control_sensors', 'detected_in_window',
                         'earlier_than_control', 'affected_sensors', 'delay_virtual_min_by_sensor',
                         'control_readings_seen', 'event_readings_seen', 'expected_readings', 'complete'])
        for r in rows:
            writer.writerow([r['candidate'], r['fp_control_sensors'], r['detected_in_window'],
                             r['earlier_than_control'], r['affected_sensors'],
                             json.dumps(r['delay_virtual_min_by_sensor']), r['control_readings_seen'],
                             r['event_readings_seen'], r['expected_readings'], r['complete']])
    return output_csv, output_json


def latest_paired_ids(root=ROOT):
    """Escoge el último control y el último evento que tienen archivos Shadow."""
    control_ids, event_ids = [], []
    for folder in root.iterdir():
        if not folder.is_dir() or not (folder / 'shadow_summary.json').is_file():
            continue
        summary_file = folder / 'summary.json'
        if not summary_file.is_file():
            continue
        summary = read_json(summary_file)
        if summary.get('event_enabled') is False:
            control_ids.append(folder.name)
        elif summary.get('event_enabled') is True:
            event_ids.append(folder.name)
    if not control_ids or not event_ids:
        raise ValueError('Falta un control o evento con archivos Shadow. Ejecuta ambos con la nueva versión.')
    return max(control_ids), max(event_ids)


def main(argv):
    if argv == ['--latest']:
        argv = list(latest_paired_ids())
    if len(argv) != 2:
        print('USO: python evaluate_shadow.py --latest  (o RUN_CONTROL RUN_EVENTO)')
        return 2
    control = load(argv[0])
    event = load(argv[1])
    rows = compare(control, event)
    print('\nCOMPARACIÓN SHADOW MQTT EN VIVO (CONTROL PAREADO)')
    print(f'Control: {control["run_id"]} | Shadow {control["received"]}/{control["published"]} lecturas')
    print(f'Evento : {event["run_id"]} | Shadow {event["received"]}/{event["published"]} lecturas')
    for r in rows:
        print(f'{r["candidate"]:11} | control FP en {r["fp_control_sensors"]} sensores | '
              f'evento {r["detected_in_window"]}/{r["affected_sensors"]} en ventana | '
              f'adelanta al control {r["earlier_than_control"]}/{r["affected_sensors"]} | '
              f'delays {r["delay_virtual_min_by_sensor"]}')
    if any(not r['complete'] for r in rows):
        print('ADVERTENCIA: el Shadow no registró todas las lecturas; comparar solo como indicio')
    csv_path, json_path = save(rows)
    print(f'CSV: results/{csv_path.name}')
    print(f'JSON: results/{json_path.name}')
    print('Solo perturbaciones sintéticas. Ajuste de parámetros y evaluación sobre la misma muestra.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, TypeError, KeyError, FileNotFoundError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
