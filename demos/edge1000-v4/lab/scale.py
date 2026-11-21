"""Repeat the same environmental scene for four grid sizes, in-process."""

import json
import csv
from edge.model import ROOT
from .demo import run


def scale(path):
    rows = []
    for n in (5, 10, 100, 1000):
        r = run(n, 48)
        rows.append(
            dict(
                nodes=n,
                readings=r["lecturas"],
                wall_s=r["segundos_en_este_equipo"],
                readings_per_s=round(r["lecturas"] / r["segundos_en_este_equipo"], 1),
                first_fire_demo_s=r["primero"]
                .get("suspected_fire", {})
                .get("segundo_de_demo"),
            )
        )
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    scale(ROOT / "resultados/escalado_local.csv")
