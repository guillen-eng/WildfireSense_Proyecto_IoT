"""Optional cloud job. Rebuild when the reviewed training history changes."""

import argparse
import hashlib
import json
from pathlib import Path
import time
from .train import train


def refresh(directory, interval, once=False):
    history = directory / "reviewed.jsonl"
    candidate = directory / "candidate.json"
    while True:
        if history.exists() and history.stat().st_size:
            fingerprint = hashlib.sha256(history.read_bytes()).hexdigest()
            previous = (
                json.loads(candidate.read_text()).get("reviewed_data_sha256")
                if candidate.exists()
                else None
            )
            if previous != fingerprint:
                train(candidate, history)
            else:
                print("Candidato actualizado", flush=True)
        else:
            print("Esperando histórico etiquetado en", history, flush=True)
        if once:
            return
        time.sleep(interval)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--directory", type=Path, default=Path("/exchange"))
    p.add_argument("--interval", type=int, default=86400)
    p.add_argument("--once", action="store_true")
    a = p.parse_args()
    if a.interval < 1:
        p.error("interval must be positive")
    refresh(a.directory, a.interval, a.once)
