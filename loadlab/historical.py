"""RESISTO temperature-anchored generator. Other variables are synthetic hypotheses.

Not a physical model of combustion; do not interpret proxy labels as real fires.
"""
from __future__ import annotations
import csv
import hashlib
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from generator import _event_profile, make_reading
from timegrid import prepare_series


class ResistoReference:
    def __init__(self, csv_file: str | Path, steps: int, *, virtual_step_seconds: float = 120.0,
                 max_gap_seconds: float = 300.0, seed: int = 0):
        self.path = Path(csv_file)
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        sequences = defaultdict(list)
        with self.path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"virtual_sensor", "temperature_c", "humidity_percent", "source_time", "source_sensor"}
            missing = required - set(reader.fieldnames or ())
            if missing:
                raise ValueError(f"Missing RESISTO fields: {sorted(missing)}")
            for row in reader:
                try:
                    temp = float(row["temperature_c"])
                except (TypeError, ValueError) as exc:
                    raise ValueError("Missing or invalid historical temperature") from exc
                if not math.isfinite(temp) or not -40 <= temp <= 85:
                    raise ValueError("Historical temperature out of reasonable range")
                humidity = None
                try:
                    candidate = float(row["humidity_percent"])
                    if math.isfinite(candidate) and 0 <= candidate <= 100:
                        humidity = candidate
                except (TypeError, ValueError):
                    pass
                sensor = (row["virtual_sensor"] or "").strip()
                if not sensor:
                    raise ValueError("Empty virtual_sensor")
                sequences[sensor].append({
                    "temperature_c": temp, "humidity_observed": humidity,
                    "source_time": row["source_time"], "source_sensor": row["source_sensor"]
                })
        self.ids = sorted(sequences)
        if not self.ids or not isinstance(steps, int) or steps < 1:
            raise ValueError("No historical sensors or invalid steps")
        if any(len(sequences[key]) < steps for key in self.ids):
            raise ValueError("Insufficient historical readings per sensor")
        self.rows = {key: sequences[key][:steps] for key in self.ids}
        self.steps = steps
        self.series = {}
        temporal_audits = {}
        for index, key in enumerate(self.ids, start=1):
            grid, audit = prepare_series(
                self.rows[key], steps=steps, step_seconds=virtual_step_seconds,
                max_gap_seconds=max_gap_seconds, seed=seed + index * 10007)
            self.series[key] = grid
            temporal_audits[key] = audit
        temperatures = [row["temperature_c"] for rs in self.rows.values() for row in rs]
        humidity_count = sum(row["humidity_observed"] is not None
                             for rs in self.rows.values() for row in rs)
        self.audit = {
            "dataset_type": "historical_temperature_not_wildfire_ground_truth",
            "source_file": self.path.name, "sha256": self.sha256,
            "historical_sensors": len(self.ids),
            "observed_temperature_samples": len(temperatures),
            "observed_humidity_samples": humidity_count,
            "observed_humidity_missing_samples": len(temperatures) - humidity_count,
            "temperature_min_c": min(temperatures),
            "temperature_max_c": max(temperatures),
            "temperature_mean_c": round(statistics.mean(temperatures), 4),
            "historical_timestamps_aligned": False,
            "historical_data_uses_irregular_source_times": True,
            "virtual_temporal_grid_seconds": virtual_step_seconds,
            "max_source_interpolation_gap_seconds": max_gap_seconds,
            "temporal_preprocessing_by_sensor": temporal_audits,
            "temperature_point_origins": {
                origin: sum(a["point_origins"][origin] for a in temporal_audits.values())
                for origin in ("observed", "interpolated", "synthetic_extension")
            },
            "timegrid_notice": "Output timestamps are virtual; interpolation and synthetic extension are not direct observations.",
            "temperature_reference_used_in_generator": True,
            "humidity_reference_used_in_generator": False,
            "pm25_reference_used_in_generator": False,
            "co_reference_used_in_generator": False,
            "truth_notice": "No verified wildfire ground truth is provided."
        }

    def source_for(self, index: int, step: int):
        if index < 1 or not 0 <= step < self.steps:
            raise ValueError("Node index or step out of range")
        name = self.ids[(index - 1) % len(self.ids)]
        return self.series[name][step], name, index > len(self.ids)


def make_resisto_reading(cfg: dict, index: int, step: int, mode: str,
                         affected: set[str], reference: ResistoReference) -> dict:
    """Build a payload with explicit provenance but WITHOUT synthetic-event truth."""
    reading = make_reading(cfg, index, step, "normal", set())
    raw, trace, reused = reference.source_for(index, step)
    temperature = raw["temperature_c"]
    if reused:
        rng = random.Random(int(cfg["seed"]) * 65537 + index * 31337 + step * 137)
        temperature += (((index * 19) % 29) - 14) / 20.0 + rng.gauss(0, 0.16)
    temperature = round(temperature, 3)
    baseline = statistics.mean(x["temperature_c"] for x in
                               reference.series[trace][:min(20, reference.steps)])
    m = reading["measurements"]
    m["air_temperature_c"] = temperature
    # Hypothetical relationship, NOT fitted to historical humidity.
    m["relative_humidity_pct"] = round(max(0.0, min(100.0,
                                       m["relative_humidity_pct"] - 0.7 * (temperature - baseline))), 3)
    profile = _event_profile(step, cfg)
    event = cfg["event"]
    if reading["node_id"] in affected:
        if mode in {"heat_proxy", "mixed_proxy"}:
            m["air_temperature_c"] = round(temperature + profile * float(event["temperature_rise_c"]), 3)
            m["relative_humidity_pct"] = round(max(0.0, min(100.0,
                m["relative_humidity_pct"] - profile * float(event["humidity_drop_percentage_points"]))), 3)
        if mode in {"smoke_proxy", "mixed_proxy"}:
            m["pm25_ug_m3"] = round(m["pm25_ug_m3"] + profile * float(event["pm25_rise_ug_m3"]), 3)
            m["co_ppm"] = round(m["co_ppm"] + profile * float(event["co_rise_ppm"]), 4)
    if mode == "dust_control" and index % 7 == 0:
        m["pm25_ug_m3"] = round(m["pm25_ug_m3"] + profile * 110.0, 3)
    reading.update({
        "source": "resisto_timegrid_hybrid_synthetic_v2",
        "source_time": raw["reference_source_times"][0] if len(raw["reference_source_times"]) == 1 else None,
        "reference_source_times": raw["reference_source_times"],
        "reference_grid_time": raw["reference_grid_time"],
        "reference_temperature_origin": raw["temperature_origin"],
        "source_sensor": raw["source_sensor"],
        "reference_trace": trace,
        "historical_trace_reused": reused,
        "measurement_provenance": {
            "air_temperature_c": (
                ("historical_observed_or_interpolated_with_possible_synthetic_injection"
                 if raw["temperature_origin"] in ("observed", "interpolated")
                 else "synthetic_extension_from_historical_reference")
                if not reused else "synthetic_variant_of_" + raw["temperature_origin"]),
            "relative_humidity_pct": "synthetic_hypothesis_not_calibrated",
            "pm25_ug_m3": "synthetic_hypothesis_not_calibrated",
            "co_ppm": "synthetic_hypothesis_not_calibrated"
        }
    })
    return reading
