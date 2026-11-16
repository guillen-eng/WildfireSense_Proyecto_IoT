"""Convert teammate scenario JSONL into canonical OFFLINE telemetry and separate truth.

The teammate's tx is VIRTUAL; it is never misrepresented as emitted_at.
Default split='pending': a single seed is NOT an independent train/test split.
"""
import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

DAY_ZERO_MS = 1784073600000  # 2026-07-15 00:00 UTC in teammate generator
TRUTH_COLUMNS = ("run_id", "node_id", "seq", "label", "group_id", "split", "scenario", "exposure_state")


def _iter_sources(source):
    source = Path(source)
    if source.is_file() and source.suffix.lower() == ".zip":
        with ZipFile(source) as archive:
            names = archive.namelist()
            jsonls = sorted(name for name in names if name.endswith(".jsonl") and not name.startswith("__MACOSX/"))
            if not jsonls:
                raise ValueError("ZIP does not contain .jsonl files")
            for name in jsonls:
                truth_name = name[:-6] + "_verdad.json"
                if truth_name not in names:
                    raise ValueError(f"Missing truth file: {truth_name}")
                truth = json.loads(archive.read(truth_name))
                with archive.open(name) as stream:
                    yield Path(name).stem, stream, truth
    elif source.is_dir():
        files = sorted(source.rglob("*.jsonl"))
        if not files:
            raise ValueError("Directory does not contain .jsonl files")
        for filename in files:
            truth_path = filename.with_name(filename.stem + "_verdad.json")
            if not truth_path.is_file():
                raise ValueError(f"Missing truth file: {truth_path}")
            with filename.open("rb") as stream:
                yield filename.stem, stream, json.loads(truth_path.read_text(encoding="utf-8"))
    else:
        raise ValueError("Input must be a ZIP or an existing scenario folder")


def _labels(message, truth, day_time):
    """Synthetic modeled smoke-or-fire exposure; never a PM-threshold label."""
    if message["kind"] == "emergency":
        return None, "manual_sos"
    if not truth.get("alarma_esperada") or not truth.get("nodos_detalle"):
        return 0, "not_fire"
    node_truth = truth["nodos_detalle"].get(str(message["id"]))
    if not node_truth:
        raise ValueError(f"Fire truth missing node {message['id']}")
    fire_arrival = node_truth.get("llega_fuego_s")
    smoke_arrival = node_truth.get("humo_empieza_s")
    if fire_arrival is not None and day_time >= fire_arrival:
        return 1, "fire_front"
    if smoke_arrival is not None and day_time >= smoke_arrival:
        return 1, "modelled_smoke_exposure"
    return 0, "not_yet_exposed"


def _normalise(message, scenario, seed):
    if not isinstance(message, dict) or message.get("v") != 1:
        raise ValueError("Unsupported raw schema")
    if type(message.get("id")) is not int or not 1 <= message["id"] <= 1024:
        raise ValueError("Invalid raw node id")
    if type(message.get("seq")) is not int or message["seq"] < 1:
        raise ValueError("Invalid raw sequence")
    if message.get("kind") not in ("periodic", "emergency"):
        raise ValueError("Unknown raw kind")
    ts = message.get("ts")
    if type(ts) is not int or not DAY_ZERO_MS <= ts <= DAY_ZERO_MS + 2 * 86400000:
        raise ValueError("Invalid simulated timestamp")
    raw = message.get("values")
    if not isinstance(raw, dict):
        raise ValueError("Missing raw measurements")
    mapping = {
        "pm25_ug_m3": "PM2.5", "pm10_ug_m3": "PM10",
        "air_temperature_c": "temperature", "relative_humidity_pct": "humidity",
    }
    measurements = {}
    for dest, key in mapping.items():
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Bad measurement: {key}")
        measurements[dest] = float(value)
    if not (0 <= measurements["pm25_ug_m3"] <= measurements["pm10_ug_m3"]
            and 0 <= measurements["relative_humidity_pct"] <= 100):
        raise ValueError("Inconsistent measurement")
    timestamp = datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")
    return {
        "schema_version": 1, "run_id": f"team_scenarios_{scenario}_seed_{seed}",
        "node_id": f"node_{message['id']:04d}", "seq": message["seq"],
        "type": "reading", "timestamp": timestamp, "timebase": "simulated",
        "source": "teammate_scenario_generator_v1", "test_only": True,
        "measurements": measurements, "boot_id": message.get("boot_id"),
    }


