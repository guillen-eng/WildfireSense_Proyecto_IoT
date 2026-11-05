"""RESISTO descriptive audit: original Zenodo CSV or reduced replay. No ML."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import timezone
from pathlib import Path
from timegrid import parse_source_time


def quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = fraction * (len(ordered) - 1)
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return round(ordered[low] + (index - low) * (ordered[high] - ordered[low]), 5)


def audit_csv(path: str | Path, max_gap_seconds: float = 300.0) -> dict:
    """Calculate reproducible temperature/availability/time-gap statistics."""
    if not math.isfinite(max_gap_seconds) or max_gap_seconds <= 0:
        raise ValueError("max_gap_seconds must be positive")
    path = Path(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    observations = defaultdict(list)
    labels = Counter()
    temperatures = []
    rows = valid_temperature = valid_humidity = bad_temperature = bad_time = 0
    bad_humidity = 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        original = {"time", "sensor_ns_id", "temperature_c", "humidity_percent"} <= fields
        reduced = {"source_time", "virtual_sensor", "temperature_c", "humidity_percent"} <= fields
        if not (original or reduced):
            raise ValueError("CSV is neither original RESISTO nor replay sample format")
        has_flags = "fire_alert_status" in fields
        for record in reader:
            rows += 1
            status = str(record.get("fire_alert_status", "")).strip() if has_flags else ""
            if has_flags:
                labels[status] += 1
            try:
                timestamp = parse_source_time(
                    record["time"] if original else record["source_time"]
                ).astimezone(timezone.utc)
            except (ValueError, TypeError):
                bad_time += 1
                continue
            try:
                temperature = float(record["temperature_c"])
            except (TypeError, ValueError):
                bad_temperature += 1
                continue
            if not math.isfinite(temperature) or not 0 <= temperature <= 55:
                bad_temperature += 1
                continue
            valid_temperature += 1
            temperatures.append(temperature)
            try:
                humidity = float(record["humidity_percent"])
            except (TypeError, ValueError):
                humidity = None
            if humidity is not None and math.isfinite(humidity) and 0 <= humidity <= 100:
                valid_humidity += 1
            else:
                bad_humidity += 1
            # Exclude source device alerts from reference normal-time windows,
            # but NEVER treat device status as verified fire ground truth.
            if has_flags and status != "0":
                continue
            key = (
                record.get("site_id", "") if original else "replay_csv",
                record["sensor_ns_id"] if original else record["virtual_sensor"],
            )
            observations[key].append((timestamp, temperature))
    gaps, rates, top = [], [], []
    positive_within = positive_over = repeated = segments = 0
    longest = 0.0
    for (site, sensor), points in observations.items():
        points.sort(key=lambda x: x[0])
        first = points[0][0]
        samples = 1
        for (earlier, t0), (later, t1) in zip(points, points[1:]):
            dt = (later - earlier).total_seconds()
            if dt <= 0 or dt > max_gap_seconds:
                if dt <= 0:
                    repeated += 1
                else:
                    positive_over += 1
                    gaps.append(dt)
                span = (earlier - first).total_seconds()
                top.append((span, site, sensor, samples))
                longest = max(longest, span)
                segments += 1
                first, samples = later, 1
            else:
                positive_within += 1
                gaps.append(dt)
                samples += 1
                # Near-zero time gaps exaggerate rates because T is quantized.
                if dt >= 30:
                    rates.append((t1 - t0) * 120.0 / dt)
        span = (points[-1][0] - first).total_seconds()
        top.append((span, site, sensor, samples))
        longest = max(longest, span)
        segments += 1
    top.sort(reverse=True)
    return {
        "dataset_file": path.name,
        "sha256": sha,
        "rows": rows,
        "source_schema": "original" if original else "replay",
        "unique_sensor_site_pairs": len(observations),
        "status_counts": dict(sorted(labels.items())) if has_flags else None,
        "device_status_note": (
            "fire_alert_status is a device flag, not verified wildfire ground truth"
            if has_flags else "source status absent in reduced replay"
        ),
        "valid_temperature_rows": valid_temperature,
        "rejected_temperature_rows": bad_temperature,
        "rejected_time_rows": bad_time,
        "valid_humidity_rows": valid_humidity,
        "missing_or_invalid_humidity_rows": bad_humidity,
        "humidity_fraction_of_valid_temp": (
            round(valid_humidity / valid_temperature, 5) if valid_temperature else None
        ),
        "temperature_statistics_c": {
            "min": min(temperatures, default=None),
            "median": quantile(temperatures, 0.5),
            "mean": round(statistics.mean(temperatures), 5) if temperatures else None,
            "max": max(temperatures, default=None),
            "p05": quantile(temperatures, 0.05),
            "p95": quantile(temperatures, 0.95),
        },
        "temporal": {
            "max_allowed_gap_seconds": max_gap_seconds,
            "source_gaps_positive": len(gaps),
            "duplicate_or_nonpositive_gaps": repeated,
            "source_gaps_within_limit": positive_within,
            "source_gaps_over_limit": positive_over,
            "source_gap_seconds_p50": quantile(gaps, 0.5),
            "source_gap_seconds_p95": quantile(gaps, 0.95),
            "longest_contiguous_span_seconds": longest,
            "longest_contiguous_span_minutes": round(longest / 60, 3),
            "contiguous_segments": segments,
            "largest_windows": [
                {"duration_minutes": round(seconds / 60, 3),
                 "site": site, "sensor": sensor, "observations": count}
                for seconds, site, sensor, count in top[:5]
            ],
            "two_minute_normalized_delta_c": {
                "samples_with_gap_30_to_limit_seconds": len(rates),
                "median": quantile(rates, 0.5),
                "p05": quantile(rates, 0.05),
                "p95": quantile(rates, 0.95),
                "absolute_p95": quantile([abs(x) for x in rates], 0.95),
                "zero_fraction": (
                    round(sum(x == 0 for x in rates) / len(rates), 5) if rates else None
                ),
                "warning": "Quantized readings; rate statistics do not validate wildfire dynamics",
            },
        },
        "interpretation": (
            "Descriptive environmental reference; no calibrated meteorology, "
            "PM2.5, CO or verified wildfire ground truth"
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="Offline descriptive RESISTO audit")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--max-gap-seconds", type=float, default=300.0)
    args = parser.parse_args()
    result = json.dumps(
        audit_csv(args.csv, args.max_gap_seconds), indent=2, ensure_ascii=False
    )
    if args.output:
        Path(args.output).write_text(result + "\n", encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
