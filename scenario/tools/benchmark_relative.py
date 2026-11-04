"""WildfireSense — experimento pareado de detector relativo sobre datos ALINEADOS.

No procesa MQTT, ni genera alarmas oficiales. Los eventos son SINTETICOS;
los CSV de origen permanecen intactos. Para grupos de 3+ sensores, compara
mediciones normales con una perturbacion de +6 C inyectada en UN sensor.
Los pasos son muestras alineadas; los huecos de tiempo no se interpolan.
"""

import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tools.analyze_relative import analyse_rows

PERIODS = ('mayo', 'octubre')
THRESHOLDS_C = (2.0, 3.0, 4.0, 6.0)
AMP_C = 6.0
RAMP_SAMPLES = 6
BASELINE_SAMPLES = 5
MIN_SLOTS = 12
CONSECUTIVE = 2
CSV_FIELDS = (
    'period', 'group', 'num_sensors', 'aligned_samples', 'threshold_c',
    'control_sensors_with_alert', 'single_sensor_injection_trials',
    'trials_with_target_alert_after_start', 'trials_attributable_by_paired_control',
    'trials_with_collateral_early_alert', 'median_attributable_delay_min',
)


def parse_utc(value):
    timestamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError('Timestamp sin zona horaria')
    return timestamp.astimezone(timezone.utc)


def load_aligned(path):
    with Path(path).open('r', encoding='utf-8-sig', newline='') as src:
        rows = list(csv.DictReader(src))
    # Validacion de integridad y alineacion (tambien de offsets/no interpolacion).
    analyse_rows(rows, Path(path).stem)
    return rows


