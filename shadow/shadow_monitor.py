"""WildfireSense: CUSUM en modo sombra sobre MQTT real.

Este servicio no publica NINGÚN mensaje MQTT: registra detecciones
experimentales en los logs, manteniendo intacto el Edge principal.
Los parámetros son candidatos exploratorios, NO validados con incendios.
"""

import json
import os
import time
import re
from pathlib import Path
from datetime import datetime, timezone

from cusum import CUSUMDetector

TOPIC = os.environ.get("MQTT_READINGS_TOPIC", "wildfiresense/readings/#")
HOST = os.environ.get("MQTT_HOST", "mosquitto")
PORT = int(os.environ.get("MQTT_PORT", "1883"))


class ShadowMonitor:
    """Evaluación en paralelo de dos configuraciones CUSUM por sensor."""

    CANDIDATES = (
        ("sensible", 0.5, 20.0),
        ("conservador", 1.5, 80.0),
    )

    def __init__(self):
        self.detectors = {
            name: CUSUMDetector(
                measurement_field="air_temperature_c", unit="C",
                allowance=k, threshold=h,
            )
            for name, k, h in self.CANDIDATES
        }
        self.readings = 0
        self.invalid_json = 0
        self.alerts_by_candidate = {name: 0 for name, _, _ in self.CANDIDATES}
        self.total_ms = 0.0
        self.max_ms = 0.0

    def process(self, topic, payload):
        """Devuelve líneas informativas; no modifica broker ni publica alarmas."""
        if not topic.startswith("wildfiresense/readings/"):
            return []
        started = time.perf_counter()
        try:
            message = json.loads(payload.decode("utf-8"))
            if not isinstance(message, dict):
                raise ValueError("JSON no es un objeto")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self.invalid_json += 1
            return [f"SHADOW_INVALID_JSON topic={topic} reason={exc}"]

        outputs = []
        for candidate, detector in self.detectors.items():
            alarm = detector.evaluate(message)
            if alarm is not None:
                self.alerts_by_candidate[candidate] += 1
                record = {
                    "candidate": candidate,
                    "node_id": alarm["node_id"],
                    "reading_timestamp": message.get("timestamp"),
                    "observed_value_c": alarm["observed_value"],
                    "cusum_score": alarm["cusum_score"],
                    "threshold": alarm["threshold"],
                    "shadow_only": True,
                }
                outputs.append("CUSUM_SHADOW " + json.dumps(record, ensure_ascii=False))

        elapsed_ms = (time.perf_counter() - started) * 1000
        self.readings += 1
        self.total_ms += elapsed_ms
        self.max_ms = max(self.max_ms, elapsed_ms)
        if self.readings % 50 == 0:
            counts = " ".join(
                f"{name}={count}"
                for name, count in self.alerts_by_candidate.items()
            )
            outputs.append(
                f"SHADOW_METRICS readings={self.readings} "
                f"avg_ms={self.total_ms / self.readings:.3f} "
                f"max_ms={self.max_ms:.3f} " + counts
            )
        return outputs


