"""Perturb the team's physical profiles; truth available only to offline scorer."""

import math
import random
from data.scenarios import generador as g

SCENES = ("normal", "slow_fire", "fast_fire", "dust", "fog", "direct_sun")
BASE = g.BASE_MS / 1000
PERIOD = 10
ORIGIN = 496


def make_scene(seed, scene):
    """Return a source-time ordered iterator, real node ids, ignition offset."""
    rng = random.Random(seed * 97 + SCENES.index(scene))
    # Equal sampling and randomized start phase for every class.
    phase = rng.uniform(-6, 6) * 3600
    focus = g.nid(rng.randrange(3, 28), rng.randrange(3, 28))
    cells = [(0, 0), (1, 0), (0, 1), (-1, 0), (1, 1)]
    if rng.randrange(2):
        cells = [(y, x) for x, y in cells]
    rotation = rng.randrange(4)

    def remap(x, y):
        for _ in range(rotation):
            x, y = -y, x
        return focus + x + 32 * y

    nodes = [remap(dx, dy) for dx, dy in cells]
    t0 = g.S(14)
    scale = rng.uniform(0.7, 1.35)
    dust_ratio, fog_delta = rng.uniform(0.16, 0.34), rng.uniform(8, 17)
    sun_gain, sun_rise = rng.uniform(2.8, 6.5), rng.uniform(1000, 2400)
    bg_pm, t_bias, rh_bias = (
        rng.uniform(5, 13),
        rng.uniform(-4, 4),
        rng.uniform(-10, 10),
    )
    if scene in ("fast_fire", "slow_fire"):
        fast = scene == "fast_fire"
        kind = "fast" if fast else "slow"
        info, signal = g.fire_model(
            (20 if fast else 1) * scale,
            rng.uniform(0.8, 1.3) * (3 if fast else 1),
            (500 if fast else 150) * rng.uniform(0.65, 1.4),
            (8.4 if fast else 98.5) * rng.uniform(0.75, 1.3),
            rng.uniform(0.67, 0.87) if fast else rng.uniform(0.50, 0.72),
            t0,
            kind,
        )
    duration = 5400 if scene != "fast_fire" else 2100
    node_rng = [random.Random(rng.getrandbits(40)) for _ in cells]
    offsets = [r.uniform(0, PERIOD) for r in node_rng]
    order = sorted(range(len(nodes)), key=offsets.__getitem__)

    def stream():
        for sec in range(-1200, duration, PERIOD):
            for j in order:
                dx, dy = cells[j]
                i = ORIGIN + dx + dy * 32
                t = sec + offsets[j]
                clock = t0 + t
                rh = g.RHdiurnal(clock + phase) + rh_bias
                temp = g.Tdiurnal(clock + phase) + t_bias
                background = bg_pm + 1.5 * math.sin((clock + phase) / 4000) + 0.35 * j
                f, coarse, dtemp = 0.0, 0.0, 0.0
                label = "normal"
                if scene.endswith("_fire"):
                    val = signal(i, clock)
                    if val.get("dead"):
                        continue
                    f, coarse, dtemp = (
                        val.get(k, 0.0) for k in ("pm25_exc", "pm10_exc", "dT")
                    )
                    if clock >= min(info[i]["ts"], info[i]["tf"]):
                        label = scene
                elif scene == "dust":
                    local = t - math.hypot(dx, dy) * g.PITCH / 3
                    if 0 <= local < 300:
                        coarse = (
                            400
                            * scale
                            * math.exp(-math.hypot(dx, dy) * g.PITCH / 100)
                            * min(1, local / 30, (300 - local) / 90)
                        )
                        f, label = dust_ratio * coarse, scene
                elif scene == "fog" and t >= 0:
                    level = min(1, t / 1400, max(0, (duration - t) / 600))
                    f, coarse, dtemp = (
                        fog_delta * level,
                        fog_delta * 1.45 * level,
                        -2 * level,
                    )
                    rh += (95 - rh) * level
                    label = scene
                elif scene == "direct_sun" and t >= 0:
                    dtemp, label = (
                        sun_gain * min(1, t / sun_rise) * (1 + 0.08 * j),
                        scene,
                    )
                r = node_rng[j]
                pm = g.meas_pm(r, background + f)
                values = (
                    round(pm, 1),
                    round(max(pm, g.meas_pm(r, 2 * background + coarse)), 1),
                    round(temp + dtemp + r.gauss(0, 0.25), 2),
                    round(min(100, max(0, rh + r.gauss(0, 1))), 1),
                )
                yield nodes[j], BASE + clock, values, label

    return stream(), nodes, BASE + t0
