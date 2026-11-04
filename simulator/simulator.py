"""Simulador didactico: NO usa datos reales ni pretende detectar incendios."""
import json
import os
import random
import time
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

HOST = os.environ.get("MQTT_HOST", "mosquitto")
N = max(1, int(os.environ.get("SENSOR_COUNT", "5")))
PERIOD = max(0.2, float(os.environ.get("INTERVAL_SECONDS", "2")))
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
while True:
    try:
        client.connect(HOST, 1883, 60)
        break
    except OSError:
        print("Esperando a Mosquitto...", flush=True)
        time.sleep(2)
client.loop_start()
print(f"Generando datos sinteticos de {N} sensores cada {PERIOD} s", flush=True)
random.seed(42)
try:
    while True:
        for i in range(1, N + 1):
            doc = {
                "node_id": f"sensor_{i:03d}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "reading",
                "source": "synthetic_demo",
                "measurements": {
                    "air_temperature_c": round(25 + random.uniform(-3, 3), 2),
                    "relative_humidity_pct": round(45 + random.uniform(-8, 8), 2),
                },
            }
            topic = f"wildfiresense/readings/{doc['node_id']}"
            info = client.publish(topic, json.dumps(doc, ensure_ascii=False), qos=0)
            print(f"{topic}: {doc['measurements']} (mqtt_rc={info.rc})", flush=True)
        time.sleep(PERIOD)
except KeyboardInterrupt:
    print("Deteniendo simulador...", flush=True)
finally:
    client.loop_stop()
    client.disconnect()