def split_groups(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[r['group']].append(dict(r))
    return dict(groups)


def indexed_series(rows, period):
    """Mapea sensor a su serie de valores relativos ordenada temporalmente."""
    detail, _ = analyse_rows(rows, period, baseline_slots=BASELINE_SAMPLES, min_slots=MIN_SLOTS)
    by_sensor = defaultdict(list)
    for row in detail:
        by_sensor[row['sensor']].append(row)
    for sensor, measurements in by_sensor.items():
        measurements.sort(key=lambda r: parse_utc(r['time_utc']))
    return dict(by_sensor)


def first_positive_alert(series, threshold_c, consecutive=CONSECUTIVE):
    """Primer índice que confirma dos excedencias positivas consecutivas."""
    if not math.isfinite(threshold_c) or threshold_c <= 0:
        raise ValueError('Umbral positivo finito necesario')
    if consecutive < 1:
        raise ValueError('Consecutivas debe ser >=1')
    streak = 0
    for i, row in enumerate(series):
        if i < BASELINE_SAMPLES:
            continue
        if float(row['change_from_baseline_c']) >= threshold_c:
            streak += 1
        else:
            streak = 0
        if streak == consecutive:
            return i
    return None


def inject_one_sensor(rows, sensor, start_index, amp_c=AMP_C, ramp_samples=RAMP_SAMPLES):
    """Crea copia de las filas; NO cambia ni archivo ni lista original."""
    if not math.isfinite(amp_c) or amp_c <= 0 or ramp_samples < 1:
        raise ValueError('Configuracion de perturbacion no valida')
    indexes = sorted({parse_utc(r['aligned_time_utc']) for r in rows})
    if start_index < BASELINE_SAMPLES or start_index >= len(indexes):
        raise ValueError('Inicio fuera de la ventana posterior al calentamiento')
    positions = {t: i for i, t in enumerate(indexes)}
    out = []
    target_count = 0
    for r in rows:
        copy = dict(r)
        if r['virtual_sensor'] == sensor:
            target_count += 1
            idx = positions[parse_utc(r['aligned_time_utc'])]
            if idx >= start_index:
                delta = amp_c * min(1.0, (idx-start_index+1)/ramp_samples)
                copy['temperature_c'] = str(float(r['temperature_c'])+delta)
        out.append(copy)
    if target_count != len(indexes):
        raise ValueError('El sensor objetivo no cubre todos los instantes')
    return out


def is_attributable(event_index, control_index, start_index):
    """Indicador causal limitado al replay pareado, no a incendios reales."""
    return (event_index is not None and event_index >= start_index and
            (control_index is None or event_index < control_index))


def analyze_group(period, group, rows, thresholds=THRESHOLDS_C):
    control = indexed_series(rows, period)
    sensors = sorted(control)
    if len(sensors) < 3:
        return [], [], {'period':period,'group':group,'skipped':'menos de 3 sensores: atribucion ambigua'}
    n = len(next(iter(control.values())))
    if n < MIN_SLOTS:
        return [], [], {'period':period,'group':group,'skipped':'menos de 12 instantes completos'}
    if any(len(x) != n for x in control.values()):
        raise ValueError('Serie incompleta o desequilibrada')
    start = max(BASELINE_SAMPLES+2, n//2)
    if start + 1 >= n:
        raise ValueError('Menos de dos instantes de evento')
    control_detection = {h: {s:first_positive_alert(control[s],h) for s in sensors}
                         for h in thresholds}
    event_series = {}
    for s in sensors:
        injected = inject_one_sensor(rows, s, start)
        event_series[s] = indexed_series(injected, period)
    details, summaries = [], []
    for h in thresholds:
        detected_after = attributable = collateral_trials = 0
        delays = []
        fp_control = sum(control_detection[h][s] is not None for s in sensors)
        for target in sensors:
            scenario_series = event_series[target]
            event_idx = first_positive_alert(scenario_series[target], h)
            control_idx = control_detection[h][target]
            after = event_idx is not None and event_idx >= start
            paired = is_attributable(event_idx, control_idx, start)
            delayed_minutes = None
            if paired:
                start_time = parse_utc(control[target][start]['time_utc'])
                event_time = parse_utc(control[target][event_idx]['time_utc'])
                delayed_minutes = round((event_time-start_time).total_seconds()/60,2)
                delays.append(delayed_minutes)
            collateral = []
            for other in sensors:
                if other == target: continue
                other_idx = first_positive_alert(scenario_series[other], h)
                if is_attributable(other_idx,control_detection[h][other],start):
                    collateral.append(other)
            detected_after += bool(after)
            attributable += bool(paired)
            collateral_trials += bool(collateral)
            details.append({
                'period': period, 'group': group, 'target_sensor': target,
                'threshold_c': h, 'event_start_index': start,
                'event_start_time_utc': control[target][start]['time_utc'],
                'control_first_alert_index': control_idx,
                'event_first_alert_index': event_idx,
                'target_alert_after_start': bool(after),
                'paired_attributable': bool(paired),
                'paired_delay_minutes': delayed_minutes,
                'other_sensors_with_early_alert': collateral,
                'injected_amp_c': AMP_C, 'ramp_aligned_samples': RAMP_SAMPLES,
            })
        summaries.append({
            'period':period,'group':group, 'num_sensors':len(sensors),
            'aligned_samples':n,'threshold_c':h,
            'control_sensors_with_alert':fp_control,
            'single_sensor_injection_trials':len(sensors),
            'trials_with_target_alert_after_start':detected_after,
            'trials_attributable_by_paired_control':attributable,
            'trials_with_collateral_early_alert':collateral_trials,
            'median_attributable_delay_min':round(statistics.median(delays),2) if delays else None,
        })
    return summaries, details, None


def run(results_dir=Path('/app/results')):
    all_summaries, all_details, skipped = [], [], []
    for period in PERIODS:
        path = results_dir / f'alineado_{period}.csv'
        rows = load_aligned(path)
        for group, group_rows in sorted(split_groups(rows).items()):
            summary, detail, skip = analyze_group(period, group, group_rows)
            if skip:
                skipped.append(skip)
                print(f'{period.upper()} | {group}: EXCLUIDO — {skip["skipped"]}')
            else:
                all_summaries.extend(summary)
                all_details.extend(detail)
                print(f'\n{period.upper()} | {group} | {summary[0]["num_sensors"]} sensores '
                      f'| {summary[0]["aligned_samples"]} instantes alineados')
                for r in summary:
                    print(f'  umbral {r["threshold_c"]:g} °C: control {r["control_sensors_with_alert"]} '
                          f'sensores con alerta; perturbación atribuible '
                          f'{r["trials_attributable_by_paired_control"]}/'
                          f'{r["single_sensor_injection_trials"]} pruebas; '
                          f'colaterales {r["trials_with_collateral_early_alert"]} pruebas')
    if not all_summaries:
        raise ValueError('No existen grupos >=3 sensores con >=12 instantes completos')
    results_dir.mkdir(parents=True,exist_ok=True)
    csv_file=results_dir/'piloto_detector_relativo.csv'
    json_file=results_dir/'piloto_detector_relativo.json'
    with csv_file.open('w',newline='',encoding='utf-8-sig') as out:
        w=csv.DictWriter(out,fieldnames=CSV_FIELDS)
        w.writeheader(); w.writerows(all_summaries)
    json_file.write_text(json.dumps({
        'method':'positive change in T_sensor - median(other sensors), relative to first 5 aligned samples; 2 consecutive positives',
        'experiment':'inject +6 C into ONE sensor only, ramped across 6 aligned samples, starting at half of the group',
        'thresholds_c':THRESHOLDS_C,'results':all_summaries,'trials':all_details,'excluded':skipped,
        'limitations':[
            'Estudio EXPLORATORIO, umbrales no validados y SIN incendios reales',
            'El control original no tiene etiquetas garantizadas de ausencia de fuego',
            'Experimentos aislados por sensor sobre una misma muestra historica; no son ensayos independientes',
            'Un grupo de dos sensores no permite atribucion: se excluye',
            'Intervalos reales entre instantes alineados pueden tener huecos: retraso medido usando timestamps, no 2 min por paso',
            'Se necesita calibracion con unas fechas y validacion con otras, mas datos y comprobacion de proximidad fisica',
            'No se publica ninguna alarma MQTT ni se modifica el Edge',
        ]},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'\nCSV: results/{csv_file.name}')
    print(f'JSON: results/{json_file.name}')
    print('SOLO experimento offline con perturbaciones sinteticas; no ajustar o desplegar alarmas basandose en este piloto.')


if __name__=='__main__':
    try:
        run()
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(f'ERROR: {exc}') from exc
