
"""
WildfireSense - Servicio principal del nodo Edge.

Funciones:
1. Recibir datos de sensores mediante MQTT.
2. Validar los mensajes JSON.
3. Ejecutar el detector estadístico de logic.py.
4. Procesar eventos SOS de forma independiente.
5. Medir los tiempos de procesamiento.
6. Publicar alarmas mediante MQTT.
"""

import json
import os
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from logic import decide_reading, decide_sos


# ==========================================
# 1. CONFIGURACIÓN GENERAL
# ==========================================

HOST = os.environ.get("MQTT_HOST", "mosquitto")
PORT = int(os.environ.get("MQTT_PORT", "1883"))

COOLDOWN = float(
    os.environ.get("ALARM_COOLDOWN_SECONDS", "30")
)

READINGS_TOPIC = "wildfiresense/readings/#"
SOS_TOPIC = "wildfiresense/events/sos"
ALERTS_TOPIC = "wildfiresense/edge/alerts"


# ==========================================
# 2. MEMORIA Y MÉTRICAS DEL EDGE
# ==========================================

# Última alarma ambiental por sensor.
LAST_ALERT = {}

# Estadísticas acumuladas durante la ejecución.
METRICS = {
    "readings": 0,
    "total_ms": 0.0,
    "max_ms": 0.0,
    "environmental_alerts": 0,
    "sos_alerts": 0,
    "invalid_messages": 0,
}


# ==========================================
# 3. CONEXIÓN CON MOSQUITTO
# ==========================================

def on_connect(client, userdata, flags, reason_code, properties):

    if reason_code.is_failure:
        print(
            f"No se pudo conectar: {reason_code}",
            flush=True
        )
        return

    print("Edge conectado a Mosquitto", flush=True)

    # Suscripción a las lecturas ambientales.
    client.subscribe(READINGS_TOPIC, qos=0)

    # Suscripción independiente para eventos SOS.
    client.subscribe(SOS_TOPIC, qos=1)


# ==========================================
# 4. RECEPCIÓN Y PROCESAMIENTO MQTT
# ==========================================

def on_message(client, userdata, msg):

    # Iniciamos la medición temporal.
    start_time = time.perf_counter()

    # PASO A: Interpretar el mensaje JSON.
    try:
        data = json.loads(
            msg.payload.decode("utf-8")
        )

        if not isinstance(data, dict):
            raise ValueError(
                "Se esperaba un objeto JSON"
            )

    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:

        METRICS["invalid_messages"] += 1

        print(
            f"Mensaje inválido en {msg.topic}: {exc}",
            flush=True
        )
        return

    # PASO B: Elegir el procesamiento correspondiente.
    is_sos = msg.topic == SOS_TOPIC

    if is_sos:

        # El SOS no necesita el detector Z-score.
        alarm = decide_sos(data)

    elif msg.topic.startswith("wildfiresense/readings/"):

        # Ejecutamos el detector de logic.py.
        alarm = decide_reading(data)

        # Tiempo empleado en interpretar y procesar.
        elapsed_ms = (
            time.perf_counter() - start_time
        ) * 1000

        METRICS["readings"] += 1
        METRICS["total_ms"] += elapsed_ms

        METRICS["max_ms"] = max(
            METRICS["max_ms"],
            elapsed_ms
        )

        # Mostrar estadísticas cada 50 lecturas.
        if METRICS["readings"] % 50 == 0:

            average_ms = (
                METRICS["total_ms"] /
                METRICS["readings"]
            )

            print(
                f"EDGE_METRICS "
                f"readings={METRICS['readings']} "
                f"avg_ms={average_ms:.3f} "
                f"max_ms={METRICS['max_ms']:.3f} "
                f"alerts={METRICS['environmental_alerts']}",
                flush=True
            )

    else:
        return

    # PASO C: Comprobar si existe una alarma.
    if alarm is None:
        return

    # PASO D: Aplicar cooldown solo a alarmas ambientales.
    if not is_sos:

        node = alarm["node_id"]
        now = time.monotonic()

        last_time = LAST_ALERT.get(
            node, float("-inf")
        )

        if now - last_time < COOLDOWN:
            return

    # Copiamos la alarma para añadir metadatos.
    alarm = dict(alarm)

    # PASO E: Medir tiempo hasta preparar la alarma.
    alarm["edge_processing_ms"] = round(
        (time.perf_counter() - start_time) * 1000,
        3
    )

    # Conservar la fecha original de la medida.
    if isinstance(data.get("timestamp"), str):
        alarm["reading_timestamp"] = data["timestamp"]

    # Fecha real de generación de la alarma.
    alarm["generated_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    # PASO F: Registrar la alarma localmente.
    print(
        f"ALARMA LOCAL: "
        f"{json.dumps(alarm, ensure_ascii=False)}",
        flush=True
    )

    # PASO G: Publicar la alarma por MQTT.
    info = client.publish(
        ALERTS_TOPIC,
        json.dumps(alarm, ensure_ascii=False),
        qos=1,
        retain=False
    )

    if info.rc != mqtt.MQTT_ERR_SUCCESS:

        print(
            f"Error de publicación: {info.rc}",
            flush=True
        )
        return

    # Actualizar contadores de alarmas aceptadas
    # para publicación por el cliente MQTT.
    if is_sos:

        METRICS["sos_alerts"] += 1

    else:

        METRICS["environmental_alerts"] += 1
        LAST_ALERT[node] = time.monotonic()


# ==========================================
# 5. EJECUCIÓN CONTINUA DEL EDGE
# ==========================================

def main():

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="wildfiresense-edge-demo"
    )

    client.on_connect = on_connect
    client.on_message = on_message

    while True:

        try:
            print(
                f"Conectando a {HOST}:{PORT}...",
                flush=True
            )

            client.connect(
                HOST,
                PORT,
                keepalive=60
            )

            client.loop_forever(
                retry_first_connection=True
            )

        except OSError as exc:

            print(
                f"Broker no disponible ({exc}). "
                f"Reintentando en 3 segundos.",
                flush=True
            )

            time.sleep(3)


# ==========================================
# 6. INICIO DEL PROGRAMA
# ==========================================

if __name__ == "__main__":
    main()
