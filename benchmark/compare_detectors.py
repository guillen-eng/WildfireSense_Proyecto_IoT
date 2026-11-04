"""Comparación OFFLINE de Z-score y CUSUM con las mismas lecturas guardadas.

Uso:
    python compare_detectors.py RUN_NORMAL RUN_SUAVE RUN_GRADUAL [RUN_FUERTE]

No publica ni consume MQTT. No modifica la configuración del Edge en producción.
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from logic import ZScoreDetector
from cusum import CUSUMDetector

RESULTS = Path('/app/results')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_jsonl(path):
    with path.open(encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def compare_one(run_id, detector_name):
    folder = RESULTS / run_id
    for name in ('ground_truth.json', 'readings_sent.jsonl', 'summary.json'):
        if not (folder / name).is_file():
            raise FileNotFoundError(f'Falta el archivo: {folder / name}')

    truth = read_json(folder / 'ground_truth.json')
    summary = read_json(folder / 'summary.json')
    readings = read_jsonl(folder / 'readings_sent.jsonl')
    sensors = set(str(x) for x in summary['sensors'])
    if len(readings) != int(summary['published']):
        raise ValueError('Número de filas guardadas diferente al de publicaciones')

    detector = (ZScoreDetector(measurement_field='air_temperature_c', unit='C')
                if detector_name == 'Z-score'
                else CUSUMDetector(measurement_field='air_temperature_c', unit='C'))

    events_by_sensor = defaultdict(list)
    active_ticks = defaultdict(list)
    for record in readings:
        node = str(record['message']['node_id'])
        tick = int(record['tick'])
        if node not in sensors:
            raise ValueError('Mensaje de sensor no registrado')
        if float(record.get('injected_temperature_increase_c', 0)) > 0:
            active_ticks[node].append(tick)
        alarm = detector.evaluate(record['message'])
        if alarm is not None:
            events_by_sensor[node].append(tick)

    # Compatibilidad con los primeros escenarios de WildfireSense (nov. 2026):
    # las ejecuciones antiguas CON evento no guardaban `event_enabled`,
    # pero sí `affected_sensors` y `event_kind`.
    if 'event_enabled' in truth:
        event_enabled = bool(truth['event_enabled'])
    else:
        event_enabled = (bool(truth.get('affected_sensors', []))
                         and truth.get('event_kind') != 'normal_control_without_injected_event')
    affected = set(truth.get('affected_sensors', [])) if event_enabled else set()
    config_path = folder / 'config_used.json'
    event_config = (read_json(config_path).get('event', {})
                    if config_path.is_file() else truth)
    if not affected:
        scenario_name = 'sin_evento'
    elif 'max_temperature_increase_c' not in event_config:
        scenario_name = 'evento_sin_config'
    elif int(event_config.get('ramp_steps', 4)) >= 8:
        scenario_name = 'gradual'
    elif float(event_config.get('max_temperature_increase_c', 0)) <= 6:
        scenario_name = 'suave'
    else:
        scenario_name = 'fuerte'
    if affected != set(active_ticks):
        raise ValueError(
            f'Ground truth no coincide con las perturbaciones inyectadas en {run_id}: '
            f'afectados={sorted(affected)}; con_inyeccion={sorted(active_ticks)}'
        )

    detected, missed, unexpected, delays, alarms = [], [], [], {}, 0
    for node in sorted(sensors):
        node_alert_ticks = events_by_sensor[node]
        alarms += len(node_alert_ticks)
        window = active_ticks.get(node, [])
        if node in affected:
            matching = [t for t in node_alert_ticks if window[0] <= t <= window[-1]]
            outside = [t for t in node_alert_ticks if t < window[0] or t > window[-1]]
            if matching:
                detected.append(node)
                delays[node] = round(
                    (min(matching) - window[0]) * float(truth['virtual_step_seconds']) / 60, 3
                )
            else:
                missed.append(node)
            if outside:
                unexpected.append(node)
        elif node_alert_ticks:
            unexpected.append(node)

    return {
        'run_id': run_id,
        'scenario': scenario_name,
        'detector': detector_name,
        'readings_evaluated': len(readings),
        'affected': len(affected),
        'detected': len(detected),
        'missed': len(missed),
        'unexpected_alert_sensors': len(set(unexpected)),
        'alarm_count': alarms,
        'detected_ids': detected,
        'missed_ids': missed,
        'unexpected_ids': sorted(set(unexpected)),
        'alarm_ticks_by_sensor': {node: ticks for node, ticks in events_by_sensor.items() if ticks},
        'delay_virtual_min_by_sensor': delays,
        'assumptions': {
            'cusum_allowance_c': 0.5 if detector_name == 'CUSUM' else None,
            'cusum_threshold': 8.0 if detector_name == 'CUSUM' else None,
            'cusum_baseline_samples': 20 if detector_name == 'CUSUM' else None,
            'zscore_min_history': 20 if detector_name == 'Z-score' else None,
            'zscore_threshold': 4.0 if detector_name == 'Z-score' else None,
        }
    }


def main():
    run_ids = sys.argv[1:]
    if not (3 <= len(run_ids) <= 4):
        print('Uso: RUN_CONTROL RUN_SUAVE RUN_GRADUAL [RUN_FUERTE]')
        return 2
    rows = []
    for run_id in run_ids:
        for algorithm in ('Z-score', 'CUSUM'):
            rows.append(compare_one(run_id, algorithm))

    # Compare each algorithm with its own no-event control, so an alarm
    # also present in normal conditions cannot be claimed as evidence
    # of successfully detecting the injected perturbation.
    controls = {r['detector']: r for r in rows if r['scenario'] == 'sin_evento'}
    for row in rows:
        control_alerts = controls[row['detector']]['alarm_ticks_by_sensor']
        row['also_alerted_in_normal_control'] = sorted(
            node for node in row['detected_ids'] if node in control_alerts
        )

    print('\nCOMPARACION OFFLINE — Z-SCORE FRENTE A CUSUM')
    print('Se usan las lecturas originales guardadas; no se envian nuevos mensajes MQTT.\n')
    for row in rows:
        delay = (', '.join(f'{name}: {value:g} min' for name, value in row['delay_virtual_min_by_sensor'].items())
                 or '—')
        print(f"{row['scenario']:<10} | {row['detector']:<7} | detectados {row['detected']}/{row['affected']} "
              f"| alarmas inesperadas en {row['unexpected_alert_sensors']} sensores | "
              f"retraso virtual: {delay}")
        if row['also_alerted_in_normal_control']:
            print('   ADVERTENCIA: esos sensores también alarmaron sin evento: ' +
                  ', '.join(row['also_alerted_in_normal_control']))

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    json_path = RESULTS / f'detector_benchmark_{stamp}.json'
    csv_path = RESULTS / f'detector_benchmark_{stamp}.csv'
    report = {
        'kind': 'offline_statistical_detector_experiment',
        'method': 'Same stored readings and event labels evaluated with independent detector instances',
        'limitation': 'Synthetic perturbations on a small real-data sample, NOT wildfire detection accuracy. Offline results do not measure MQTT latency.',
        'rows': rows,
    }
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with csv_path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['scenario', 'run_id', 'detector', 'readings', 'affected', 'detected', 'missed',
                         'sensors_with_unexpected_alerts', 'alarms', 'alerts_also_present_in_control', 'delays_virtual_minutes'])
        for row in rows:
            writer.writerow([row['scenario'], row['run_id'], row['detector'], row['readings_evaluated'],
                             row['affected'], row['detected'], row['missed'],
                             row['unexpected_alert_sensors'], row['alarm_count'],
                             ';'.join(row['also_alerted_in_normal_control']),
                             json.dumps(row['delay_virtual_min_by_sensor'], ensure_ascii=False)])
    print(f'\nInforme: results/{json_path.name}')
    print(f'Tabla CSV: results/{csv_path.name}')
    print('AVISO: resultados de algoritmos sobre datos guardados, no prueba de deteccion de incendios reales.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f'ERROR: {exc}')
        sys.exit(1)
