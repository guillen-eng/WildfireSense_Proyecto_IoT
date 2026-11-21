"""1000 distinct cells, individual clocks/noise and spatial profiles of the team."""

import random
from data.scenarios import generador as g
from edge.contract import MEASUREMENTS
from edge.logic import checked_node, iso


def fleet(nodes=1000, cycles=48, period=10, seed=42, scene="fast_fire", run="demo"):
    if not 1 <= nodes <= 1024 or cycles < 1 or not 1 <= period <= 3600:
        raise ValueError("Grid supports 1..1024 active nodes; period must be 1..3600 s")
    # For small demos, start at the focus and include its closest neighbours.
    ids = (
        sorted(range(1, 1025), key=lambda n: (g.dist(n, g.N3), n))[:nodes]
        if nodes < 596
        else range(1, nodes + 1)
    )
    phases = []
    for n in ids:
        rng = random.Random(seed * 10000 + n)
        phases.append(
            (rng.uniform(0, period), n, rng, rng.gauss(0, 1.2), rng.gauss(0, 0.3))
        )
    phases.sort()
    t0 = g.S(14)
    info, fire = g.fire_model(20, 3, 500, 8.4, 0.8, t0, "fast")
    for k in range(cycles):
        for phase, n, rng, offset, bias in phases:
            elapsed = k * period + phase
            t = t0 - 50 + elapsed
            val = fire(n, t) if scene == "fast_fire" and n in info else {}
            if val.get("dead"):
                continue
            fine = g.meas_pm(rng, 8 + offset + val.get("pm25_exc", 0))
            coarse = max(fine, g.meas_pm(rng, 16 + offset * 2 + val.get("pm10_exc", 0)))
            values = (
                round(fine, 1),
                round(coarse, 1),
                round(g.Tdiurnal(t) + bias + val.get("dT", 0) + rng.gauss(0, 0.25), 2),
                round(min(100, max(0, g.RHdiurnal(t) + rng.gauss(0, 1))), 1),
            )
            m = dict(
                schema_version=1,
                run_id=run,
                node_id=checked_node(n),
                type="reading",
                seq=k + 1,
                boot_id=str(seed),
                period_s=period,
                timestamp=iso(g.BASE_MS / 1000 + t),
                timebase="simulated",
                measurements=dict(zip(MEASUREMENTS, values)),
                test_only=True,
            )
            yield elapsed, m
            if scene == "fast_fire" and k == 1 and n == g.N3:
                yield (
                    elapsed,
                    {
                        k: v
                        for k, v in {**m, "type": "sos"}.items()
                        if k != "measurements"
                    },
                )
