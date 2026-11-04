"""Detector CUSUM experimental de cambios positivos, independiente de MQTT.

Solo para COMPARAR algoritmos con escenarios sintéticos de WildfireSense.
No es un modelo físico ni una prueba de incendios reales.

CUSUM (una sola cara): S_t = max(0, S_(t-1) + x_t - mu_0 - k)
Alerta si S_t >= h. mu_0 se fija con las primeras 20 lecturas
por sensor. Un único aviso por sensor y evaluación.
"""

import math
import statistics
from collections import defaultdict


class CUSUMDetector:
    def __init__(
        self,
        measurement_field="air_temperature_c",
        unit="C",
        min_history=20,
        allowance=0.5,
        threshold=8.0,
    ):
        if min_history < 2 or allowance < 0 or threshold <= 0:
            raise ValueError("Parámetros CUSUM no válidos")
        self.measurement_field = measurement_field
        self.unit = unit
        self.min_history = int(min_history)
        self.allowance = float(allowance)
        self.threshold = float(threshold)
        self.history = defaultdict(list)
        self.baseline = {}
        self.scores = defaultdict(float)
        self.alarmed = set()

    def evaluate(self, message):
        if not isinstance(message, dict):
            return None
        node = message.get("node_id")
        if isinstance(node, bool) or not isinstance(node, (str, int)):
            return None
        node = str(node).strip()
        if not node:
            return None
        measurements = message.get("measurements")
        if not isinstance(measurements, dict):
            return None
        value = measurements.get(self.measurement_field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if not math.isfinite(value):
            return None
        value = float(value)

        if node not in self.baseline:
            history = self.history[node]
            history.append(value)
            if len(history) == self.min_history:
                self.baseline[node] = statistics.mean(history)
            return None

        # Versión inicial: emite como máximo una alarma por sensor.
        if node in self.alarmed:
            return None

        difference = value - self.baseline[node] - self.allowance
        self.scores[node] = max(0.0, self.scores[node] + difference)
        if self.scores[node] < self.threshold:
            return None

        self.alarmed.add(node)
        return {
            "type": "environmental_alert",
            "priority": "high",
            "detector": "cusum_experimental",
            "node_id": node,
            "measurement": self.measurement_field,
            "unit": self.unit,
            "observed_value": value,
            "baseline_mean": round(self.baseline[node], 3),
            "cusum_score": round(self.scores[node], 3),
            "threshold": self.threshold,
            "reason": "accumulated_positive_shift",
            "test_only": True,
        }
