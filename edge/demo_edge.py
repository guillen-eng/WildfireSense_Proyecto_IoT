"""Demostración reproducible de WildfireSense (3 noviembre 2026).

Requisitos: paho-mqtt 2.1; Mosquitto y Edge funcionando en Docker.
Ejecutar DENTRO del contenedor edge: python demo_edge.py --nodes 1

Usa un identificador nuevo por ejecución, sin contaminar el historial anterior.
Las señales son SINTÉTICAS: no demuestran un incendio real.
"""

import argparse
import json
import os
import statistics
import threading
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

ALERT_TOPIC = "wildfiresense/edge/alerts"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Demonstration:
    def __init__(self, nodes, interval):
        self.nodes = nodes
        self.interval = interval
        self.tag = uuid.uuid4().hex[:8]
        self.node_ids = [f"demo_{self.tag}_{i:03d}" for i in range(1, nodes + 1)]
        self.sos_id = f"SOS_{self.tag}"
        self.subscribed = threading.Event()
        self.alert_events = {name: threading.Event() for name in self.node_ids + [self.sos_id]}
        self.sent_at = {}
        self.received = {}
        self.messages_sent = 0
        self.payload_bytes_in = 0
        self.payload_bytes_alerts = 0
        self.lock = threading.Lock()
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"wf-demo-{self.tag}",
        )
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"ERROR: conexión MQTT rechazada: {reason_code}", flush=True)
            return
        client.subscribe(ALERT_TOPIC, qos=1)

    def on_subscribe(self, client, userdata, mid, reason_code_list, properties):
        self.subscribed.set()

    def on_message(self, client, userdata, msg):
        try:
            alarm = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        node_id = alarm.get("node_id") if isinstance(alarm, dict) else None
        if node_id not in self.alert_events:
            return
        with self.lock:
            if node_id in self.received:
                return
            delay_ms = None
            if node_id in self.sent_at:
                delay_ms = (time.perf_counter() - self.sent_at[node_id]) * 1000
            self.received[node_id] = (alarm, delay_ms)
            self.payload_bytes_alerts += len(msg.payload)
        self.alert_events[node_id].set()

    def publish(self, topic, payload):
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        info = self.client.publish(topic, raw, qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Fallo al publicar MQTT, código {info.rc}")
        info.wait_for_publish(timeout=8)
        if not info.is_published():
            raise RuntimeError("No se confirmó el envío MQTT (PUBACK)")
        self.messages_sent += 1
        self.payload_bytes_in += len(raw.encode("utf-8"))
        time.sleep(self.interval)

    def reading(self, node_id, value):
        return {
            "node_id": node_id,
            "timestamp": utc_now(),
            "type": "reading",
            "source": "synthetic_demo_03nov",
            "measurements": {"sensible_heat_flux": float(value)},
        }

    def run(self):
        host = os.environ.get("MQTT_HOST", "mosquitto")
        port = int(os.environ.get("MQTT_PORT", "1883"))
        print(f"Conectando a {host}:{port} y suscribiendo a {ALERT_TOPIC} ...", flush=True)
        self.client.connect(host, port, keepalive=60)
        self.client.loop_start()
        try:
            if not self.subscribed.wait(timeout=8):
                raise RuntimeError("No se confirmó la suscripción al tópico de alertas")

            for node_id in self.node_ids:
                print(f"\n[{node_id}] 20 lecturas normales de 100 W/m²", flush=True)
                for _ in range(20):
                    self.publish(f"wildfiresense/readings/{node_id}", self.reading(node_id, 100))
                print(f"[{node_id}] primer pico: 150 W/m² (todavía sin alarma)", flush=True)
                self.publish(f"wildfiresense/readings/{node_id}", self.reading(node_id, 150))
                with self.lock:
                    self.sent_at[node_id] = time.perf_counter()
                print(f"[{node_id}] segundo pico: 150 W/m² (alarma esperada)", flush=True)
                self.publish(f"wildfiresense/readings/{node_id}", self.reading(node_id, 150))
                arrived = self.alert_events[node_id].wait(timeout=8)
                print(f"[{node_id}] {'ALARMA RECIBIDA' if arrived else 'SIN ALARMA: revisar logs del Edge'}", flush=True)

            print(f"\n[{self.sos_id}] envío SOS inmediato (sin calentamiento)", flush=True)
            with self.lock:
                self.sent_at[self.sos_id] = time.perf_counter()
            self.publish(
                "wildfiresense/events/sos",
                {"node_id": self.sos_id, "zone": "trail_A", "test_only": True},
            )
            sos_arrived = self.alert_events[self.sos_id].wait(timeout=8)
            print(f"[{self.sos_id}] {'SOS RECIBIDO' if sos_arrived else 'SIN SOS: revisar logs del Edge'}", flush=True)

            print("\n===== RESULTADOS DE DEMOSTRACIÓN LOCAL =====")
            print(f"Nodos ambientales: {self.nodes}")
            print(f"Mensajes publicados (lecturas + SOS): {self.messages_sent}")
            print(f"Alarmas recibidas: {len(self.received)} / {self.nodes + 1} esperadas")
            print(f"Bytes de payload publicados en entradas MQTT: {self.payload_bytes_in}")
            print(f"Bytes de payload recibidos en alertas MQTT: {self.payload_bytes_alerts}")
            print("NOTA: son bytes de payload y canales lógicos, NO ancho de banda cloud ni radio.")
            latencies = []
            for key in self.node_ids + [self.sos_id]:
                record = self.received.get(key)
                if record is None:
                    print(f"{key}: SIN ALARMA")
                    continue
                alarm, latency = record
                if latency is not None:
                    latencies.append(latency)
                print(
                    f"{key}: tipo={alarm.get('type')} prioridad={alarm.get('priority')} "
                    f"latencia_local_mqtt_ms={latency:.2f}" if latency is not None
                    else f"{key}: alarma recibida sin tiempo válido"
                )
            if latencies:
                print(f"Mediana de latencia local MQTT: {statistics.median(latencies):.2f} ms")
            print("Latencia local: desde publicación del evento que dispara alarma hasta recepción del aviso, mismo host.")
            print("NO incluye muestreo físico, radio, Cloud ni verificación de incendio real.")
            print("============================================")
            return len(self.received) == self.nodes + 1
        finally:
            self.client.disconnect()
            self.client.loop_stop()


def main():
    parser = argparse.ArgumentParser(description="Prueba MQTT automatizada del Edge de WildfireSense")
    parser.add_argument("--nodes", type=int, default=1, help="Número de nodos virtuales: 1 o 5")
    parser.add_argument("--interval", type=float, default=0.08, help="Pausa entre publicaciones (s)")
    args = parser.parse_args()
    if not 1 <= args.nodes <= 20:
        parser.error("--nodes debe estar entre 1 y 20 en esta prueba")
    if not 0 <= args.interval <= 2:
        parser.error("--interval debe estar entre 0 y 2 segundos")
    try:
        ok = Demonstration(args.nodes, args.interval).run()
    except Exception as exc:
        print(f"ERROR: {exc}", flush=True)
        raise SystemExit(2) from exc
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
