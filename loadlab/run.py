"""Generate reproducible, labeled-as-a-separate-file synthetic IoT load.

By default OFFLINE ONLY. --publish explicitly opts into MQTT traffic.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from generator import MODES, affected_ids, make_reading, validate_config
from historical import ResistoReference, make_resisto_reading
from rules import ExperimentalFusion


def run_experiment(cfg: dict, nodes: int, mode: str, out_base: Path,
                   publisher=None, pace: bool = False, historical: ResistoReference | None = None) -> tuple[dict, Path]:
    validate_config(cfg, nodes, mode)
    truth_ids = set(affected_ids(cfg, nodes, mode))
    # Never publish ground truth through MQTT.
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = out_base / f"{run_id}_{mode}_{nodes}nodes"
    run_dir.mkdir(parents=True, exist_ok=False)
    rule = ExperimentalFusion(cfg["experimental_fusion"])
    detection = {}
    total_bytes = 0
    total = 0
    start = time.perf_counter()
    with (run_dir / "readings.jsonl").open("w", encoding="utf-8") as f:
        for step in range(int(cfg["steps"])):
            for i in range(1, nodes + 1):
                reading = (make_resisto_reading(cfg, i, step, mode, truth_ids, historical)
                           if historical is not None else make_reading(cfg, i, step, mode, truth_ids))
                payload = json.dumps(reading, separators=(",", ":"), ensure_ascii=False)
                f.write(payload + "\n")
                total_bytes += len(payload.encode("utf-8"))
                total += 1
                if publisher is not None:
                    publisher(f"wildfiresense/readings/{reading['node_id']}", payload)
                decision = rule.evaluate(reading)
                if decision and reading["node_id"] not in detection:
                    detection[reading["node_id"]] = {
                        "detected_at_step": step,
                        "indicators": decision["indicators"],
                    }
            if pace and float(cfg["real_step_seconds"]) > 0:
                time.sleep(float(cfg["real_step_seconds"]))
    elapsed = time.perf_counter() - start
    ev = cfg["event"]
    is_event = mode in {"smoke_proxy", "mixed_proxy", "heat_proxy"}
    # 'dust_control' is a deliberately negative case; labels are private.
    truth = {
        "synthetic_event": is_event,
        "affected_sensors": sorted(truth_ids),
        "event_start_step": int(ev["start_step"]) if is_event else None,
        "event_duration_steps": int(ev["duration_steps"]) if is_event else None,
        "note": "Etiqueta SOLO para evaluacion offline; no aparece en payload MQTT.",
    }
    if historical is not None:
        (run_dir / "historical_audit.json").write_text(
            json.dumps(historical.audit, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    cfg_copy = copy.deepcopy(cfg)
    cfg_copy["nodes"] = nodes
    cfg_copy["baseline"] = "resisto_temperature" if historical is not None else "fully_synthetic"
    if historical is not None:
        cfg_copy["historical_reference_sha256"] = historical.sha256
    cfg_copy["mode"] = mode
    (run_dir / "config_used.json").write_text(json.dumps(cfg_copy, indent=2), encoding="utf-8")
    detected_positive = sorted(truth_ids.intersection(detection))
    fp_nodes = sorted(set(detection) - truth_ids)
    if not is_event:
        fp_nodes = sorted(detection)
    summary = {
        "run_id": run_id,
        "mode": mode,
        "nodes": nodes,
        "baseline": "resisto_temperature" if historical is not None else "fully_synthetic",
        "historical_template_sensors": len(historical.ids) if historical is not None else 0,
        "additional_virtual_sensors_are_synthetic": historical is not None and nodes > len(historical.ids),
        "steps": int(cfg["steps"]),
        "generated_messages": total,
        "generated_payload_bytes": total_bytes,
        "mqtt_publish_attempted": publisher is not None,
        "publish_qos": 1 if publisher is not None else None,
        "mqtt_delivery_to_edge_verified": False,
        "wall_elapsed_seconds": round(elapsed, 3),
        "experimental_rule_detections": len(detection),
        "synthetic_event_sensors": len(truth_ids),
        "detected_event_sensors": len(detected_positive),
        "unexpected_detection_sensors": len(fp_nodes),
        "first_detections": detection,
        "notice": "Solo senales sinteticas y reglas experimentales; no detecta incendios reales.",
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary, run_dir


def main():
    parser = argparse.ArgumentParser(description="WildfireSense LoadLab (synthetic experimental) v1")
    parser.add_argument("--config", default="/app/config.json" if Path("/app/config.json").exists() else "config.json")
    parser.add_argument("--nodes", type=int, default=None)
    parser.add_argument("--mode", choices=sorted(MODES), default="mixed_proxy")
    parser.add_argument("--baseline", choices=("synthetic", "resisto"), default="synthetic",
                        help="Use RESISTO historical temperature as a template, other variables synthetic")
    parser.add_argument("--historical-csv", default=None,
                        help="Historical CSV path for --baseline resisto")
    parser.add_argument("--publish", action="store_true", help="Publica MQTT REAL (solo TEST); puede provocar alarmas oficiales")
    parser.add_argument("--no-pace", action="store_true", help="Solo offline; no aplicar pausa entre pasos")
    parser.add_argument("--results", default="/app/results" if Path("/app").exists() else "results")
    args = parser.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    nodes = args.nodes if args.nodes is not None else int(cfg["nodes"])
    validate_config(cfg, nodes, args.mode)
    historical = None
    if args.baseline == "resisto":
        default_csv = (Path("/app/historical-data/resisto_sample.csv") if Path("/app").exists()
                       else Path(__file__).resolve().parents[1] / "scenario/data/resisto_sample.csv")
        historical = ResistoReference(args.historical_csv or default_csv, int(cfg["steps"]))
        print("RESISTO: only temperature historically anchored; RH, PM2.5 and CO synthetic.")
        print("RESISTO: extra virtual nodes reuse five original temperature templates.")
    publisher = None
    client = None
    if args.publish:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.connect(os.getenv("MQTT_HOST", "mosquitto"), int(os.getenv("MQTT_PORT", "1883")), keepalive=60)
        client.loop_start()

        def publisher(topic, payload):
            info = client.publish(topic, payload, qos=1, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"Fallo MQTT publish: {info.rc}")
            info.wait_for_publish(timeout=10)
            if not info.is_published():
                raise RuntimeError("No se confirmo MQTT QoS1 publish")
    try:
        summary, path = run_experiment(
            cfg, nodes, args.mode, Path(args.results), publisher=publisher,
            pace=args.publish and not args.no_pace, historical=historical,
        )
    finally:
        if client is not None:
            client.disconnect()
            client.loop_stop()
    print(f"RESULTADOS: {path}")
    print("RESUMEN:", json.dumps(summary, ensure_ascii=False))
    if args.publish:
        print("AVISO: PUBACK confirma broker, NO que Edge proceso todas las lecturas.")
        print("AVISO: el Edge oficial actual SOLO usa temperatura, NO procesa PM2.5 ni CO.")
    else:
        print("MODO OFFLINE: sin publicaciones MQTT ni cambios al dashboard.")


if __name__ == "__main__":
    main()
