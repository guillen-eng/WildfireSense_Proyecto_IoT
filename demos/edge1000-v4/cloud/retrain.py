"""Retraining on verified labels, synthetic gate, model registry and rollback.

Trigger: N new labels since the last run. Candidates never go live on their own:
promotion is explicit (button or API), and only for candidates that passed the gate.
Rollback restores the previous registered version.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from edge.model import ROOT

TRIGGER_LABELS = 10
STATUSES = ("active", "candidate", "previous", "rejected")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _subprocess_train(extra, output):
    subprocess.run(
        [sys.executable, "-m", "lab.train", "--output", str(output), "--extra", str(extra)],
        cwd=ROOT, check=True, capture_output=True, timeout=3600,
    )


def _subprocess_gate(candidate, baseline, report):
    # The gate exits non-zero when it rejects; the report is written either way.
    subprocess.run(
        [sys.executable, "-m", "lab.model_gate", "--candidate", str(candidate),
         "--baseline", str(baseline), "--out", str(report)],
        cwd=ROOT, capture_output=True, timeout=3600,
    )
    return json.loads(Path(report).read_text(encoding="utf-8"))


def _scenario_check(candidate, baseline):
    """The team's nine scenarios: the candidate must not regress against the deployed model."""
    from lab.scenario_gate import DEFAULT_DIR, compare

    if not DEFAULT_DIR.exists():
        # Promotion is advertised as conditional on the nine scenarios: absence blocks it.
        if os.environ.get("ALLOW_MISSING_SCENARIOS") == "1":
            return dict(approved=True, skipped="scenarios_unavailable")
        return dict(approved=False, regressions=["scenarios_unavailable"])
    return compare(Path(candidate), Path(baseline))


def _version(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))["version"]


def _promote(candidate, target):
    from lab.promote import promote

    promote(Path(candidate), Path(target))


