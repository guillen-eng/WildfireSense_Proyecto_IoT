"""Create *SYNTHETIC* labelled JSONL to demonstrate the Cloud AI lifecycle.

Every label comes directly from the simulator ground truth. These records are
NOT independently human-reviewed field observations, despite the training
schema requiring a reviewed-train-* group. Never pass this file off as real.
Seed 125 is outside the original training, validation and test seed ranges.
"""

import argparse
from collections import defaultdict
import json
from pathlib import Path

from edge.logic import checked_node, iso
from .episodes import SCENES, make_scene


def generate(path: Path, seed: int = 125, scenes=("fast_fire", "slow_fire", "dust")):
    if seed in range(101, 125) or seed in range(201, 231) or seed in range(301, 307):
        raise ValueError("Demonstration seed must stay outside the train/test/validation sets")
    if not scenes or any(scene not in SCENES for scene in scenes):
        raise ValueError("Unknown or empty scenes")
    path.parent.mkdir(exist_ok=True, parents=True)
    total = 0
    with path.open("x", encoding="utf-8") as stream:
        for scene in scenes:
            count_by_node = defaultdict(int)
            series, _, _ = make_scene(seed, scene)
            for node, t, values, label in series:
                canonical = checked_node(node)
                count_by_node[canonical] += 1
                record = dict(
                    group=f"reviewed-train-SYNTHETIC-{seed}-{scene}",
                    **{"class": label},
                    message=dict(
                        schema_version=1,
                        type="reading",
                        run_id=f"synthetic-train-{seed}-{scene}",
                        node_id=canonical,
                        boot_id="demo",
                        seq=count_by_node[canonical],
                        timestamp=iso(t),
                        timebase="simulated",
                        measurements=dict(
                            pm25_ug_m3=values[0], pm10_ug_m3=values[1],
                            air_temperature_c=values[2], relative_humidity_pct=values[3],
                        ),
                    ),
                )
                stream.write(json.dumps(record, separators=(",", ":")) + "\n")
                total += 1
    print(json.dumps({"rows": total, "synthetic_only": True,
                      "seed": seed, "scenes": scenes, "path": str(path)}))
    return total


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("/exchange/demo_synthetic.jsonl"))
    p.add_argument("--seed", type=int, default=125)
    a = p.parse_args()
    generate(a.out, a.seed)


if __name__ == "__main__":
    main()
