"""Evaluate per-reading classification and per-episode alert timing separately."""

import csv
import json
from collections import Counter
from pathlib import Path
from edge.logic import Engine, READINGS, SOS, adapt, checked_node
from edge.model import CLASSES, ROOT, Forest
from .episodes import make_scene, SCENES, PERIOD

TEST = tuple(range(201, 231))


def output_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def update_counts(counters, matrix, name, seed, t0, engines, rows):
    first = {k: {} for k in engines}
    pre = Counter()
    sequence = Counter()
    for n, t, values, label in rows:
        seq = sequence[n] = sequence[n] + 1
        for method, engine in engines.items():
            (cls, _), events = engine.evaluate(
                "eval", checked_node(n), "a", seq, t, values, period=PERIOD
            )
            if method == "ml":
                matrix[label, cls] += 1
            for e in events:
                d = e["decision"]
                if d in ("suspected_fire", "environmental_risk"):
                    if t < t0:
                        pre[method] += int(d == "suspected_fire")
                    else:
                        first[method].setdefault(d, t - t0)
    for k in engines:
        counters.append(
            dict(
                seed=seed,
                scenario=name,
                method=k,
                risk_delay_s=rounded(first[k].get("environmental_risk")),
                fire_delay_s=rounded(first[k].get("suspected_fire")),
                alerts_before_onset=pre[k],
            )
        )


def rounded(value):
    return round(value, 2) if value is not None else None


def evaluate(directory, model=None, seeds=TEST):
    directory.mkdir(exist_ok=True, parents=True)
    rows, matrix = [], Counter()
    forest = Forest(model)
    for seed in seeds:
        for name in SCENES:
            stream, _, t0 = make_scene(seed, name)
            engines = {k: Engine(forest, k) for k in ("ml", "rules")}
            update_counts(rows, matrix, name, seed, t0, engines, stream)
    output_csv(directory / "episodios_test.csv", rows)
    output_csv(
        directory / "confusion.csv",
        [dict(real=c, **{p: matrix[c, p] for p in CLASSES}) for c in CLASSES],
    )
    scores = []
    for c in CLASSES:
        tp = matrix[c, c]
        total = sum(matrix[c, p] for p in CLASSES)
        predicted = sum(matrix[p, c] for p in CLASSES)
        scores.append(
            dict(
                clase=c,
                n=total,
                precision=tp / max(1, predicted),
                recall=tp / max(1, total),
                F1=2 * tp / max(1, total + predicted),
            )
        )
    output_csv(directory / "clases.csv", scores)
    result = dict(
        model=forest.version,
        seeds=seeds,
        episode_count=len(rows) // 2,
        samples=sum(matrix.values()),
        accuracy=sum(matrix[c, c] for c in CLASSES) / sum(matrix.values()),
        macro_f1=sum(s["F1"] for s in scores) / len(scores),
    )
    for method in ("ml", "rules"):
        fire = [
            r for r in rows if r["method"] == method and r["scenario"].endswith("_fire")
        ]
        negative = [
            r
            for r in rows
            if r["method"] == method and not r["scenario"].endswith("_fire")
        ]
        delays = [r["fire_delay_s"] for r in fire if r["fire_delay_s"] is not None]
        result[method] = dict(
            detected=len(delays),
            fires=len(fire),
            mean_delay_s=rounded(sum(delays) / len(delays)) if delays else None,
            false_positive_episodes=sum(
                r["fire_delay_s"] is not None or r["alerts_before_onset"] > 0
                for r in negative
            ),
            negative_episodes=len(negative),
            pre_ignition=sum(r["alerts_before_onset"] for r in fire),
        )
    (directory / "validacion.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


def originals(directory, model=None):
    directory.mkdir(exist_ok=True, parents=True)
    result = []
    for file in sorted((ROOT / "data/scenarios").glob("*.jsonl")):
        truth = json.loads(file.with_name(file.stem + "_verdad.json").read_text())
        t0 = 1784073600 + truth["t0_s"]
        for method in ("ml", "rules"):
            engine = Engine(forest=Forest(model), mode=method)
            events = []
            count = 0
            for line in file.open():
                raw = json.loads(line)
                msg = adapt(raw, "external")
                msg["period_s"] = truth["periodo_s"]
                topic = SOS if msg["type"] == "sos" else READINGS + msg["node_id"]
                _, ev = engine.handle(topic, msg)
                events.extend((raw["ts"] / 1000 - t0, e) for e in ev)
                count += 1

            def pick(kind, health=None, node=None):
                return [
                    round(t, 2)
                    for t, e in events
                    if e["decision"] == kind
                    and (not health or e.get("health") == health)
                    and (not node or e["node_id"] == checked_node(node))
                ]

            risk, fire, sos = (
                pick("environmental_risk"),
                pick("suspected_fire"),
                pick("sos_alert"),
            )
            target = truth.get("nodo_evento")
            state = (
                pick("node_health", truth.get("estado_esperado_nodo"), target)
                if truth.get("estado_esperado_nodo")
                else []
            )
            result.append(
                dict(
                    scenario=file.stem,
                    method=method,
                    messages=count,
                    nodes=len(engine.nodes),
                    risk_events=len(risk),
                    fire_events=len(fire),
                    pre_ignition=sum(t < 0 for t in fire),
                    risk_delay_s=next((t for t in risk if t >= 0), None),
                    fire_delay_s=next((t for t in fire if t >= 0), None),
                    sos_outputs=len(sos),
                    first_sos_after_t0_s=next(iter(sos), None),
                    expected_health=truth.get("estado_esperado_nodo"),
                    health_delay_s=next((t for t in state if t >= 0), None),
                )
            )
    output_csv(directory / "escenarios_equipo.csv", result)
    print("Escenarios originales terminados")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--originales", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "resultados")
    ap.add_argument("--model", type=Path, help="Modelo candidato para evaluación")
    ap.add_argument(
        "--validation",
        action="store_true",
        help="Usa semillas 301–306 para elegir candidatos",
    )
    args = ap.parse_args()
    if args.originales:
        originals(args.out, args.model)
    else:
        evaluate(
            args.out, args.model, tuple(range(301, 307)) if args.validation else TEST
        )