class Retrainer:
    def __init__(self, store, work_dir, model_path=None, trigger_labels=TRIGGER_LABELS,
                 train_fn=_subprocess_train, gate_fn=_subprocess_gate, promote_fn=_promote,
                 scenario_fn=_scenario_check):
        self.store = store
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = Path(model_path or ROOT / "models/forest.json")
        self.trigger_labels = trigger_labels
        self.train_fn, self.gate_fn, self.promote_fn = train_fn, gate_fn, promote_fn
        self.scenario_fn = scenario_fn
        self.lock = threading.Lock()
        with store.connect() as conn:
            if conn.execute("SELECT COUNT(*) FROM models").fetchone()[0] == 0:
                conn.execute(
                    "INSERT INTO models(version,status,metrics_json,created_at) VALUES (?,?,?,?)",
                    (_version(self.model_path), "active", None, _now()),
                )

    # --- state -----------------------------------------------------------
    def pending_labels(self):
        with self.store.connect() as conn:
            last = conn.execute("SELECT MAX(started_at) FROM retrain_runs").fetchone()[0]
            if last is None:
                return conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
            return conn.execute(
                "SELECT COUNT(*) FROM labels WHERE created_at > ?", (last,)
            ).fetchone()[0]

    def state(self):
        with self.store.connect() as conn:
            models = [dict(r) for r in conn.execute(
                "SELECT version,status,metrics_json,created_at FROM models ORDER BY created_at DESC")]
            runs = [dict(r) for r in conn.execute(
                "SELECT * FROM retrain_runs ORDER BY id DESC LIMIT 20")]
        for m in models:
            m["metrics"] = json.loads(m.pop("metrics_json") or "null")
        return dict(models=models, runs=runs, pending_labels=self.pending_labels(),
                    trigger_labels=self.trigger_labels, running=self.lock.locked())

    # --- retraining ------------------------------------------------------
    def maybe_trigger(self):
        """Start a background run when enough new verified labels exist."""
        if self.lock.locked() or self.pending_labels() < self.trigger_labels:
            return False
        threading.Thread(target=self.run, args=("labels",), daemon=True).start()
        return True

    def run(self, trigger="manual"):
        if not self.lock.acquire(blocking=False):
            return dict(result="busy")
        try:
            used = self.pending_labels()
            with self.store.connect() as conn:
                run_id = conn.execute(
                    "INSERT INTO retrain_runs(started_at,trigger,labels_used) VALUES (?,?,?)",
                    (_now(), trigger, used),
                ).lastrowid
            result, version = self._execute(run_id)
            with self.store.connect() as conn:
                conn.execute(
                    "UPDATE retrain_runs SET finished_at=?,result=?,model_version=? WHERE id=?",
                    (_now(), result, version, run_id),
                )
            return dict(result=result, model_version=version, run_id=run_id)
        finally:
            self.lock.release()

    def _execute(self, run_id):
        extra = self.work_dir / f"extra_{run_id}.jsonl"
        if self.store.export_training(extra) == 0:
            return "no_data", None
        candidate = self.work_dir / f"candidate_{run_id}.json"
        try:
            self.train_fn(extra, candidate)
            version = _version(candidate)
            report = self.gate_fn(candidate, self.model_path, self.work_dir / f"gate_{run_id}.json")
            scenarios = self.scenario_fn(candidate, self.model_path)
        except Exception as exc:  # noqa: BLE001 - recorded, never fatal for the Cloud
            return f"error: {type(exc).__name__}", None
        final = self.work_dir / f"forest.{version}.json"
        candidate.replace(final)
        reasons = list(report.get("reasons") or [])
        if not scenarios.get("approved"):
            reasons += [f"scenario_regression:{n}" for n in scenarios.get("regressions", [])]
        approved = (
            bool(report.get("approved"))
            and bool(scenarios.get("approved"))
            and not report.get("same_version")
        )
        status = "candidate" if approved else "rejected"
        passed = scenarios.get("candidate", {})
        metrics = dict(approved=approved, reasons=reasons,
                       scenarios=dict(passed=passed.get("passed"), total=passed.get("total"),
                                      failed=passed.get("failed"), skipped=scenarios.get("skipped")),
                       baseline=report.get("baseline_model"),
                       candidate=report.get("candidate"), reference=report.get("baseline"))
        with self.store.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO models(version,status,metrics_json,created_at) VALUES (?,?,?,?)",
                (version, status, json.dumps(metrics), _now()),
            )
        return ("candidate" if approved else "rejected"), version

    # --- promotion and rollback -------------------------------------------
    def _active(self, conn):
        row = conn.execute("SELECT version FROM models WHERE status='active'").fetchone()
        return row[0] if row else None

    def promote(self, version):
        with self.store.connect() as conn:
            row = conn.execute("SELECT status FROM models WHERE version=?", (version,)).fetchone()
            if row is None or row[0] != "candidate":
                raise ValueError("only gate-approved candidates can be promoted")
            old = self._active(conn)
        if old:
            keep = self.work_dir / f"forest.{old}.json"
            if not keep.exists() and self.model_path.exists():
                keep.write_bytes(self.model_path.read_bytes())
        self.promote_fn(self.work_dir / f"forest.{version}.json", self.model_path)
        with self.store.connect() as conn:
            conn.execute("UPDATE models SET status='candidate' WHERE status='previous'")
            if old:
                conn.execute("UPDATE models SET status='previous' WHERE version=?", (old,))
            conn.execute("UPDATE models SET status='active' WHERE version=?", (version,))
        return version

    def rollback(self):
        with self.store.connect() as conn:
            prev = conn.execute(
                "SELECT version FROM models WHERE status='previous' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            current = self._active(conn)
        if prev is None:
            raise ValueError("no previous model to restore")
        version = prev[0]
        source = self.work_dir / f"forest.{version}.json"
        if not source.exists():
            source = self.model_path.with_name(f"forest.{version}.json")
        if not source.exists():
            raise ValueError("previous model file is missing")
        self.promote_fn(source, self.model_path)
        with self.store.connect() as conn:
            conn.execute("UPDATE models SET status='candidate' WHERE version=?", (current,))
            conn.execute("UPDATE models SET status='active' WHERE version=?", (version,))
        return version
