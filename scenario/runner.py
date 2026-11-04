"""Simulador de escenarios WildfireSense: replay real + evento sintético separado.

Publica una serie real de RESISTO en MQTT e introduce un escenario de prueba
controlado para evaluar la cadena IoT. No reproduce física de incendios real.
"""
import csv
import json
import math
import os
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Event, Lock


def load_replay(path: str, num_sensors: int):
    """Lee las filas históricas por sensor, preservando los timestamps originales."""
    sequences = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sequences[row["virtual_sensor"]].append(row)
    names = sorted(sequences)[:num_sensors]
    if len(names) < num_sensors:
        raise ValueError("No hay suficientes sensores en el CSV")
    return {name: sequences[name] for name in names}


def fire_delta(step: int, sensor: str, event: dict, recovery_steps: int) -> float:
    """Inyección experimental: subida gradual, meseta y recuperación.

    No corresponde a un modelo físico calibrado; es la señal de test.
    """
    if not event.get("enabled", True):
        return 0.0
    names=event.get("affected_sensors", [])
    if sensor not in names:
        return 0.0
    delay=event.get("second_sensor_delay_steps",0) if sensor==names[-1] and len(names)>1 else 0
    start=int(event["start_step"])+int(delay)
    duration=int(event["duration_steps"])
    maximum=float(event["max_temperature_increase_c"])
    if step < start:
        return 0.0
    t=step-start
    # Perfil configurable: si ramp_steps no aparece, conservamos el comportamiento anterior.
    ramp = int(event.get("ramp_steps", min(4, max(1, duration // 3))))
    if not (1 <= ramp <= duration):
        raise ValueError("ramp_steps debe estar entre 1 y duration_steps")
    if t < ramp:
        return maximum*(t+1)/ramp
    if t < duration:
        return maximum
    recovery_step=t-duration
    if recovery_step < recovery_steps:
        return maximum * (1-(recovery_step+1)/recovery_steps)
    return 0.0


def make_message(row: dict, *, step: int, virtual_time: str, temp_increase: float, source_label: str = "resisto_replay_with_test_injection") -> dict:
    """Mensaje MQTT para el Edge. NUNCA enviamos la etiqueta de incendio."""
    temp=float(row["temperature_c"])+temp_increase
    measurements={"air_temperature_c":round(temp,3)}
    try:
        h=float(row["humidity_percent"])
        if math.isfinite(h) and 0 <= h <=100:
            measurements["relative_humidity_pct"]=round(h,2)
    except (TypeError,ValueError):
        pass
    return {
        "node_id":row["virtual_sensor"],
        "timestamp":virtual_time,
        "type":"reading",
        "source":source_label,
        "source_time":row["source_time"],
        "source_sensor":row["source_sensor"],
        "measurements":measurements,
    }


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def publish_scenario_marker(client, action: str, run_id: str):
    """Etiqueta solo el inicio y fin del replay en un tópico experimental.

    No incluye ground truth, sensores afectados ni intensidad del evento.
    Los sensores y el Edge siguen recibiendo mensajes sin etiquetas.
    """
    payload = json.dumps({"type": action, "run_id": run_id})
    delivery = client.publish(
        "wildfiresense/scenario/control", payload, qos=1, retain=False
    )
    delivery.wait_for_publish(timeout=5)
    if not delivery.is_published():
        raise RuntimeError(f"No se confirmó marcador de escenario: {action}")


def main():
    # La biblioteca MQTT solo se necesita al ejecutar el contenedor Docker.
    import paho.mqtt.client as mqtt
    config_path=Path(os.environ.get("SCENARIO_CONFIG","config.json"))
    cfg=json.loads(config_path.read_text(encoding="utf-8"))
    seqs=load_replay(cfg["dataset"],int(cfg["num_sensors"]))
    total=int(cfg["total_steps"])
    if any(len(seq)<total for seq in seqs.values()):
        raise ValueError("El dataset reducido no tiene suficientes filas por sensor")
    event=cfg["event"]
    event_enabled = bool(event.get("enabled", True))
    host=os.environ.get("MQTT_HOST","mosquitto")
    port=int(os.environ.get("MQTT_PORT","1883"))
    results=Path('/app/results')
    results.mkdir(parents=True, exist_ok=True)
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    # Archivo único por ejecución. El historial no se pierde entre demostraciones.
    run_dir=results/run_id
    run_dir.mkdir()
    print(f"RESULTADOS: results/{run_id}",flush=True)
    ready=Event()
    lock=Lock()
    alerts=[]
    def on_connect(client,userdata,flags,reason_code,properties):
        if reason_code.is_failure:
            print(f"Fallo de conexión: {reason_code}",flush=True)
        else:
            client.subscribe('wildfiresense/edge/alerts',qos=1)
    def on_subscribe(client,userdata,mid,reason_codes,properties):
        ready.set()
    def on_message(client,userdata,msg):
        try:
            alert=json.loads(msg.payload.decode('utf-8'))
        except (ValueError,UnicodeDecodeError):
            return
        if not isinstance(alert,dict) or alert.get('node_id') not in seqs:
            return
        with lock:
            alerts.append({'received_at':utc_now(),'alarm':alert})
        print(f"ALERTA RECIBIDA: {alert.get('node_id')} {alert.get('type')}",flush=True)
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='wildfiresense-scenario-'+run_id[-12:])
    client.on_connect=on_connect
    client.on_subscribe=on_subscribe
    client.on_message=on_message
    deadline=time.monotonic()+20
    while True:
        try:
            client.connect(host,port,keepalive=30)
            break
        except OSError as exc:
            if time.monotonic()>=deadline:
                raise RuntimeError('No se pudo conectar al broker') from exc
            time.sleep(1)
    client.loop_start()
    if not ready.wait(15):
        raise RuntimeError('No se confirmó suscripción a wildfiresense/edge/alerts')
    # Pequeño margen para que el Edge complete la suscripción (ya ha sido iniciado).
    time.sleep(2)
    # Legacy runs keep the 2024-11-09 virtual clock. New datasets may declare their own.
    virtual_start=datetime.fromisoformat(cfg.get('virtual_start', '2024-11-09T00:00:00+00:00'))
    if virtual_start.tzinfo is None:
        raise ValueError('virtual_start debe contener información de zona horaria')
    ground_truth={'run_id':run_id,'dataset':cfg.get('dataset_label','RESISTO - muestra histórica 2024-11-09'),
                  'event_kind':('synthetic_temperature_perturbation_not_real_fire'
                                if event_enabled else 'normal_control_without_injected_event'),
                  'event_enabled': event_enabled,
                  'start_step':event['start_step'] if event_enabled else None,
                  'affected_sensors':event['affected_sensors'] if event_enabled else [],
                  'second_sensor_delay_steps':event['second_sensor_delay_steps'],
                  'duration_steps':event['duration_steps'],
                  'max_temperature_increase_c':event['max_temperature_increase_c'],
                  'virtual_step_seconds':cfg['virtual_step_seconds'],
                  'note':'Esta verdad de referencia queda fuera de los mensajes MQTT.'}
    (run_dir/'ground_truth.json').write_text(json.dumps(ground_truth,indent=2,ensure_ascii=False),encoding='utf-8')
    # Guardar configuracion exacta de esta ejecucion para experimentos reproducibles.
    (run_dir/'config_used.json').write_text(json.dumps(cfg,indent=2,ensure_ascii=False),encoding='utf-8')
    counts={'published':0,'environmental_alerts':0,'sos_alerts':0}
    try:
        publish_scenario_marker(client, "start", run_id)
        with (run_dir/'readings_sent.jsonl').open('w',encoding='utf-8') as output:
            scenario_label = (f"evento en paso {event['start_step']}" if event_enabled else "SIN EVENTO")
            print(f"Escenario: {len(seqs)} sensores, {total} pasos, {scenario_label}",flush=True)
            for tick in range(total):
                vtime=(virtual_start+timedelta(seconds=tick*float(cfg['virtual_step_seconds']))).isoformat()
                if event_enabled and tick==int(event['start_step']):
                    print('ESCENARIO: comienza evento sintético (Edge no conoce la etiqueta)',flush=True)
                for node,rows in seqs.items():
                    delta=fire_delta(tick,node,event,int(cfg['recovery_steps']))
                    msg=make_message(rows[tick],step=tick,virtual_time=vtime,temp_increase=delta,
                                     source_label=cfg.get('source_label','resisto_replay_with_test_injection'))
                    envelope={'tick':tick,'injected_temperature_increase_c':round(delta,2),'message':msg}
                    # El incremento SOLO se registra localmente, no se transmite en MQTT.
                    output.write(json.dumps(envelope,ensure_ascii=False)+'\n')
                    published=client.publish(f'wildfiresense/readings/{node}',json.dumps(msg,ensure_ascii=False),qos=1)
                    published.wait_for_publish(timeout=5)
                    if not published.is_published():
                        raise RuntimeError('No se confirmó publicación MQTT')
                    counts['published']+=1
                if tick % 10 == 0:
                    print(f"Paso {tick:02d}/{total}: {counts['published']} lecturas publicadas",flush=True)
                time.sleep(float(cfg['real_step_seconds']))
        # Dejar terminar el tratamiento de mensajes antes de cerrar.
        time.sleep(2)
        publish_scenario_marker(client, "end", run_id)
    finally:
        client.disconnect()
        client.loop_stop()
    with lock:
        received=list(alerts)
    with (run_dir/'alerts_received.jsonl').open('w',encoding='utf-8') as f:
        for a in received:
            f.write(json.dumps(a,ensure_ascii=False)+'\n')
    counts['environmental_alerts']=sum(a['alarm'].get('type')=='environmental_alert' for a in received)
    counts['sos_alerts']=sum(a['alarm'].get('type')=='sos_alert' for a in received)
    summary={'run_id':run_id,'event_enabled':event_enabled,'published':counts['published'],
             'environmental_alerts_received':counts['environmental_alerts'],
             'alerts_total_received':len(received),
             'sensors':list(seqs),
             'virtual_duration_min':round(total*float(cfg['virtual_step_seconds'])/60,2),
             'nominal_execution_seconds':round(total*float(cfg['real_step_seconds']),2),
             'notes':('Perturbacion sintetica sobre datos ambientales reales; no incendio real.'
                      if event_enabled else 'Control normal: datos ambientales de replay sin perturbacion inyectada.')}
    (run_dir/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    print('RESUMEN:',json.dumps(summary,ensure_ascii=False),flush=True)
    if event_enabled and not counts['environmental_alerts']:
        print('AVISO: no se observaron alarmas ambientales. Revisar logs del Edge y umbrales.',flush=True)
    if not event_enabled:
        print(f"CONTROL SIN EVENTO: {counts['environmental_alerts']} alertas ambientales (objetivo inicial: 0)",flush=True)


if __name__=='__main__':
    main()
