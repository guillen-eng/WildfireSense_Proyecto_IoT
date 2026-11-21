"""EXPERIMENTAL bounded event-time buffer for deterministic offline evaluation.

Not connected to the live gateway. A watermark makes delayed events sortable
only if their lateness stays within the configured window. Delaying readings
also delays alarms; SOS always bypasses the buffer.
"""

from datetime import datetime
import heapq
import math

from .logic import SOS


class BoundedEventBuffer:
    def __init__(self, lateness_s: float, max_pending: int = 50000):
        if not (isinstance(lateness_s, (int, float)) and math.isfinite(lateness_s)
                and 0 <= lateness_s <= 3600):
            raise ValueError("lateness_s must be finite and between 0 and 3600")
        if not isinstance(max_pending, int) or isinstance(max_pending, bool) or max_pending < 1:
            raise ValueError("max_pending must be positive")
        self.lateness_s = float(lateness_s)
        self.max_pending = max_pending
        self.heap = []
        self.index = 0
        self.max_event_time = -math.inf
        self.late = 0
        self.forced = 0
        self.peak_pending = 0
        self.sos_bypassed = 0

    @staticmethod
    def event_time(msg):
        try:
            stamp = datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("Timestamp must include timezone")
            value = stamp.timestamp()
        except (ValueError, TypeError, KeyError, OverflowError, AttributeError) as exc:
            raise ValueError("Unusable event timestamp") from exc
        if not math.isfinite(value):
            raise ValueError("Non-finite event timestamp")
        return value

    def push(self, arrival: float, topic: str, msg: dict):
        """Emit (available_at, topic, msg) tuples, in event-time order.

        Arrival and event timestamp must have compatible simulated seconds;
        this module only models message ordering and decision availability.
        """
        if topic == SOS:
            self.sos_bypassed += 1
            return [(arrival, topic, msg)]
        event_t = self.event_time(msg)
        previous_watermark = self.max_event_time - self.lateness_s
        if event_t < previous_watermark:
            self.late += 1
        self.max_event_time = max(self.max_event_time, event_t)
        self.index += 1
        heapq.heappush(self.heap, (event_t, self.index, topic, msg))
        ready = []
        watermark = self.max_event_time - self.lateness_s
        while self.heap and self.heap[0][0] <= watermark:
            _, _, topic, msg = heapq.heappop(self.heap)
            ready.append((arrival, topic, msg))
        while len(self.heap) > self.max_pending:
            self.forced += 1
            _, _, topic, msg = heapq.heappop(self.heap)
            ready.append((arrival, topic, msg))
        self.peak_pending = max(self.peak_pending, len(self.heap))
        return ready

    def finish(self, last_arrival: float):
        """Offline end-of-stream flush; real streaming would need idle timers."""
        ready_at = last_arrival + self.lateness_s
        result = []
        while self.heap:
            _, _, topic, msg = heapq.heappop(self.heap)
            result.append((ready_at, topic, msg))
        return result

    def metrics(self):
        return dict(reorder_window_s=self.lateness_s,
                    late_beyond_window=self.late,
                    buffer_overflows=self.forced,
                    max_buffered=self.peak_pending,
                    sos_bypassed=self.sos_bypassed)
