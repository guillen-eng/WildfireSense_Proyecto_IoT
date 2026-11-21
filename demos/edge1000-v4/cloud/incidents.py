"""Read-only aggregation: many suspected-fire events may be one simulated incident.

Events remain the source of truth in SQLite and are never altered by grouping.
This grouping is an explicit lab hypothesis, not a geographic wildfire tracker.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import math

# A chain of spatially adjacent, sufficiently close events is one incident.
# The time gate is between successive spatially adjacent event observations.
MAX_NEIGHBOUR_GAP_S = 30 * 60
GRID_WIDTH = 32


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def _grid_index(node):
    if not isinstance(node, str) or not node.startswith("node_"):
        return None
    digits = node[5:]
    if not digits.isascii() or not digits.isdigit():
        return None
    num = int(digits)
    if not 1 <= num <= 1024:
        return None
    return num - 1


def _close_nodes(node):
    index = _grid_index(node)
    if index is None:
        return (node,)
    x, y = index % GRID_WIDTH, index // GRID_WIDTH
    return tuple(
        f"node_{1 + yy * GRID_WIDTH + xx:04d}"
        for yy in range(max(0, y - 1), min(GRID_WIDTH, y + 2))
        for xx in range(max(0, x - 1), min(GRID_WIDTH, x + 2))
    )


def group_suspected_fire(events, gap_s=MAX_NEIGHBOUR_GAP_S):
    """Group events by run, 8-neighbour grid proximity and event time.

    Input dicts contain event_id, run_id, node_id, reading_timestamp,
    received_at, decision. Prealerts, SOS and health events are excluded.
    Missing run_id is isolated per event rather than merging unrelated legacy
    records. Group IDs are deterministic for a fixed event set but may change
    if older events arrive and previously separate groups merge.
    """
    if not isinstance(gap_s, (int, float)) or not math.isfinite(gap_s) or gap_s <= 0:
        raise ValueError("gap_s must be finite and positive")
    records = []
    for event in events:
        if event.get("decision") != "suspected_fire":
            continue
        event_id = str(event["event_id"])
        node = event.get("node_id")
        if not isinstance(node, str) or not node:
            continue
        run = event.get("run_id")
        if not isinstance(run, str) or not run:
            run = "legacy-" + event_id
        ts = (
            _timestamp(event.get("reading_timestamp"))
            or _timestamp(event.get("generated_at"))
            or _timestamp(event.get("received_at"))
        )
        if ts is None:
            continue
        records.append({**event, "event_id": event_id, "run_id": run, "_ts": ts})
    records.sort(key=lambda e: (e["run_id"], e["_ts"], e["event_id"]))
    n = len(records)
    parent = list(range(n))
    size = [1] * n

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        a, b = root(a), root(b)
        if a == b:
            return
        if size[a] < size[b]:
            a, b = b, a
        parent[b] = a
        size[a] += size[b]

    latest = {}  # (run_id, node_id) -> (event timestamp, row index)
    for i, item in enumerate(records):
        t, run, node = item["_ts"], item["run_id"], item["node_id"]
        for near in _close_nodes(node):
            previous = latest.get((run, near))
            if previous is not None and 0 <= t - previous[0] <= gap_s:
                union(i, previous[1])
        latest[(run, node)] = (t, i)

    components = defaultdict(list)
    for i, item in enumerate(records):
        components[root(i)].append(item)

    result = []
    for cluster in components.values():
        run = cluster[0]["run_id"]
        ids = sorted(e["event_id"] for e in cluster)
        incident_id = sha256(("wf-incident-v1/" + run + "/" + ids[0]).encode()).hexdigest()[:20]
        nodes = sorted({e["node_id"] for e in cluster})
        ordered = sorted(cluster, key=lambda e: (e["_ts"], e["event_id"]))
        scores = [
            e["fire_score"]
            for e in cluster
            if isinstance(e.get("fire_score"), (int, float))
            and not isinstance(e.get("fire_score"), bool)
            and math.isfinite(e["fire_score"])
        ]
        result.append(
            dict(
                incident_id=incident_id,
                run_id=run,
                first_seen=datetime.fromtimestamp(ordered[0]["_ts"], timezone.utc).isoformat(),
                last_seen=datetime.fromtimestamp(ordered[-1]["_ts"], timezone.utc).isoformat(),
                first_node=ordered[0]["node_id"],
                alert_count=len(cluster),
                node_count=len(nodes),
                nodes=nodes[:16],
                nodes_truncated=len(nodes) > 16,
                max_fire_score=round(max(scores), 4) if scores else None,
                test_only=all(e.get("test_only") is True for e in cluster),
            )
        )
    result.sort(key=lambda e: (e["last_seen"], e["incident_id"]), reverse=True)
    return result
