"""MQTT smoke-test source only; NOT a wildfire training dataset."""
import json
import math
import os
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

HOST = os.environ.get("MQTT_HOST", "mosquitto")
NODES = max(1, min(1000, int(os.environ.get("SENSOR_COUNT", "5"))))
PERIOD = max(0.2, float(os.environ.get("INTERVAL_SECONDS", "10")))
RUN_ID = os.environ.get("RUN_ID", "mqtt_demo_run")
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="wildfiresense-demo-sensor-generator")
while True:
    try:
        client.connect(HOST, 1883, keepalive=60)
        break
    except OSError:
        print("Waiting for MQTT broker...", flush=True)
        time.sleep(2)
client.loop_start()
print(f"Demo: {NODES} virtual sensors, {PERIOD}s cadence. Not training data.", flush=True)
seed = 42
seq = 0
try:
    while True:
        for index in range(1, NODES + 1):
            node = f"node_{index:04d}"
            rng = random.Random(seed + index * 10007 + seq * 1000003)
            pm25 = max(0.0, 8.0 + rng.gauss(0, 0.7))
            pm10 = pm25 + 11.0 + abs(rng.gauss(0, 1.2))
            temperature = 25.0 + 0.8 * math.sin(seq / 18) + rng.gauss(0, 0.2)
            humidity = 50.0 - 2.0 * math.sin(seq / 18) + rng.gauss(0, 0.8)
            now = datetime.now(timezone.utc).isoformat()
            message = {
                "schema_version": 1, "run_id": RUN_ID, "node_id": node,
                "seq": seq, "type": "reading", "timestamp": now,
                "emitted_at": now, "timebase": "wall", "source": "synthetic_mqtt_smoke_test",
                "test_only": True,
                "measurements": {
                    "pm25_ug_m3": round(pm25, 2),
                    "pm10_ug_m3": round(pm10, 2),
                    "air_temperature_c": round(temperature, 2),
                    "relative_humidity_pct": round(max(0, min(100, humidity)), 2),
                },
            }
            client.publish(f"wildfiresense/readings/{node}", json.dumps(message), qos=0)
        if seq % 10 == 0:
            print(f"MQTT demo sweep seq={seq}, nodes={NODES}", flush=True)
        seq += 1
        time.sleep(PERIOD)
except KeyboardInterrupt:
    pass
finally:
    client.loop_stop()
    client.disconnect()
