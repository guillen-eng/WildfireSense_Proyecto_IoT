"""Promote a local training artifact after checking contract and self-digest."""

import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from edge.model import Forest, ROOT


def validate_candidate(candidate):
    data = json.loads(candidate.read_text())
    version = data.pop("version")
    digest = hashlib.sha256(
        json.dumps(data, separators=(",", ":")).encode()
    ).hexdigest()[:12]
    if version != "rf-" + digest:
        raise ValueError("Checksum de versión incorrecto")
    model = Forest(candidate)
    # The export uses forward child indices, making cycles invalid.
    if not 1 <= len(model.trees) <= 100:
        raise ValueError("Invalid forest size")
    for tree in model.trees:
        if not 1 <= len(tree) <= 2047:
            raise ValueError("Invalid tree size")
        for index, node in enumerate(tree):
            if len(node) == 4:
                feat, threshold, left, right = node
                if not (
                    type(feat) == int
                    and 0 <= feat < 8
                    and math.isfinite(threshold)
                    and all(
                        type(i) == int and index < i < len(tree) for i in (left, right)
                    )
                ):
                    raise ValueError("Invalid split")
            elif (
                len(node) != 6
                or any(not math.isfinite(x) or x < 0 for x in node)
                or abs(sum(node) - 1) > 1e-6
            ):
                raise ValueError("Invalid class weights")
    for values in [(8, 16, 0.5, 0, 0, 60, 0, 8), (150, 200, 0.75, 45, 3, 40, -2, 100)]:
        model.predict(values)
    return model


def promote(candidate, target):
    model = validate_candidate(candidate)
    version = model.version
    target.parent.mkdir(parents=True, exist_ok=True)
    # Keep the preceding valid model as a separate, immutable version before
    # writing the new one. This is a rollback *artifact*, not auto rollback.
    if target.exists() and target.read_bytes() != candidate.read_bytes():
        current = validate_candidate(target)
        previous = target.with_name(f"forest.{current.version}.json")
        if not previous.exists():
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as bf:
                backup_tmp = Path(bf.name)
                bf.write(target.read_bytes())
            try:
                os.chmod(backup_tmp, 0o644)
                os.replace(backup_tmp, previous)
            finally:
                backup_tmp.unlink(missing_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as f:
        temp = Path(f.name)
        f.write(candidate.read_bytes())
    try:
        os.chmod(temp, 0o644)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    print("Modelo promovido", version)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("candidate", type=Path)
    p.add_argument("--target", type=Path, default=ROOT / "models/forest.json")
    a = p.parse_args()
    promote(a.candidate, a.target)
