"""EXPERIMENTAL baseline-relative fusion, independent of the production Edge.

This is a software demonstrator, NOT a calibrated detection criterion.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean


class ExperimentalFusion:
    def __init__(self, config: dict):
        self.config = config
        self.samples = int(config["baseline_samples"])
        self.consecutive_required = int(config["consecutive_samples"])
        self.indicators_required = int(config["minimum_indicators"])
        self.thresholds = config["thresholds"]
        self.history = defaultdict(list)
        self.consecutive = defaultdict(int)
        self.alarmed = set()

    def evaluate(self, reading: dict) -> dict | None:
        node = reading["node_id"]
        m = reading["measurements"]
        h = self.history[node]
        if len(h) < self.samples:
            h.append(m)
            return None
        baseline = {key: mean(row[key] for row in h) for key in (
            "air_temperature_c", "relative_humidity_pct", "pm25_ug_m3", "co_ppm"
        )}
        t = self.thresholds
        indicators = [
            name for name, ok in (
                ("temperature", m["air_temperature_c"] - baseline["air_temperature_c"] >= t["temperature_increase_c"]),
                ("humidity", baseline["relative_humidity_pct"] - m["relative_humidity_pct"] >= t["humidity_decrease_percentage_points"]),
                ("pm25", m["pm25_ug_m3"] - baseline["pm25_ug_m3"] >= t["pm25_increase_ug_m3"]),
                ("co", m["co_ppm"] - baseline["co_ppm"] >= t["co_increase_ppm"]),
            ) if ok
        ]
        if len(indicators) >= self.indicators_required:
            self.consecutive[node] += 1
        else:
            self.consecutive[node] = 0
        if node in self.alarmed or self.consecutive[node] != self.consecutive_required:
            return None
        self.alarmed.add(node)
        return {
            "node_id": node,
            "reading_timestamp": reading["timestamp"],
            "indicators": indicators,
            "type": "experimental_multivariate_detection",
            "test_only": True,
            "model_version": "fusion-rules-demo-v1",
        }
