"""WildfireSense: barrido EXPLORATORIO de parámetros CUSUM en replays pareados.

No cambia el Edge ni publica MQTT. Los eventos se construyen sobre las mismas
lecturas naturales del control; detectar una anomalía en una ventana de evento
no basta para atribuirla a la perturbación si también alarma el control.

Uso: python sweep_cusum.py RUN_CONTROL RUN_SUAVE RUN_GRADUAL RUN_FUERTE
"""
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from cusum import CUSUMDetector

RESULTS = Path('/app/results')
ALLOWANCES = (0.5, 1.0, 1.5, 2.0)  # grados C por lectura
THRESHOLDS = (8, 20, 40, 60, 80)  # grados C x lecturas
LABELS = ('control', 'suave', 'gradual', 'fuerte')


def load_run(run_id):
    path = RESULTS / run_id
    samples_path = path / 'readings_sent.jsonl'
    truth_path = path / 'ground_truth.json'
    summary_path = path / 'summary.json'
    for p in (samples_path, truth_path, summary_path):
        if not p.is_file():
            raise FileNotFoundError(f'Falta archivo: {p}')
    with samples_path.open(encoding='utf-8') as fh:
        readings = [json.loads(line) for line in fh if line.strip()]
    truth = json.loads(truth_path.read_text(encoding='utf-8'))
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    if len(readings) != int(summary['published']):
        raise ValueError(f'{run_id}: número de lecturas distinto de published')
    sensor_names = {str(s) for s in summary['sensors']}
    indexed, windows = {}, {}
    for row in readings:
        node = str(row['message']['node_id'])
        tick = int(row['tick'])
        if node not in sensor_names or (node, tick) in indexed:
            raise ValueError(f'{run_id}: sensor desconocido o lectura repetida')
        indexed[(node, tick)] = row
        if float(row.get('injected_temperature_increase_c', 0)) > 0:
            windows.setdefault(node, []).append(tick)
    return {'readings': readings, 'truth': truth, 'indexed': indexed,
            'windows': windows, 'sensors': sensor_names, 'run_id': run_id}


def check_paired_control(control, event, label):
    """Comprueba que lo único cambiado frente al control es la inyección de T."""
    if set(control['indexed']) != set(event['indexed']):
        raise ValueError(f'{label}: sensores y pasos no coinciden con el control')
    for key in control['indexed']:
        base = control['indexed'][key]
        altered = event['indexed'][key]
        orig = float(base['message']['measurements']['air_temperature_c'])
        modified = float(altered['message']['measurements']['air_temperature_c'])
        injected = float(altered.get('injected_temperature_increase_c', 0))
        if not math.isclose(modified, orig + injected, abs_tol=1e-5):
            raise ValueError(f'{label}: {key} no coincide con control + inyección')
    if event['sensors'] != control['sensors']:
        raise ValueError(f'{label}: sensores distintos del control')
    if float(event['truth']['virtual_step_seconds']) != float(control['truth']['virtual_step_seconds']):
        raise ValueError(f'{label}: pasos virtuales distintos del control')
    if not event['windows']:
        raise ValueError(f'{label}: no contiene perturbación positiva')


def alarm_ticks(readings, allowance, threshold):
    detector = CUSUMDetector(measurement_field='air_temperature_c', unit='C',
                             allowance=allowance, threshold=threshold)
    alarms = {}
    for row in readings:
        alarm = detector.evaluate(row['message'])
        if alarm is not None:
            alarms[str(alarm['node_id'])] = int(row['tick'])
    return alarms


def assess_event(alarms, control_alarms, windows, virtual_step_seconds):
    """Contar coincidencias temporales, y señales adelantadas respecto al control.

    'señal adelantada' = alarma en ventana inyectada y el control del mismo
    sensor no alerta, o alerta en un paso estrictamente posterior. No es
    validación fuera de muestra ni demuestra causalidad sobre incendios reales.
    """
    in_window, earlier_than_control, delays = [], [], {}
    for sensor, active in sorted(windows.items()):
        tick = alarms.get(sensor)
        if tick is None or not (active[0] <= tick <= active[-1]):
            continue
        in_window.append(sensor)
        ctrl_tick = control_alarms.get(sensor)
        if ctrl_tick is None or tick < ctrl_tick:
            earlier_than_control.append(sensor)
            delays[sensor] = round((tick-active[0])*virtual_step_seconds/60, 3)
    return {'in_window': in_window, 'earlier_than_control': earlier_than_control,
            'virtual_delays_min': delays}


