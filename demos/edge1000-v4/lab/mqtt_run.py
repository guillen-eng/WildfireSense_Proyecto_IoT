"""Timed MQTT replay with one or many independent Paho TCP clients, one thread."""

import argparse
import json
import os
import selectors
import time
import uuid
from pathlib import Path
import paho.mqtt.client as mqtt
from edge.logic import READINGS, SOS, adapt
from edge.transport import STATS, READY, wire
from .fleet import fleet


def _safe_modify(selector, sock, events, client):
    """Ignore late socket callbacks once the FD is no longer registered."""
    try:
        selector.modify(sock, events, client)
    except (KeyError, ValueError):
        # Unregistered socket or selector already closed during teardown.
        pass


class Pool:
    def __init__(self, host, port, count, run):
        self.selector = selectors.DefaultSelector()
        self.clients = []
        self.connected = set()
        self.status = None
        self.subscribed = False
        self.last_misc = time.monotonic()

        def on_readable(c, u, sock):
            self.selector.register(sock, selectors.EVENT_READ, c)

        def on_close(c, u, sock):
            try:
                self.selector.unregister(sock)
            except (KeyError, ValueError):
                pass

        def on_connect(c, u, flags, reason, properties):
            if reason.is_failure:
                raise RuntimeError(str(reason))
            self.connected.add(u)
            if u == 0:
                c.subscribe(STATS, 0)

        def on_msg(c, u, msg):
            self.status = json.loads(msg.payload)

        def on_sub(c, u, mid, qos, properties):
            self.subscribed = True

        for i in range(count):
            c = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2, client_id=f"wf-{run}-{i}", userdata=i
            )
            c.on_socket_open = on_readable
            c.on_socket_close = on_close
            c.on_connect = on_connect
            c.on_message = on_msg
            c.on_subscribe = on_sub
            # During shutdown, Paho can call these after on_socket_close.
            # A removed/closed selector key is normal and must not cause an error.
            c.on_socket_register_write = lambda c, u, s: _safe_modify(
                self.selector, s, selectors.EVENT_READ | selectors.EVENT_WRITE, c
            )
            c.on_socket_unregister_write = lambda c, u, s: _safe_modify(
                self.selector, s, selectors.EVENT_READ, c
            )
            c.connect(host, port, 60)
            self.clients.append(c)
            self.pump(0)
        self.wait(lambda: len(self.connected) == count and self.subscribed, 20)
        self.status = None
        self.clients[0].publish(READY, "{}")
        self.wait(lambda: self.status is not None, 10)

    def pump(self, timeout=0.02):
        for key, mask in self.selector.select(timeout):
            c = key.data
            if mask & selectors.EVENT_WRITE and c.loop_write() != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError("MQTT write failed")
            if mask & selectors.EVENT_READ and c.loop_read() != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError("MQTT connection lost")
        now = time.monotonic()
        if now - self.last_misc > 1:
            for c in self.clients:
                c.loop_misc()
            self.last_misc = now

    def wait(self, test, seconds):
        end = time.monotonic() + seconds
        while not test():
            if time.monotonic() > end:
                raise TimeoutError(
                    "MQTT timeout. Comprueba broker, Edge, límites de sockets y logs."
                )
            self.pump()

    def close(self):
        # Disconnect while callbacks and selector are still alive.
        # Disable callbacks before closing the selector: Paho's __del__ may
        # otherwise invoke a stale unregister-write callback on GC.
        try:
            for c in self.clients:
                try:
                    c.disconnect()
                finally:
                    c.on_socket_open = None
                    c.on_socket_close = None
                    c.on_socket_register_write = None
                    c.on_socket_unregister_write = None
        finally:
            self.selector.close()


def replay(path, run):
    t0 = None
    with path.open() as f:
        for line in f:
            raw = json.loads(line)
            if t0 is None:
                t0 = raw["ts"]
            yield (raw["ts"] - t0) / 1000, adapt(raw, run)


def run(args):
    run_id = uuid.uuid4().hex[:12]
    if not 1 <= args.clients <= 1024 or args.speed <= 0:
        raise ValueError("clients 1..1024 and speed > 0 required")
    pool = Pool(args.host, args.port, args.clients, run_id)
    try:
        start = pool.status.copy()
        node_clients = {}
        sent = sos = 0
        stream = (
            replay(args.file, run_id)
            if args.file
            else fleet(
                args.nodes, args.cycles, args.period, args.seed, args.scene, run_id
            )
        )
        at = time.monotonic()
        for sim_t, msg in stream:
            when = at + sim_t / args.speed
            while (rest := when - time.monotonic()) > 0:
                pool.pump(min(rest, 0.04))
            topic = SOS if msg["type"] == "sos" else READINGS + msg["node_id"]
            if msg["node_id"] not in node_clients:
                node_clients[msg["node_id"]] = len(node_clients) % len(pool.clients)
            c = pool.clients[node_clients[msg["node_id"]]]
            msg["sent_unix_ns"] = time.time_ns()
            rc = c.publish(topic, wire(msg), qos=int(topic == SOS)).rc
            if rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"PUBLISH rc={rc}")
            pool.pump(0)
            if topic == SOS:
                sos += 1
            else:
                sent += 1
        send_duration = time.monotonic() - at
        try:
            pool.wait(
                lambda: (
                    pool.status["readings"] - start["readings"] >= sent
                    and pool.status.get("sos_alert", 0) - start.get("sos_alert", 0)
                    >= sos
                ),
                12,
            )
        except TimeoutError:
            pass
        last = pool.status
        received = last["readings"] - start["readings"]
        result = dict(
            run_id=run_id,
            clients=len(pool.clients),
            nodes_requested=args.nodes if not args.file else None,
            publishing_clients=len(set(node_clients.values())),
            distinct_nodes_sent=len(node_clients),
            source=args.file.name if args.file else args.scene,
            period_s=args.period if not args.file else None,
            speed=args.speed,
            sent=sent,
            received=received,
            PDR=received / max(1, sent),
            sos_sent=sos,
            sos_received=last.get("sos_alert", 0) - start.get("sos_alert", 0),
            send_duration_s=round(send_duration, 3),
            offered_msg_s=round(sent / max(send_duration, 0.001), 2),
            stats_before=start,
            stats_after=last,
        )
        print(json.dumps(result, indent=2))
        if args.out:
            args.out.parent.mkdir(exist_ok=True, parents=True)
            args.out.write_text(json.dumps(result, indent=2))
        if received != sent or result["sos_received"] != sos:
            raise SystemExit(
                "Recepción incompleta o publicador externo activo; véase PDR."
            )
    finally:
        pool.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default=os.getenv("MQTT_HOST", "localhost"))
    p.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    p.add_argument("--clients", type=int, default=1)
    p.add_argument("--nodes", type=int, default=1000)
    p.add_argument("--cycles", type=int, default=48)
    p.add_argument("--period", type=float, default=10)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--speed", type=float, default=8)
    p.add_argument("--scene", choices=["normal", "fast_fire"], default="fast_fire")
    p.add_argument("--file", type=Path)
    p.add_argument("--out", type=Path)
    run(p.parse_args())
