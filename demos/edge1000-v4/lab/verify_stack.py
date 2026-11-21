"""Launch isolated native processes, run TCP/IP tests and stop only these children."""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, ProxyHandler
from edge.model import ROOT

http = build_opener(ProxyHandler({}))


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait(fn, timeout=20):
    limit = time.monotonic() + timeout
    while time.monotonic() < limit:
        try:
            if fn():
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise TimeoutError("Timeout esperando a los servicios")


def main(args):
    args.out.mkdir(exist_ok=True, parents=True)
    mqtt_port, http_port = port(), port()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        conf = tmp / "mosquitto.conf"
        conf.write_text(
            f"listener {mqtt_port} 127.0.0.1\nallow_anonymous true\nlog_type warning\n"
        )
        env = dict(
            os.environ,
            MQTT_HOST="127.0.0.1",
            MQTT_PORT=str(mqtt_port),
            EDGE_DB=str(tmp / "edge.sqlite"),
            CLOUD_DB_PATH=str(tmp / "cloud.sqlite"),
            HTTP_PORT=str(http_port),
            PYTHONUNBUFFERED="1",
        )
        procs = []

        def start(cmd):
            p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL)
            procs.append(p)
            return p

        def get(path):
            with http.open(f"http://127.0.0.1:{http_port}/api/{path}", timeout=2) as r:
                return json.load(r)

        def cloud():
            p = start([sys.executable, "-m", "cloud.app"])
            wait(lambda: get("health")["mqtt_connected"])
            return p

        def replay(name, *flags):
            out = args.out / (name + ".json")
            with (tmp / (name + ".log")).open("w") as stream:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "lab.mqtt_run",
                        "--out",
                        str(out.resolve()),
                        *flags,
                    ],
                    cwd=ROOT,
                    env=env,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=240,
                )
            if result.returncode:
                raise RuntimeError((tmp / (name + ".log")).read_text()[-4000:])
            return json.loads(out.read_text())

        try:
            start([args.broker, "-c", str(conf)])

            def tcp_ready():
                with socket.create_connection(("127.0.0.1", mqtt_port), timeout=0.5):
                    return True

            wait(tcp_ready)
            start([sys.executable, "-m", "edge.main"])
            c = cloud()
            time.sleep(2.5)
            r = replay(
                "mqtt_1000",
                "--clients",
                "1000",
                "--nodes",
                "1000",
                "--cycles",
                "6",
                "--period",
                "10",
                "--speed",
                "1",
                "--scene",
                "normal",
            )
            if r["stats_after"]["nodes"] != 1000 or r["received"] != 6000:
                raise AssertionError("La flota no llegó completa")
            wait(lambda: get("stats")["last_summary"] is not None)
            wait(lambda: (get("stats").get("edge") or {}).get("readings") == 6000)
            online = get("stats")
            c.terminate()
            c.wait(8)
            time.sleep(7)
            offline = replay(
                "mqtt_sin_cloud",
                "--clients",
                "1000",
                "--nodes",
                "1000",
                "--cycles",
                "48",
                "--period",
                "10",
                "--speed",
                "12",
            )
            before = offline["stats_before"]
            after = offline["stats_after"]
            assert after["sos_alert"] > before.get("sos_alert", 0) and after[
                "suspected_fire"
            ] > before.get("suspected_fire", 0)
            assert (
                not after["cloud_available"]
                and after["backlog"] > 0
                and after["windows_edge"] > before.get("windows_edge", 0)
            )
            cloud()
            import sqlite3

            def drained():
                with sqlite3.connect(tmp / "edge.sqlite") as db:
                    return (
                        db.execute(
                            "select count(*) from events where confirmed=0"
                        ).fetchone()[0]
                        == 0
                    )

            wait(drained)
            final = get("stats")
            assert final["sos_alerts"] >= 1 and final["last_summary"] is not None
            with (
                sqlite3.connect(tmp / "edge.sqlite") as local,
                sqlite3.connect(tmp / "cloud.sqlite") as central,
            ):
                expected = {
                    r[0]
                    for r in local.execute(
                        "select id from events where topic='wildfiresense/edge/alerts'"
                    )
                }
                actual = {
                    r[0] for r in central.execute("select event_hash from alerts")
                }
                assert expected == actual
                sos_record = json.loads(
                    central.execute(
                        "SELECT payload_json FROM alerts WHERE alert_type='sos_alert' LIMIT 1"
                    ).fetchone()[0]
                )
                assert sos_record["rx_ts"] and sos_record["sender_to_rx_ms"] >= 0
                windows = dict(
                    central.execute(
                        "select json_extract(payload,'$.computed_by'),count(*) from summaries group by 1"
                    )
                )
                assert set(windows) == {"cloud", "edge"}
            result = dict(
                online_summary=online["last_summary"],
                during_outage_backlog=after["backlog"],
                sos_sender_to_rx_ms=sos_record["sender_to_rx_ms"],
                sos_edge_decision_ms=sos_record["edge_processing_ms"],
                local_alarms=len(expected),
                synchronized_unique_alerts=len(actual),
                pending_after_recovery=0,
                windows_by_compute_location=windows,
                cloud_http_after_restart=final,
            )
            (args.out / "recuperacion.json").write_text(json.dumps(result, indent=2))
            print("OK: 1000 conexiones, detección autónoma, reenvío y persistencia.")
        finally:
            for p in reversed(procs):
                if p.poll() is None:
                    p.terminate()
                    p.wait(10)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--broker", default=shutil.which("mosquitto") or "mosquitto")
    p.add_argument("--out", type=Path, default=ROOT / "resultados")
    main(p.parse_args())
