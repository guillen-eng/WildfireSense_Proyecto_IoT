"""Comparacion reproducible de escenarios WildfireSense.

Uso en el contenedor scenario:
    python evaluate.py <run_con_evento> <run_sin_evento>

Este programa evalua el comportamiento ante perturbaciones sinteticas;
no estima precision de deteccion de incendios reales.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path


RESULTS_ROOT = Path('/app/results')


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def load_jsonl(path):
    with path.open(encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def get_run(name):
    path = RESULTS_ROOT / name
    if not path.is_dir():
        raise FileNotFoundError(f'No existe el directorio de ejecucion: {path}')
    required = ('ground_truth.json', 'readings_sent.jsonl',
                'alerts_received.jsonl', 'summary.json')
    for filename in required:
        if not (path / filename).is_file():
            raise FileNotFoundError(f'Falta {path / filename}')
    return path, load_json(path/'ground_truth.json'), \
        load_jsonl(path/'readings_sent.jsonl'), \
        load_jsonl(path/'alerts_received.jsonl'), load_json(path/'summary.json')


def evaluate_run(run_name):
    path, truth, readings, records, summary = get_run(run_name)
    enabled = bool(truth.get('event_enabled', True))
    sensors = list(summary['sensors'])
    affected = set(truth.get('affected_sensors', [])) if enabled else set()
    if not affected.issubset(sensors):
        raise ValueError('Hay sensores afectados que no estan en summary.sensors')

    # Tick de cada lectura realmente publicada y primera perturbacion por sensor.
    ticks = {}
    onset = {}
    for row in readings:
        msg = row['message']
        node = str(msg['node_id'])
        ticks[(node, str(msg['timestamp']))] = int(row['tick'])
        if float(row.get('injected_temperature_increase_c', 0)) > 0 and node not in onset:
            onset[node] = int(row['tick'])
    if enabled and set(onset) != affected:
        raise ValueError('No coincide el ground truth con las perturbaciones registradas')

    alarm_rows = defaultdict(list)
    for record in records:
        alarm = record.get('alarm', {})
        if alarm.get('type') != 'environmental_alert':
            continue
        node = str(alarm.get('node_id', ''))
        if node not in sensors:
            continue
        tick = ticks.get((node, str(alarm.get('reading_timestamp', ''))))
        alarm_rows[node].append({'tick': tick,
                                 'edge_processing_ms': alarm.get('edge_processing_ms')})

    step_min = float(truth['virtual_step_seconds']) / 60.0
    detected = []
    missed = []
    unexpected = []
    no_alert = []
    details = []
    for sensor in sensors:
        alarms = alarm_rows[sensor]
        if sensor in affected:
            matches = [a for a in alarms if a['tick'] is not None and a['tick'] >= onset[sensor]]
            early = [a for a in alarms if a['tick'] is None or a['tick'] < onset[sensor]]
            if matches:
                selected = min(matches, key=lambda a: a['tick'])
                detected.append(sensor)
                delay = (selected['tick'] - onset[sensor]) * step_min
                details.append({'sensor': sensor, 'result': 'detected',
                                'onset_tick': onset[sensor], 'alarm_tick': selected['tick'],
                                'delay_virtual_minutes': delay,
                                'edge_processing_ms': selected['edge_processing_ms']})
            else:
                missed.append(sensor)
                details.append({'sensor': sensor, 'result': 'missed',
                                'onset_tick': onset[sensor], 'alarm_tick': None,
                                'delay_virtual_minutes': None})
            if early:
                unexpected.append(sensor)
        elif alarms:
            unexpected.append(sensor)
            details.append({'sensor': sensor, 'result': 'unexpected_alarm',
                            'num_alarms': len(alarms)})
        else:
            no_alert.append(sensor)
            details.append({'sensor': sensor, 'result': 'no_alarm'})

    return {'run_id': run_name, 'event_enabled': enabled,
            'readings_published': summary['published'],
            'num_sensors': len(sensors),
            'affected_detected': detected, 'affected_missed': missed,
            'unaffected_without_alert': no_alert,
            'sensors_with_unexpected_alarms': sorted(set(unexpected)),
            'environmental_alerts_received': summary['environmental_alerts_received'],
            'sensor_details': details}


def main():
    if len(sys.argv) != 3:
        print('Uso: python evaluate.py <run_con_evento> <run_sin_evento>')
        return 2
    event = evaluate_run(sys.argv[1])
    control = evaluate_run(sys.argv[2])
    if not event['event_enabled'] or control['event_enabled']:
        print('ERROR: primer run debe tener evento; segundo debe ser control sin evento.')
        return 2
    result = {
        'comparison_kind': 'synthetic_perturbation_functional_check',
        'event_run': event,
        'control_run': control,
        'limitations': 'Dos ejecuciones cortas: no mide precision, sensibilidad o tasas de falsas alarmas reales.'
    }
    print('\nEVALUACION COMPARATIVA — WILDFIRESENSE')
    print('Escenario CON evento:')
    print(f"  Lecturas: {event['readings_published']}")
    print(f"  Sensores afectados con alarma: {len(event['affected_detected'])}")
    print(f"  Sensores afectados sin alarma: {len(event['affected_missed'])}")
    print(f"  Sensores con alarmas inesperadas: {len(event['sensors_with_unexpected_alarms'])}")
    for item in event['sensor_details']:
        if item['result'] == 'detected':
            print(f"  {item['sensor']}: inicio paso {item['onset_tick']}, "
                  f"alarma paso {item['alarm_tick']}, retraso {item['delay_virtual_minutes']:g} min virtuales")
    print('Control SIN evento:')
    print(f"  Lecturas: {control['readings_published']}")
    print(f"  Sensores sin alarma: {len(control['unaffected_without_alert'])}/{control['num_sensors']}")
    print(f"  Sensores con alarma inesperada: {len(control['sensors_with_unexpected_alarms'])}")
    filename = f"comparison_{event['run_id']}_{control['run_id']}.json"
    output = RESULTS_ROOT / filename
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Informe guardado: results/{filename}')
    print('NOTA: es una comprobacion funcional con perturbaciones sinteticas, no una evaluacion con incendios reales.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
