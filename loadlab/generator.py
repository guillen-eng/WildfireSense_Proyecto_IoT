"""Deterministic MULTIVARIATE SYNTHETIC signals for functional/scale tests.

Not a calibrated wildfire, smoke dispersion or physical sensor model.
Ground truth is intentionally separate from the MQTT message.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

MODES = {"normal", "smoke_proxy", "mixed_proxy", "heat_proxy", "dust_control"}


def validate_config(cfg: dict, nodes: int, mode: str) -> None:
    if mode not in MODES:
        raise ValueError(f"Modo desconocido: {mode}; modos: {sorted(MODES)}")
    if not isinstance(nodes, int) or isinstance(nodes, bool) or not 1 <= nodes <= 1000:
        raise ValueError("nodes debe ser un entero entre 1 y 1000")
    if int(cfg["schema_version"]) != 1:
        raise ValueError("schema_version no soportada")
    steps = int(cfg["steps"])
    event = cfg["event"]
    if not 25 <= steps <= 10000:
        raise ValueError("steps debe estar entre 25 y 10000")
    if not 0 <= int(event["start_step"]) < steps:
        raise ValueError("event.start_step fuera de rango")
    if not 1 <= int(event["ramp_steps"]) <= int(event["duration_steps"]):
        raise ValueError("ramp_steps invalido")
    if float(cfg["real_step_seconds"]) < 0:
        raise ValueError("real_step_seconds no puede ser negativo")
    if float(cfg["virtual_step_seconds"]) <= 0:
        raise ValueError("virtual_step_seconds debe ser positivo")
    if not 0 < float(event["affected_fraction"]) <= 1:
        raise ValueError("affected_fraction fuera de rango")
    if not 1 <= int(event["minimum_affected"]) <= nodes:
        raise ValueError("minimum_affected no puede superar numero de nodos")
    rule = cfg["experimental_fusion"]
    if not 2 <= int(rule["baseline_samples"]) < int(event["start_step"]):
        raise ValueError("baseline_samples debe ser menor al inicio del evento")
    if not 1 <= int(rule["minimum_indicators"]) <= 4:
        raise ValueError("minimum_indicators debe estar entre 1 y 4")
    if not 1 <= int(rule["consecutive_samples"]) <= 20:
        raise ValueError("consecutive_samples invalido")
    for name, value in rule["thresholds"].items():
        if not math.isfinite(float(value)) or float(value) <= 0:
            raise ValueError(f"Umbral no valido: {name}")


def affected_ids(cfg: dict, nodes: int, mode: str) -> list[str]:
    if mode in {"normal", "dust_control"}:
        return []
    event = cfg["event"]
    n = min(nodes, max(int(event["minimum_affected"]), round(nodes * float(event["affected_fraction"]))))
    # Sparse deterministic selection across the node array; no geographic assertion.
    picked = random.Random(int(cfg["seed"]) + 101).sample(range(1, nodes + 1), n)
    return [f"scale_{k:04d}" for k in sorted(picked)]


def _event_profile(step: int, cfg: dict) -> float:
    ev = cfg["event"]
    offset = step - int(ev["start_step"])
    if offset < 0 or offset >= int(ev["duration_steps"]):
        return 0.0
    return min(1.0, (offset + 1) / int(ev["ramp_steps"]))


def make_reading(cfg: dict, index: int, step: int, mode: str, affected: set[str]) -> dict:
    """Returns a payload with no synthetic-event label, for MQTT or a JSONL file."""
    node_id = f"scale_{index:04d}"
    seed = int(cfg["seed"])
    # The per-node/step RNG means results don't depend on traversal order.
    rng = random.Random(seed * 104729 + index * 10007 + step * 103)
    phase = 2 * math.pi * step / 96
    bias = ((index * 17) % 23 - 11) / 10
    temp = 22.0 + bias + 1.4 * math.sin(phase) + rng.gauss(0, .22)
    humidity = 56.0 - 1.5 * bias - 2.5 * math.sin(phase) + rng.gauss(0, .65)
    pm25 = max(0, 8.0 + .4 * bias + rng.gauss(0, .8))
    co = max(.01, .3 + .01 * bias + rng.gauss(0, .035))
    p = _event_profile(step, cfg)
    if node_id in affected:
        ev = cfg["event"]
        if mode in {"mixed_proxy", "heat_proxy"}:
            temp += p * float(ev["temperature_rise_c"])
            humidity -= p * float(ev["humidity_drop_percentage_points"])
        if mode in {"mixed_proxy", "smoke_proxy"}:
            pm25 += p * float(ev["pm25_rise_ug_m3"])
            co += p * float(ev["co_rise_ppm"])
    if mode == "dust_control" and index % 7 == 0:
        # Background particulate-only excursion, NO synthetic fire label.
        pm25 += p * 110.0
    vtime = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        seconds=step * float(cfg["virtual_step_seconds"])
    )
    return {
        "node_id": node_id,
        "type": "reading",
        "timestamp": vtime.isoformat(),
        "source": "wildfiresense_loadlab_synthetic_v1",
        "test_only": True,
        "measurements": {
            "air_temperature_c": round(temp, 3),
            "relative_humidity_pct": round(min(100, max(0, humidity)), 3),
            "pm25_ug_m3": round(pm25, 3),
            "co_ppm": round(co, 4),
        },
    }
