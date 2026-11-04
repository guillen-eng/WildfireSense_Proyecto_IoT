"""WildfireSense: compara cargas útiles de lecturas MQTT y alarmas Edge.

Uso: python traffic_report.py RUN_ID [RUN_ID ...]

Es una comparación de dos políticas hipotéticas de envío hacia Cloud:
  A) reenviar cada payload ambiental publicado por el simulador;
  B) reenviar exclusivamente cada payload de alarma oficial recibido.
No mide una conexión Cloud ni los bytes de red MQTT/TCP/IP.
"""
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/app/results')
RUN_PATTERN = re.compile(r'^\d{8}T\d{12}Z$')


def read_json(path):
    if not path.is_file():
        raise FileNotFoundError(f'Falta archivo: {path}')
    return json.loads(path.read_text(encoding='utf-8'))


def read_jsonl(path):
    if not path.is_file():
        raise FileNotFoundError(f'Falta archivo: {path}')
    output = []
    with path.open(encoding='utf-8') as f:
        for line_number, line in enumerate(f, start=1):
            if line.strip():
                try:
                    output.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f'{path.name}, línea {line_number}: JSON incorrecto') from exc
    return output


def mqtt_json_payload_bytes(value):
    """Replica json.dumps(value, ensure_ascii=False) usado al publicar MQTT.

    No incluye tópico, encabezados MQTT, TCP/IP, retransmisiones ni TLS.
    """
    if not isinstance(value, dict):
        raise ValueError('Un payload de lectura/alarma debe ser un objeto JSON')
    return len(json.dumps(value, ensure_ascii=False).encode('utf-8'))


def analyze_run(run_id, root=ROOT):
    if not RUN_PATTERN.fullmatch(run_id):
        raise ValueError(f'RUN_ID con formato incorrecto: {run_id}')
    folder = root / run_id
    summary = read_json(folder / 'summary.json')
    truth = read_json(folder / 'ground_truth.json')
    sent = read_jsonl(folder / 'readings_sent.jsonl')
    alerts = read_jsonl(folder / 'alerts_received.jsonl')

    if summary.get('run_id') != run_id:
        raise ValueError(f'{run_id}: summary.json no corresponde a este RUN_ID')
    if truth.get('run_id') != run_id:
        raise ValueError(f'{run_id}: ground_truth.json no corresponde a este RUN_ID')

    published = int(summary['published'])
    received = int(summary['alerts_total_received'])
    if published != len(sent):
        raise ValueError(f'{run_id}: {published} publicaciones pero {len(sent)} filas guardadas')
    if received != len(alerts):
        raise ValueError(f'{run_id}: {received} alarmas en resumen pero {len(alerts)} guardadas')
    if published <= 0:
        raise ValueError(f'{run_id}: no hay lecturas para analizar')

    inbound = 0
    for record in sent:
        if not isinstance(record, dict) or 'message' not in record:
            raise ValueError(f'{run_id}: una lectura no contiene message')
        inbound += mqtt_json_payload_bytes(record['message'])

    outbound = 0
    env_alerts = 0
    sos_alerts = 0
    for record in alerts:
        if not isinstance(record, dict) or 'alarm' not in record:
            raise ValueError(f'{run_id}: una alarma no contiene alarm')
        alarm = record['alarm']
        outbound += mqtt_json_payload_bytes(alarm)
        env_alerts += alarm.get('type') == 'environmental_alert'
        sos_alerts += alarm.get('type') == 'sos_alert'

    if env_alerts != int(summary['environmental_alerts_received']):
        raise ValueError(f'{run_id}: el total de alarmas ambientales no coincide')

    event_enabled = truth.get('event_enabled')
    if event_enabled is None:
        event_enabled = bool(truth.get('affected_sensors'))

    return {
        'run_id': run_id,
        'scenario': 'con_perturbacion' if event_enabled else 'sin_perturbacion',
        'readings_published': published,
        'official_alerts_received': received,
        'environmental_alerts_received': env_alerts,
        'sos_alerts_received': sos_alerts,
        'readings_payload_bytes': inbound,
        'alerts_payload_bytes': outbound,
        'hypothetical_messages_avoided': published - received,
        'hypothetical_message_reduction_pct': round(100 * (1 - received / published), 3),
        'hypothetical_payload_bytes_saved': inbound - outbound,
        'hypothetical_payload_reduction_pct': round(100 * (1 - outbound / inbound), 3),
        'event_without_official_environmental_alert': bool(event_enabled and env_alerts == 0),
    }


def save_report(rows, root=ROOT):
    now = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    json_path = root / f'traffic_report_{now}.json'
    csv_path = root / f'traffic_report_{now}.csv'
    report = {
        'method': 'offline_payload_comparison_not_real_cloud_traffic',
        'baseline': 'forward_all_original_reading_payloads',
        'alternative': 'forward_received_official_alert_payloads_only',
        'excluded': ['mqtt_headers', 'topic_bytes', 'tcp_ip', 'tls', 'retransmissions', 'actual_cloud_uplink'],
        'results': rows,
    }
    root.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    with csv_path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path


def main(args=None):
    args = sys.argv[1:] if args is None else args
    if not args:
        print('Uso: python traffic_report.py RUN_ID [RUN_ID ...]')
        return 2
    try:
        rows = [analyze_run(run_id) for run_id in args]
        json_path, csv_path = save_report(rows)
    except (OSError, KeyError, ValueError, TypeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    print('\nTRÁFICO EDGE — COMPARACIÓN DE PAYLOADS MQTT (OFFLINE)')
    for row in rows:
        print(f"{row['run_id']} [{row['scenario']}]")
        print(f"  Lecturas originales: {row['readings_published']} mensajes, {row['readings_payload_bytes']} bytes")
        print(f"  Alarmas oficiales:   {row['official_alerts_received']} mensajes, {row['alerts_payload_bytes']} bytes")
        print(f"  Reducción hipotética: {row['hypothetical_message_reduction_pct']:.2f}% mensajes, "
              f"{row['hypothetical_payload_reduction_pct']:.2f}% bytes de payload")
        if row['event_without_official_environmental_alert']:
            print('  ATENCIÓN: hubo perturbación y ninguna alarma ambiental; NO considerar ahorro como éxito.')
    print(f'JSON: {json_path}')
    print(f'CSV: {csv_path}')
    print('IMPORTANTE: no se ha implementado ni medido un enlace Cloud. No incluye cabeceras ni retransmisiones.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
