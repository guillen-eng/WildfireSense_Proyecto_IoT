import argparse
from collections import Counter
import json
import time
from edge.logic import Engine, READINGS, SOS
from .fleet import fleet


def run(nodes=1000, cycles=48):
    e = Engine()
    count = Counter()
    first = {}
    start = time.perf_counter()
    for t, m in fleet(nodes, cycles):
        _, events = e.handle(SOS if m["type"] == "sos" else READINGS + m["node_id"], m)
        for ev in events:
            d = ev["decision"]
            count[d] += 1
            if d not in first:
                first[d] = dict(
                    segundo_de_demo=round(t, 2),
                    sensor=ev["node_id"],
                    vecino=ev.get("neighbour"),
                )
    if e.accepted < 1 or len(e.nodes) != nodes:
        raise RuntimeError("Incomplete simulation")
    return dict(
        nodos=len(e.nodes),
        lecturas=e.accepted,
        segundos_en_este_equipo=round(time.perf_counter() - start, 3),
        modelo=e.forest.version,
        eventos=count,
        primero=first,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, default=1000)
    ap.add_argument("--cycles", type=int, default=48)
    args = ap.parse_args()
    print(json.dumps(run(args.nodes, args.cycles), indent=2, ensure_ascii=False))
