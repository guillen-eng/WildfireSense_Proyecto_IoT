"""Causal rolling features for WildfireSense MQTT v1; never uses labels/future samples."""
from collections import defaultdict, deque
from datetime import datetime
from math import isfinite
from statistics import mean

FEATURE_NAMES = (
    "pm25_now", "pm10_now", "temperature_now", "humidity_now",
    "pm25_mean", "pm10_mean", "temperature_mean", "humidity_mean",
    "pm25_delta", "pm10_delta", "temperature_delta", "humidity_delta",
    "pm25_slope_per_min", "pm10_slope_per_min",
    "temperature_slope_per_min", "humidity_slope_per_min",
    "pm25_pm10_ratio", "pm10_is_zero",
)
MEASUREMENTS = ("pm25_ug_m3", "pm10_ug_m3", "air_temperature_c", "relative_humidity_pct")
BANNED_FIELDS = frozenset({"ground_truth", "label", "fire_label", "affected_by_fire", "synthetic_event"})


def parse_reading(message):
    """Validate v1 telemetry; return (run_id, node_id, seq, time, measurements)."""
    if not isinstance(message, dict) or BANNED_FIELDS.intersection(message):
        raise ValueError("Invalid telemetry or evaluation label leaked into payload")
    if type(message.get("schema_version")) is not int or message["schema_version"] != 1 or message.get("type") != "reading":
        raise ValueError("Unsupported schema/type")
    run_id, node_id, seq = message.get("run_id"), message.get("node_id"), message.get("seq")
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
    if not (0 <= pm25 <= 100000 and 0 <= pm10 <= 100000 and -60 <= temp <= 100 and 0 <= humidity <= 100):
        raise ValueError("Measurement outside sanity limits")
    return run_id, node_id, seq, ts, tuple(readings)


class RollingFeatures:
    """Bounded history per (run_id, node_id), no labels, no future samples."""

    def __init__(self, window=6, min_samples=3):
        if not isinstance(window, int) or not isinstance(min_samples, int) or not 2 <= min_samples <= window:
            raise ValueError("Require 2 <= min_samples <= window")
        self.window = window
        self.min_samples = min_samples
        self._history = defaultdict(lambda: deque(maxlen=window))
        self.out_of_order_or_duplicate = 0
        self.sequence_gaps = 0

    def add(self, message):
        run_id, node_id, seq, ts, values = parse_reading(message)
        samples = self._history[(run_id, node_id)]
        if samples:
            last_seq, last_ts, _ = samples[-1]
            if seq <= last_seq or ts <= last_ts:
                self.out_of_order_or_duplicate += 1
                return None
            self.sequence_gaps += seq - last_seq - 1
        samples.append((seq, ts, values))
        if len(samples) < self.min_samples:
            return None
        first, previous, current = samples[0], samples[-2], samples[-1]
        minutes = (current[1] - first[1]).total_seconds() / 60
        if minutes <= 0:
            return None
        current_v, previous_v, first_v = current[2], previous[2], first[2]
        names = ("pm25", "pm10", "temperature", "humidity")
        features = {}
        for i, name in enumerate(names):
            features[f"{name}_now"] = current_v[i]
            features[f"{name}_mean"] = mean(sample[2][i] for sample in samples)
            features[f"{name}_delta"] = current_v[i] - previous_v[i]
            features[f"{name}_slope_per_min"] = (current_v[i] - first_v[i]) / minutes
        features["pm25_pm10_ratio"] = current_v[0] / current_v[1] if current_v[1] > 0 else 0.0
        features["pm10_is_zero"] = float(current_v[1] == 0)
        return {name: float(features[name]) for name in FEATURE_NAMES}
