"""Non-critical calculation offloaded when the measured link is healthy."""

from edge.transport import aggregate
import math


def summarize(data):
    mode = data["computed_by"]
    if mode == "cloud":
        samples = data["samples"]
        if (
            not isinstance(samples, list)
            or not 1 <= len(samples) <= 512
            or not all(type(x) in (float, int) and math.isfinite(x) for x in samples)
        ):
            raise ValueError("Invalid samples")
        result = aggregate(samples)
    elif mode == "edge":
        result = {k: data[k] for k in ("n", "mean_pm25", "max_pm25")}
        if (
            type(result["n"]) != int
            or not 1 <= result["n"] <= 512
            or not all(
                type(result[k]) in (float, int) and math.isfinite(result[k])
                for k in ("mean_pm25", "max_pm25")
            )
        ):
            raise ValueError("Invalid summary")
    else:
        raise ValueError("Invalid routing mode")
    return dict(
        **result,
        computed_by=mode,
        generated_at=data["generated_at"],
        event_id=data["event_id"],
    )