class ShadowSessionRecorder:
    """Recibe marcadores del runner y guarda detecciones en el RUN correcto.

    No publica MQTT; solo crea archivos de resultados en el volumen compartido.
    No utiliza etiquetas de evento para tomar decisiones.
    """

    RUN_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{12}Z$")
    CONTROL_TOPIC = "wildfiresense/scenario/control"

    def __init__(self, output_dir="/app/results"):
        self.root = Path(output_dir)
        self.monitor = ShadowMonitor()
        self.run_id = None

    def on_control(self, payload):
        try:
            data = json.loads(payload.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("No es un objeto JSON")
            run_id = data.get("run_id")
            kind = data.get("type")
            if not isinstance(run_id, str) or not self.RUN_PATTERN.fullmatch(run_id):
                raise ValueError("run_id inválido")
            if kind not in ("start", "end"):
                raise ValueError("marcador desconocido")
        except (UnicodeDecodeError, ValueError, TypeError) as exc:
            return [f"SHADOW_BAD_CONTROL {exc}"]

        if kind == "start":
            if self.run_id is not None:
                return ["SHADOW_SESSION_ERROR ya hay un escenario activo; ignoro start"]
            folder = self.root / run_id
            # El runner crea esta carpeta antes de enviar el marcador.
            if not folder.is_dir():
                return [f"SHADOW_SESSION_ERROR falta carpeta de resultados {run_id}"]
            self.monitor = ShadowMonitor()  # Cada escenario arranca con historial vacío.
            self.run_id = run_id
            (folder / "shadow_events.jsonl").write_text("", encoding="utf-8")
            return [f"SHADOW_SESSION_START run_id={run_id}"]

        if self.run_id != run_id:
            return [f"SHADOW_SESSION_ERROR end sin start correspondiente: {run_id}"]

        summary = {
            "run_id": run_id,
            "session_closed": True,
            "readings_received": self.monitor.readings,
            "invalid_json": self.monitor.invalid_json,
            "detections_by_candidate": dict(self.monitor.alerts_by_candidate),
            "mean_processing_ms": round(self.monitor.total_ms / self.monitor.readings, 6)
                if self.monitor.readings else None,
            "max_processing_ms": round(self.monitor.max_ms, 6),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "notes": "Solo observación. No se envían alertas MQTT desde el Shadow.",
        }
        folder = self.root / run_id
        (folder / "shadow_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.run_id = None
        return [f"SHADOW_SESSION_END run_id={run_id} readings={summary['readings_received']} "
                f"detections={summary['detections_by_candidate']}"]

    def on_reading(self, topic, payload):
        if self.run_id is None:
            # Protege contra mezclar lecturas de otro simulador o fuera de escenario.
            return []
        outputs = self.monitor.process(topic, payload)
        folder = self.root / self.run_id
        with (folder / "shadow_events.jsonl").open("a", encoding="utf-8") as file:
            for line in outputs:
                if line.startswith("CUSUM_SHADOW "):
                    record = json.loads(line[len("CUSUM_SHADOW "):])
                    record["run_id"] = self.run_id
                    record["received_at"] = datetime.now(timezone.utc).isoformat()
                    file.write(json.dumps(record, ensure_ascii=False) + "\n")
        return outputs


def main():
    # La dependencia MQTT solo se necesita en el contenedor; los tests de
    # ShadowMonitor pueden ejecutarse sin conectar con un broker.
    import paho.mqtt.client as mqtt

    recorder = ShadowSessionRecorder()
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="wildfiresense-cusum-shadow",
    )

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"SHADOW_CONNECT_ERROR {reason_code}", flush=True)
            return
        print("SHADOW_CONNECTED MQTT; modo solo observación", flush=True)
        client.subscribe(TOPIC, qos=0)
        client.subscribe(ShadowSessionRecorder.CONTROL_TOPIC, qos=1)

    def on_message(client, userdata, msg):
        if msg.topic == ShadowSessionRecorder.CONTROL_TOPIC:
            lines = recorder.on_control(msg.payload)
        else:
            lines = recorder.on_reading(msg.topic, msg.payload)
        for line in lines:
            print(line, flush=True)

    client.on_connect = on_connect
    client.on_message = on_message

    print(
        "SHADOW_START candidates=" + ",".join(
            f"{name}(k={k:g},h={h:g})"
            for name, k, h in ShadowMonitor.CANDIDATES
        ) + "; MQTT publish deshabilitado",
        flush=True,
    )
    while True:
        try:
            client.connect(HOST, PORT, keepalive=60)
            client.loop_forever(retry_first_connection=True)
        except OSError as exc:
            print(f"SHADOW_BROKER_UNAVAILABLE {exc}; reintento 3s", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
