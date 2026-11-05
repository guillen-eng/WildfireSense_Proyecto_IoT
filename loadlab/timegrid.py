"""Time-aware temperature templates from sparse, irregular historical observations.

A contiguous historical window is chosen per sensor. Only observations with real
source timestamps are used for interpolation; NO interpolation crosses a gap
larger than max_gap_seconds. The missing tail is a seeded, bounded SYNTHETIC
extension, not a historical observation or a validated physical model.
"""
from __future__ import annotations

import bisect
import math
import random
import statistics
from datetime import datetime, timedelta


def parse_source_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Empty historical source_time")
    try:
        result = datetime.fromisoformat(value.strip())
    except ValueError:
        try:
            result = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S.%f %z")
        except ValueError as exc:
            raise ValueError(f"Invalid historical timestamp: {value!r}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Historical timestamps must include a timezone offset")
    return result


def prepare_series(rows: list[dict], *, steps: int, step_seconds: float,
                   max_gap_seconds: float, seed: int) -> tuple[list[dict], dict]:
    """Return a uniform virtual-time grid and a machine-readable provenance audit.

    Historical values are only exact at source timestamps. Interpolated points
    have two provenance timestamps. Beyond the chosen contiguous window, values
    are transparent synthetic continuations. Calendar times are not aligned
    between sensors: the grid starts at each sensor's selected window start.
    """
    if not rows or steps < 1 or step_seconds <= 0 or max_gap_seconds <= 0:
        raise ValueError("Invalid temporal preparation settings")
    ordered = sorted(rows, key=lambda r: parse_source_time(r["source_time"]))
    times = [parse_source_time(r["source_time"]) for r in ordered]
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("Historical timestamps must be unique for each sensor")
    gaps = [(right - left).total_seconds() for left, right in zip(times, times[1:])]
    bounds = []
    start = 0
    for i, gap in enumerate(gaps, start=1):
        if gap > max_gap_seconds:
            bounds.append((start, i))
            start = i
    bounds.append((start, len(ordered)))
    # Most coverage by elapsed time, tie-break by number of observed samples.
    a, b = max(bounds, key=lambda ab: ((times[ab[1]-1] - times[ab[0]]).total_seconds(), ab[1]-ab[0]))
    selected = ordered[a:b]
    selected_times = times[a:b]
    temps = [float(row["temperature_c"]) for row in selected]
    t0 = selected_times[0]
    endpoint = selected_times[-1]
    median = statistics.median(temps)
    rng = random.Random(seed)
    prepared = []
    previous = None
    counts = {"observed": 0, "interpolated": 0, "synthetic_extension": 0}
    for step in range(steps):
        grid_time = t0 + timedelta(seconds=step * step_seconds)
        j = bisect.bisect_left(selected_times, grid_time)
        if j < len(selected_times) and selected_times[j] == grid_time:
            value = temps[j]
            kind = "observed"
            source_times = [selected[j]["source_time"]]
        elif 0 < j < len(selected_times):
            # Guaranteed no large source gaps inside selected contiguous window.
            left, right = selected_times[j - 1], selected_times[j]
            gap = (right - left).total_seconds()
            if gap > max_gap_seconds:
                raise AssertionError("Interpolation would bridge a historical outage")
            weight = (grid_time - left).total_seconds() / gap
            value = temps[j - 1] + weight * (temps[j] - temps[j - 1])
            kind = "interpolated"
            source_times = [selected[j-1]["source_time"], selected[j]["source_time"]]
        else:
            # Constrained stochastic extension. No later isolated samples are
            # reattached, because that would introduce fictitious fast jumps.
            assert grid_time > endpoint
            if previous is None:
                previous = temps[-1]
            drift = max(-0.20, min(0.20, 0.06 * (median - previous)))
            increment = max(-0.65, min(0.65, drift + rng.gauss(0, 0.13)))
            value = previous + increment
            kind = "synthetic_extension"
            source_times = []
        if not math.isfinite(value):
            raise ValueError("Non-finite temperature on virtual grid")
        counts[kind] += 1
        previous = value
        prepared.append({
            "temperature_c": round(value, 3),
            "temperature_origin": kind,
            "reference_source_times": source_times,
            "reference_grid_time": grid_time.isoformat(),
            "source_sensor": selected[0]["source_sensor"],
        })
    audit = {
        "selected_window_start": t0.isoformat(),
        "selected_window_end": endpoint.isoformat(),
        "selected_window_observations": len(selected),
        "selected_window_duration_seconds": round((endpoint - t0).total_seconds(), 3),
        "original_source_gap_count_over_max": sum(g > max_gap_seconds for g in gaps),
        "original_source_max_gap_seconds": max(gaps, default=0.0),
        "virtual_step_seconds": step_seconds,
        "max_interpolation_gap_seconds": max_gap_seconds,
        "point_origins": counts,
        "selected_window_policy": "longest_elapsed_contiguous_window_no_cross_gap_interpolation",
        "synthetic_extension_policy": "bounded_seeded_stochastic_drift_not_physical_model",
    }
    return prepared, audit