def evaluate(loaded, allowance, threshold):
    c = loaded['control']
    control_alarms = alarm_ticks(c['readings'], allowance, threshold)
    item = {'allowance_c': allowance, 'threshold_c_samples': threshold,
            'false_alert_sensors_control': len(control_alarms),
            'false_alert_ids_control': sorted(control_alarms),
            'control_alarm_tick_by_sensor': control_alarms}
    for label in ('suave', 'gradual', 'fuerte'):
        run = loaded[label]
        alarms = alarm_ticks(run['readings'], allowance, threshold)
        scored = assess_event(alarms, control_alarms, run['windows'],
                              float(run['truth']['virtual_step_seconds']))
        item[f'{label}_alerts_in_event_window'] = len(scored['in_window'])
        item[f'{label}_earlier_than_control'] = len(scored['earlier_than_control'])
        item[f'{label}_earlier_ids'] = scored['earlier_than_control']
        item[f'{label}_virtual_delays_min'] = scored['virtual_delays_min']
        item[f'{label}_alarm_tick_by_sensor'] = alarms
    return item


def main(args):
    if len(args) != 4:
        print('USO: sweep_cusum.py RUN_CONTROL RUN_SUAVE RUN_GRADUAL RUN_FUERTE')
        return 2
    loaded = {name: load_run(identifier) for name, identifier in zip(LABELS, args)}
    if loaded['control']['windows']:
        raise ValueError('El primer RUN no es un control sin perturbación')
    for name in LABELS[1:]:
        check_paired_control(loaded['control'], loaded[name], name)
    rows = [evaluate(loaded, k, h) for k in ALLOWANCES for h in THRESHOLDS]
    print('\nBARRIDO CUSUM — EXPLORATORIO, SOLO DATOS GUARDADOS')
    print('Parámetros: k = desviación tolerada (°C/muestra); h = umbral acumulado (°C·muestras)')
    print('CONTROL_FP = sensores con alarma sin evento; EN_VENTANA = alarmas durante la perturbación;')
    print('ADELANTA = alarmas en la ventana que ocurren antes que en el control pareado.\n')
    print(f'{"k":>4} {"h":>4} | {"FP control":>10} | {"Gradual (en/adel.)":>19} | {"Suave (en/adel.)":>19} | {"Fuerte (en/adel.)":>19}')
    for r in rows:
        numbers = [f"{r[label+'_alerts_in_event_window']}/2 / {r[label+'_earlier_than_control']}/2"
                   for label in ('gradual', 'suave', 'fuerte')]
        print(f"{r['allowance_c']:>4g} {r['threshold_c_samples']:>4g} | "
              f"{r['false_alert_sensors_control']:>10} | "
              f"{numbers[0]:>19} | {numbers[1]:>19} | {numbers[2]:>19}")
    now = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    outfile = RESULTS / f'cusum_sweep_{now}.csv'
    jsonpath = RESULTS / f'cusum_sweep_{now}.json'
    cols = ['allowance_c', 'threshold_c_samples', 'false_alert_sensors_control',
            'gradual_alerts_in_event_window', 'gradual_earlier_than_control',
            'suave_alerts_in_event_window', 'suave_earlier_than_control',
            'fuerte_alerts_in_event_window', 'fuerte_earlier_than_control']
    with outfile.open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    report = {'type': 'exploratory_cusum_parameter_sweep',
              'run_ids': dict(zip(LABELS, args)), 'config': {'k_values': ALLOWANCES, 'h_values': THRESHOLDS},
              'disclaimer': 'Se usan los mismos datos para inspección y selección de umbral. No son resultados independientes ni precisión de incendios reales.',
              'rows': rows}
    jsonpath.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\nCSV: results/{outfile.name}')
    print(f'JSON: results/{jsonpath.name}')
    print('NOTA: no elegir un umbral como validado solo con estos cuatro escenarios.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except (FileNotFoundError, ValueError, KeyError, TypeError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
