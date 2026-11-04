"""WildfireSense: detector estadistico experimental para el nodo Edge.

Detecta anomalías del flujo de calor sensible (W/m²) por sensor.
NO confirma incendios reales; los parámetros requieren evaluación.
"""

import math
import os
import statistics
from collections import deque

# 1. CONFIGURACIÓN DEL DETECTOR (valores provisionales)
HISTORY_SIZE = 30       # Maximo de lecturas normales guardadas por sensor
MIN_HISTORY = 20        # Lecturas normales requeridas antes de detectar
Z_SCORE_THRESHOLD = 4.0 # Umbral: media + 4 * desviacion estandar
MIN_STD = 1.0           # Suelo de desviacion estandar, en W/m² (experimental)
REQUIRED_CONSECUTIVE = 2


# 2. DETECTOR CON MEMORIA INDEPENDIENTE POR SENSOR
class ZScoreDetector:
    def __init__(self, measurement_field="sensible_heat_flux", unit="W/m2"):
        # Cada experimento debe seleccionar explícitamente su magnitud y unidad.
        self.measurement_field = measurement_field
        self.unit = unit
        self.history = {}                # node_id -> deque de medidas normales
        self.consecutive_anomalies = {}  # node_id -> anomalías consecutivas

    def evaluate(self, message: dict) -> dict | None:
        # 3. VALIDAR Y EXTRAER LA LECTURA
        if not isinstance(message, dict):
            return None

        node_id = message.get("node_id")
        if not isinstance(node_id, (str, int)) or isinstance(node_id, bool):
            return None
        node_id = str(node_id).strip()
        if not node_id:
            return None

        measurements = message.get("measurements")
        if not isinstance(measurements, dict):
            self.consecutive_anomalies[node_id] = 0
            return None

        value = measurements.get(self.measurement_field)
        if (isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)):
            self.consecutive_anomalies[node_id] = 0
            return None
        value = float(value)

        # 4. CREAR EL HISTORIAL SIN MEZCLAR SENSORES
        if node_id not in self.history:
            self.history[node_id] = deque(maxlen=HISTORY_SIZE)
            self.consecutive_anomalies[node_id] = 0
        node_history = self.history[node_id]

        # 5. CALENTAMIENTO: SIN HISTORIAL SUFICIENTE NO DETECTAMOS
        if len(node_history) < MIN_HISTORY:
            node_history.append(value)
            return None

        # 6. UMBRAL DINÁMICO CALCULADO ANTES DE AÑADIR LA LECTURA
        mean_val = statistics.mean(node_history)
        std_val = max(statistics.stdev(node_history), MIN_STD)
        threshold = mean_val + Z_SCORE_THRESHOLD * std_val
        is_anomaly = value > threshold

        # 7. CONFIRMACIÓN EN DOS MEDIDAS CONSECUTIVAS
        if not is_anomaly:
            self.consecutive_anomalies[node_id] = 0
            node_history.append(value)  # Solo datos considerados normales
            return None

        self.consecutive_anomalies[node_id] += 1
        if self.consecutive_anomalies[node_id] != REQUIRED_CONSECUTIVE:
            return None

        # 8. DEVOLVER UNA ALERTA SOLO EN LA SEGUNDA ANOMALÍA
        return {
            "type": "environmental_alert",
            "priority": "high",
            "node_id": node_id,
            "measurement": self.measurement_field,
            "unit": self.unit,
            "observed_value": value,
            "threshold_exceeded": round(threshold, 3),
            "z_score": round((value - mean_val) / std_val, 3),
            "reason": "two_consecutive_statistical_anomalies",
            "test_only": True,
        }


# 9. INTERFAZ PARA main.py: UN DETECTOR PERSISTENTE POR PROCESO
DETECTOR = ZScoreDetector(
    measurement_field=os.environ.get("EDGE_MEASUREMENT_FIELD", "sensible_heat_flux"),
    unit=os.environ.get("EDGE_MEASUREMENT_UNIT", "W/m2"),
)


def decide_reading(message: dict) -> dict | None:
    return DETECTOR.evaluate(message)


# 10. SOS INDEPENDIENTE DE ESTADÍSTICA E HISTORIAL

def decide_sos(message: dict) -> dict:
    return {
        "type": "sos_alert",
        "priority": "critical",
        "node_id": str(message.get("node_id", "unknown")),
        "zone": str(message.get("zone", "unknown")),
        "reason": "manual_sos",
        "test_only": True,
    }
