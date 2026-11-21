"""Validación del contrato v1 de la rama de integración ML del equipo."""

from datetime import datetime
from math import isfinite

MEASUREMENTS = (
    "pm25_ug_m3",
    "pm10_ug_m3",
    "air_temperature_c",
    "relative_humidity_pct",
)
BANNED_FIELDS = frozenset(
    {"ground_truth", "label", "fire_label", "affected_by_fire", "synthetic_event"}
)


def parse_reading(message):
    """Validate v1 telemetry; return (run_id, node_id, seq, time, measurements)."""
    if not isinstance(message, dict) or BANNED_FIELDS.intersection(message):
        raise ValueError("Invalid telemetry or evaluation label leaked into payload")
    if (
        type(message.get("schema_version")) is not int
        or message["schema_version"] != 1
        or message.get("type") != "reading"
    ):
        raise ValueError("Unsupported schema/type")
    run_id, node_id, seq = (
        message.get("run_id"),
        message.get("node_id"),
        message.get("seq"),
    )
    if any(not isinstance(x, str) or not 1 <= len(x) <= 128 for x in (run_id, node_id)):
        raise ValueError("Invalid run_id/node_id")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise ValueError("seq must be a nonnegative integer")
    if message.get("timebase") not in ("simulated", "wall"):
        raise ValueError("Missing/invalid timebase")
    if not isinstance(message.get("timestamp"), str):
        raise ValueError("timestamp is required")
    try:
        ts = datetime.fromisoformat(message["timestamp"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid ISO timestamp") from exc
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    raw = message.get("measurements")
    if not isinstance(raw, dict):
        raise ValueError("measurements object required")
    readings = []
    for name in MEASUREMENTS:
        x = raw.get(name)
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x):
            raise ValueError(f"Invalid measurement: {name}")
        readings.append(float(x))
    pm25, pm10, temp, humidity = readings
    if not (
        0 <= pm25 <= 100000
        and 0 <= pm10 <= 100000
        and -60 <= temp <= 100
        and 0 <= humidity <= 100
    ):
        raise ValueError("Measurement outside sanity limits")
    return run_id, node_id, seq, ts, tuple(readings)