def convert(input_path, output_dir, test_seeds=()):
    """Labels never enter readings.jsonl. No MQTT publish and no model fit."""
    output = Path(output_dir)
    test_seeds = {int(seed) for seed in test_seeds}
    available_seeds = set()
    for _, _stream, truth in _iter_sources(input_path):
        available_seeds.add(int(truth["seed"]))
    if test_seeds and (len(available_seeds) < 2 or not test_seeds < available_seeds):
        raise ValueError("Test seeds must be a proper subset of >=2 available seeds; do not split one seed")
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "synthetic_only": True, "dataset_source": Path(input_path).name,
        "available_seeds": sorted(available_seeds),
        "split_policy": "by generator seed across all scenarios",
        "scenarios": {}, "skipped_emergency_for_environmental_ml": 0, "excluded_sos_periodic": 0,
        "positive_label_definition": "modelled smoke arrival OR fire-front arrival at a node; never PM threshold",
        "note": "Very weak modeled smoke may not be measurable; no wildfire field ground truth.",
        "offline_only": True,
    }
    with (output / "readings.jsonl").open("w", encoding="utf-8") as out_read, (
            output / "truth.csv").open("w", newline="", encoding="utf-8") as out_truth:
        writer = csv.DictWriter(out_truth, fieldnames=TRUTH_COLUMNS)
        writer.writeheader()
        for name, stream, truth in _iter_sources(input_path):
            if truth.get("escenario") != name:
                raise ValueError(f"Filename/truth scenario mismatch: {name}")
            seed = int(truth["seed"])
            split = ("test" if seed in test_seeds else "train") if test_seeds else "pending"
            allowed = set(truth["nodos"])
            counts = Counter()
            last = {}
            for line in stream:
                if not line.strip():
                    continue
                raw = json.loads(line)
                if raw.get("id") not in allowed:
                    raise ValueError(f"Node missing from truth: {name}")
                if name == "sos_boton":
                    # SOS is a separate safety path. Excluding only emergency messages
                    # would create artificial gaps in the periodic stream.
                    if raw.get("kind") == "emergency":
                        report["skipped_emergency_for_environmental_ml"] += 1
                    else:
                        report["excluded_sos_periodic"] += 1
                    counts["excluded_from_environmental_ml"] += 1
                    continue
                reading = _normalise(raw, name, seed)
                ident, seq = reading["node_id"], raw["seq"]
                if ident in last and (seq <= last[ident][0] or raw["ts"] <= last[ident][1]):
                    raise ValueError(f"Out-of-order or repeated: {name}/{ident}")
                last[ident] = (seq, raw["ts"])
                day_time = (raw["ts"] - DAY_ZERO_MS) / 1000
                label, exposure = _labels(raw, truth, day_time)
                if label is None:
                    report["skipped_emergency_for_environmental_ml"] += 1
                    counts["excluded_emergency"] += 1
                    continue
                counts[f"label_{label}"] += 1
                counts[f"state_{exposure}"] += 1
                out_read.write(json.dumps(reading, ensure_ascii=False, separators=(",", ":")) + "\n")
                writer.writerow({
                    "run_id": reading["run_id"], "node_id": ident,
                    "seq": seq, "label": label, "group_id": f"generator_seed_{seed}",
                    "split": split, "scenario": name, "exposure_state": exposure,
                })
            report_key = f"{name}_seed_{seed}"
            if report_key in report["scenarios"]:
                raise ValueError(f"Duplicate scenario and seed: {report_key}")
            report["scenarios"][report_key] = {"seed": seed, "scenario": name, "split": split,
                                                "nodes": len(allowed), **counts}
    report["readings_rows"] = sum(s.get("label_0", 0) + s.get("label_1", 0)
                                  for s in report["scenarios"].values())
    report["label_1"] = sum(s.get("label_1", 0) for s in report["scenarios"].values())
    report["label_0"] = sum(s.get("label_0", 0) for s in report["scenarios"].values())
    (output / "import_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser(description="Import teammate scenario ZIP to offline ML data")
    p.add_argument("--input", required=True, help="ZIP or extracted scenario directory")
    p.add_argument("--output", required=True)
    p.add_argument("--test-seeds", default="", help="Comma-separated independent test seeds")
    args = p.parse_args()
    seeds = tuple(x.strip() for x in args.test_seeds.split(",") if x.strip())
    summary = convert(args.input, args.output, seeds)
    print(json.dumps({k: v for k, v in summary.items() if k != "scenarios"}, indent=2))


if __name__ == "__main__":
    main()
