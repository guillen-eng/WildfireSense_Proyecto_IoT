"""Causal filters in seconds. Same code for learning, file replay and MQTT."""

from math import expm1

NAMES = (
    "pm25_fast",
    "pm10_fast",
    "fine_fraction",
    "pm25_change",
    "temperature_change",
    "humidity_fast",
    "humidity_change",
    "pm25_slow",
)


class Filters:
    def __init__(self):
        self.time = None
        self.fast = self.slow = None

    def update(self, t, values):
        if self.time is None:
            self.fast = self.slow = tuple(values)
        else:
            dt = t - self.time
            if dt <= 0:
                raise ValueError("non-increasing sample time")

            def smooth(old, tau):
                alpha = -expm1(-dt / tau)
                return tuple(a + alpha * (b - a) for a, b in zip(old, values))

            self.fast = smooth(self.fast, 30)
            self.slow = smooth(self.slow, 300)
        self.time = t
        a, b = self.fast, self.slow
        return (
            a[0],
            a[1],
            a[0] / max(0.1, a[1]),
            a[0] - b[0],
            a[2] - b[2],
            a[3],
            a[3] - b[3],
            b[0],
        )
