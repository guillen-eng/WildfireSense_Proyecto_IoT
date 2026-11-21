"""Measure MQTT frames emitted by the project's client, on a dedicated local link.

An instrumented TCP relay counts bytes in each direction. This protocol-level
measurement excludes TCP/IP and Ethernet headers, TLS, retransmits and RF.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import paho.mqtt.client as mqtt
from edge.logic import READINGS, SOS
from edge.model import ROOT
from edge.transport import wire
from .fleet import fleet


def frames(stream):
    i = 0
    result = Counter()
    while i < len(stream):
        start = i
        first = stream[i]
        i += 1
        size = 0
        factor = 1
        while True:
            digit = stream[i]
            i += 1
            size += (digit & 127) * factor
            if digit < 128:
                break
            factor *= 128
        end = i + size
        if end > len(stream):
            raise ValueError("Incomplete MQTT frame")
        packet = first >> 4
        result[f"type_{packet}_bytes"] += end - start
        result[f"type_{packet}_count"] += 1
        if packet == 3:
            topic_len = int.from_bytes(stream[i : i + 2], "big")
            qos = (first >> 1) & 3
            payload = size - 2 - topic_len - (2 if qos else 0)
            result["publish_payload_bytes"] += payload
            result["publish_overhead_bytes"] += end - start - payload
        i = end
    return dict(result)


def measure(broker):
    with tempfile.TemporaryDirectory() as tmp, socket.socket() as relay:
        relay.bind(("127.0.0.1", 0))
        relay.listen()
        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            port = reserve.getsockname()[1]
        cfg = Path(tmp) / "broker.conf"
        cfg.write_text(
            f"listener {port} 127.0.0.1\nallow_anonymous true\nlog_type warning\n"
        )
        p = subprocess.Popen([broker, "-c", str(cfg)], stdout=subprocess.DEVNULL)
        capture = {}

        def copy(src, dest, label):
            data = bytearray()
            while chunk := src.recv(32768):
                data.extend(chunk)
                dest.sendall(chunk)
            dest.shutdown(socket.SHUT_WR)
            capture[label] = bytes(data)

        def proxy():
            with (
                relay.accept()[0] as front,
                socket.create_connection(("127.0.0.1", port)) as back,
            ):
                th = threading.Thread(
                    target=copy, args=(back, front, "broker_to_publisher")
                )
                th.start()
                copy(front, back, "publisher_to_broker")
                th.join()

        try:
            for attempt in range(40):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.05)
            thread = threading.Thread(target=proxy, daemon=True)
            thread.start()
            c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="wf-overhead")
            c.connect("127.0.0.1", relay.getsockname()[1])
            c.loop_start()
            sizes = Counter()
            for _, m in fleet(5, 5, run="wire-test"):
                topic = SOS if m["type"] == "sos" else READINGS + m["node_id"]
                m["sent_unix_ns"] = time.time_ns()
                body = wire(m)
                sizes["expected_payload_bytes"] += len(body.encode())
                r = c.publish(topic, body, qos=int(topic == SOS))
                r.wait_for_publish(4)
                if not r.is_published():
                    raise TimeoutError("PUBLISH timeout")
            c.disconnect()
            c.loop_stop()
            thread.join(timeout=8)
            result = {
                k: dict(tcp_stream_bytes=len(v), **frames(v))
                for k, v in capture.items()
            }
            assert (
                result["publisher_to_broker"]["publish_payload_bytes"]
                == sizes["expected_payload_bytes"]
            )
            assert (
                result["publisher_to_broker"]["type_3_count"] == 26
                and result["broker_to_publisher"]["type_4_count"] == 1
            )
            return result
        finally:
            p.terminate()
            p.wait()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", default="mosquitto")
    ap.add_argument("--out", type=Path, default=ROOT / "resultados/tramas_mqtt.json")
    a = ap.parse_args()
    r = measure(a.broker)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(r, indent=2))
    print(json.dumps(r, indent=2))
