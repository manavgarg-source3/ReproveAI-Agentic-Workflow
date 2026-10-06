"""Small durable SQLite repository for the Step 6 single-node MVP."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class ExecutionRepository:
    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.getenv("REPROVE_EXECUTION_DB", ".data/execution.db")
        self.path = Path(configured)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS approvals (
                  approval_id TEXT PRIMARY KEY, target_id TEXT NOT NULL,
                  payload TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
                  expires_at TEXT, revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                  staging_id TEXT PRIMARY KEY, target_id TEXT NOT NULL,
                  artifact_id TEXT NOT NULL, payload TEXT NOT NULL,
                  source TEXT NOT NULL, snapshot_path TEXT NOT NULL,
                  sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                  created_at TEXT NOT NULL, immutable INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                  run_id TEXT PRIMARY KEY, target_id TEXT NOT NULL,
                  payload TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                  event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                  event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                  run_id TEXT PRIMARY KEY, target_id TEXT NOT NULL, approval_id TEXT NOT NULL,
                  policy TEXT NOT NULL, status TEXT NOT NULL, worker_id TEXT,
                  claimed_at TEXT, heartbeat_at TEXT, lease_expiry TEXT, released_at TEXT
                );
                CREATE TABLE IF NOT EXISTS comparisons (
                  comparison_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                  target_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS investigations (
                  investigation_id TEXT PRIMARY KEY, target_id TEXT NOT NULL,
                  payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sandbox_handles (
                  run_id TEXT PRIMARY KEY, container_name TEXT NOT NULL,
                  cancel_requested INTEGER NOT NULL DEFAULT 0,
                  cleanup_status TEXT NOT NULL DEFAULT 'PENDING'
                );
                CREATE TABLE IF NOT EXISTS observed_results (
                  observed_id TEXT PRIMARY KEY, target_id TEXT NOT NULL,
                  run_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS diagnostic_approvals (
                  approval_id TEXT PRIMARY KEY, diagnostic_plan_id TEXT NOT NULL, target_id TEXT NOT NULL,
                  payload TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS diagnostic_executions (
                  diagnostic_execution_id TEXT PRIMARY KEY, diagnostic_plan_id TEXT NOT NULL, target_id TEXT NOT NULL,
                  payload TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS hypotheses (
                  hypothesis_id TEXT PRIMARY KEY, discrepancy_id TEXT NOT NULL,
                  payload TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS hypothesis_tests (
                  test_id TEXT PRIMARY KEY, hypothesis_id TEXT NOT NULL, diagnostic_execution_id TEXT NOT NULL,
                  payload TEXT NOT NULL, created_at TEXT NOT NULL,
                  UNIQUE(diagnostic_execution_id)
                );
                CREATE TABLE IF NOT EXISTS state_transitions (
                  event_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
                  payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_cases (
                  research_case_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS graph_snapshots (
                  graph_snapshot_id TEXT PRIMARY KEY, research_case_id TEXT NOT NULL,
                  payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS immutable_terminal_run
                BEFORE UPDATE ON runs
                WHEN OLD.status IN ('COMPLETED','FAILED','BLOCKED','CANCELLED','TIMED_OUT','INTERRUPTED')
                BEGIN SELECT RAISE(ABORT, 'Terminal execution records are immutable'); END;
                """
            )
            for row in db.execute("SELECT approval_id,payload,revoked_at FROM approvals WHERE status='REVOKED'").fetchall():
                payload = json.loads(row['payload'])
                payload.update(status='REVOKED', revoked_at=row['revoked_at'])
                db.execute('UPDATE approvals SET payload=? WHERE approval_id=?', (json.dumps(payload,sort_keys=True),row['approval_id']))

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, table: str, key: str, target_id: str, payload: Any, status: str, created_at: str) -> None:
        if table == "approvals":
            sql = "INSERT OR REPLACE INTO approvals(approval_id,target_id,payload,status,created_at,expires_at,revoked_at) VALUES(?,?,?,?,?,?,?)"
            data = json.loads(payload) if isinstance(payload, str) else payload
            args = (key, target_id, json.dumps(data, sort_keys=True), status, created_at, data.get("expires_at"), data.get("revoked_at"))
        elif table == "runs":
            sql = "INSERT INTO runs(run_id,target_id,payload,status,created_at) VALUES(?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET payload=excluded.payload,status=excluded.status"
            args = (key, target_id, payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True), status, created_at)
        else:
            raise ValueError(table)
        with self._lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if table == 'runs':
                previous = db.execute('SELECT status,payload FROM runs WHERE run_id=?', (key,)).fetchone()
                if previous and previous['status'] in {'COMPLETED','FAILED','BLOCKED','CANCELLED','TIMED_OUT','INTERRUPTED'}:
                    if json.loads(previous['payload']) != json.loads(args[2]):
                        raise ValueError('Terminal execution records are immutable.')
                    return
                if previous and previous['status'] == 'CANCEL_REQUESTED' and status in {'COMPLETED','FAILED','TIMED_OUT'}:
                    handle = db.execute('SELECT cleanup_status FROM sandbox_handles WHERE run_id=?',(key,)).fetchone()
                    if not handle or handle[0] != 'DONE':
                        raise ValueError('Cancellation cleanup is not confirmed')
                    payload = json.loads(args[2])
                    payload.update(status='CANCELLED',failure_code=None,failure_reason='Cancellation finalized after sandbox cleanup.')
                    args = (key,target_id,json.dumps(payload,sort_keys=True),'CANCELLED',created_at)
            if table == 'approvals':
                previous = db.execute('SELECT status FROM approvals WHERE approval_id=?', (key,)).fetchone()
                if previous:
                    raise ValueError('Approval identity is immutable; use revocation.')
            db.execute(sql, args)

    def load(self, table: str, key: str) -> dict[str, Any] | None:
        column = "approval_id" if table == "approvals" else "run_id"
        with self._connect() as db:
            row = db.execute(f"SELECT payload FROM {table} WHERE {column}=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, table: str, target_id: str) -> list[dict[str, Any]]:
        column = "target_id"
        with self._connect() as db:
            rows = db.execute(f"SELECT payload FROM {table} WHERE {column}=? ORDER BY created_at", (target_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def event(self, event_id: str, run_id: str, event_type: str, payload: dict[str, Any], created_at: str) -> None:
        safe = {k: v for k, v in payload.items() if not any(s in k.casefold() for s in ("secret", "token", "password", "key"))}
        with self._lock, self._connect() as db:
            db.execute("INSERT OR REPLACE INTO events(event_id,run_id,event_type,payload,created_at) VALUES(?,?,?,?,?)", (event_id, run_id, event_type, json.dumps(safe, sort_keys=True), created_at))

    def put_artifact(self, staging_id: str, target_id: str, artifact_id: str, source: str, snapshot_path: str, sha256: str, size_bytes: int, created_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT OR REPLACE INTO artifacts(staging_id,target_id,artifact_id,payload,source,snapshot_path,sha256,size_bytes,created_at,immutable) VALUES(?,?,?,?,?,?,?,?,?,1)", (staging_id, target_id, artifact_id, "{}", source, snapshot_path, sha256, size_bytes, created_at))

    def artifact(self, target_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM artifacts WHERE target_id=? ORDER BY created_at DESC LIMIT 1", (target_id,)).fetchone()
        return dict(row) if row else None

    def revoke(self, approval_id: str, revoked_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM approvals WHERE approval_id=?', (approval_id,)).fetchone()
            if row is None:
                raise ValueError('Unknown approval')
            payload = json.loads(row['payload'])
            payload.update(status='REVOKED', revoked_at=revoked_at)
            db.execute("UPDATE approvals SET status='REVOKED', revoked_at=?,payload=? WHERE approval_id=?", (revoked_at,json.dumps(payload,sort_keys=True),approval_id))

    def enqueue(self, run_id: str, target_id: str, approval_id: str, policy: dict[str, Any]) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO jobs(run_id,target_id,approval_id,policy,status) VALUES(?,?,?,?,?)", (run_id, target_id, approval_id, json.dumps(policy, sort_keys=True), "QUEUED"))

    def claim(self, run_id: str, worker_id: str, now: str, lease_expiry: str) -> bool:
        with self._lock, self._connect() as db:
            row = db.execute("UPDATE jobs SET status='CLAIMED',worker_id=?,claimed_at=?,heartbeat_at=?,lease_expiry=? WHERE run_id=? AND status='QUEUED'", (worker_id, now, now, lease_expiry, run_id))
            return row.rowcount == 1

    def release(self, run_id: str, status: str, released_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE jobs SET status=?,released_at=? WHERE run_id=?", (status, released_at, run_id))

    def active_jobs(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM jobs WHERE status='CLAIMED'").fetchall()]

    def sandbox_handle(self, run_id: str, container_name: str) -> None:
        with self._connect() as db:
            db.execute('INSERT OR IGNORE INTO sandbox_handles(run_id,container_name) VALUES(?,?)', (run_id,container_name))

    def handle(self, run_id: str):
        with self._connect() as db:
            row = db.execute('SELECT * FROM sandbox_handles WHERE run_id=?',(run_id,)).fetchone()
            return dict(row) if row else None

    def cleanup(self, run_id: str, success: bool) -> None:
        with self._connect() as db:
            db.execute('UPDATE sandbox_handles SET cleanup_status=? WHERE run_id=?',('DONE' if success else 'FAILED',run_id))

    def heartbeat(self, run_id: str, worker_id: str, now: str, expiry: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE jobs SET heartbeat_at=?,lease_expiry=? WHERE run_id=? AND worker_id=? AND status='CLAIMED'",(now,expiry,run_id,worker_id))

    def request_cancel(self, target_id: str, run_id: str) -> dict:
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload,status FROM runs WHERE run_id=? AND target_id=?',(run_id,target_id)).fetchone()
            if not row:
                raise ValueError('Unknown run')
            if row['status'] in {'CANCELLED','CANCEL_REQUESTED'}:
                return json.loads(row['payload'])
            if row['status'] in {'COMPLETED','FAILED','BLOCKED','TIMED_OUT','INTERRUPTED'}:
                raise ValueError('Terminal run cannot be cancelled')
            payload = json.loads(row['payload'])
            payload['status'] = 'CANCEL_REQUESTED'
            db.execute("UPDATE runs SET status='CANCEL_REQUESTED',payload=? WHERE run_id=?",(json.dumps(payload,sort_keys=True),run_id))
            db.execute('UPDATE sandbox_handles SET cancel_requested=1 WHERE run_id=?',(run_id,))
            return payload

    def put_comparison(self, comparison_id: str, run_id: str, target_id: str, payload: dict[str, Any], created_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT OR IGNORE INTO comparisons(comparison_id,run_id,target_id,payload,created_at) VALUES(?,?,?,?,?)", (comparison_id, run_id, target_id, json.dumps(payload, sort_keys=True), created_at))

    def load_comparison(self, target_id: str, run_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM comparisons WHERE target_id=? AND run_id=?", (target_id, run_id)).fetchone()
        return json.loads(row[0]) if row else None

    def put_observed_result(self, observed_id: str, target_id: str, run_id: str, payload: dict[str, Any], created_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT OR IGNORE INTO observed_results(observed_id,target_id,run_id,payload,created_at) VALUES(?,?,?,?,?)", (observed_id, target_id, run_id, json.dumps(payload, sort_keys=True), created_at))

    def load_observed_result(self, target_id: str, run_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM observed_results WHERE target_id=? AND run_id=?", (target_id, run_id)).fetchone()
        return json.loads(row[0]) if row else None

    def put_investigation(self, investigation_id: str, target_id: str, payload: dict[str, Any], created_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT OR IGNORE INTO investigations(investigation_id,target_id,payload,created_at) VALUES(?,?,?,?)", (investigation_id, target_id, json.dumps(payload, sort_keys=True), created_at))

    def investigations(self, target_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT payload FROM investigations WHERE target_id=? ORDER BY created_at", (target_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def put_diagnostic_approval(self, approval_id: str, diagnostic_plan_id: str, target_id: str, payload: dict[str, Any], created_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT OR REPLACE INTO diagnostic_approvals(approval_id,diagnostic_plan_id,target_id,payload,status,created_at) VALUES(?,?,?,?,?,?)", (approval_id, diagnostic_plan_id, target_id, json.dumps(payload, sort_keys=True), payload.get('status', 'APPROVED'), created_at))

    def load_diagnostic_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM diagnostic_approvals WHERE approval_id=?", (approval_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def put_diagnostic_execution(self, diagnostic_execution_id: str, diagnostic_plan_id: str, target_id: str, payload: dict[str, Any], status: str, created_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO diagnostic_executions(diagnostic_execution_id,diagnostic_plan_id,target_id,payload,status,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(diagnostic_execution_id) DO UPDATE SET payload=excluded.payload, status=excluded.status", (diagnostic_execution_id, diagnostic_plan_id, target_id, json.dumps(payload, sort_keys=True), status, created_at))

    def load_diagnostic_execution(self, diagnostic_execution_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM diagnostic_executions WHERE diagnostic_execution_id=?", (diagnostic_execution_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def diagnostic_executions(self, investigation_id: str) -> list[dict[str, Any]]:
        # Since we don't have investigation_id directly in the diagnostic_executions table columns, we filter the payload.
        # It's a small durable DB for the MVP, so this is fine.
        with self._connect() as db:
            rows = db.execute("SELECT payload FROM diagnostic_executions ORDER BY created_at").fetchall()
        executions = [json.loads(row[0]) for row in rows]
        return [ex for ex in executions if ex.get("investigation_id") == investigation_id]

    def put_hypothesis(self, hypothesis_id: str, discrepancy_id: str, payload: dict[str, Any], status: str, created_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO hypotheses(hypothesis_id,discrepancy_id,payload,status,created_at) VALUES(?,?,?,?,?) ON CONFLICT(hypothesis_id) DO UPDATE SET payload=excluded.payload, status=excluded.status", (hypothesis_id, discrepancy_id, json.dumps(payload, sort_keys=True), status, created_at))

    def load_hypothesis(self, hypothesis_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM hypotheses WHERE hypothesis_id=?", (hypothesis_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def put_hypothesis_test(self, test_id: str, hypothesis_id: str, diagnostic_execution_id: str, payload: dict[str, Any], created_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO hypothesis_tests(test_id,hypothesis_id,diagnostic_execution_id,payload,created_at) VALUES(?,?,?,?,?)", (test_id, hypothesis_id, diagnostic_execution_id, json.dumps(payload, sort_keys=True), created_at))

    def load_hypothesis_test_by_diagnostic(self, diagnostic_execution_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM hypothesis_tests WHERE diagnostic_execution_id=?", (diagnostic_execution_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def hypothesis_tests(self, hypothesis_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT payload FROM hypothesis_tests WHERE hypothesis_id=? ORDER BY created_at", (hypothesis_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def put_state_transition(self, event_id: str, entity_type: str, entity_id: str, payload: dict[str, Any], created_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO state_transitions(event_id,entity_type,entity_id,payload,created_at) VALUES(?,?,?,?,?)", (event_id, entity_type, entity_id, json.dumps(payload, sort_keys=True), created_at))

    def state_transitions(self, entity_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT payload FROM state_transitions WHERE entity_id=? ORDER BY created_at", (entity_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def update_investigation(self, investigation_id: str, payload: dict[str, Any]) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE investigations SET payload=? WHERE investigation_id=?", (json.dumps(payload, sort_keys=True), investigation_id))

    def save_evaluation_result(self, hypothesis: dict[str, Any], test: dict[str, Any], transitions: list[dict[str, Any]], investigation: dict[str, Any], test_created_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("INSERT INTO hypotheses(hypothesis_id,discrepancy_id,payload,status,created_at) VALUES(?,?,?,?,?) ON CONFLICT(hypothesis_id) DO UPDATE SET payload=excluded.payload, status=excluded.status", (hypothesis["hypothesis_id"], hypothesis["discrepancy_id"], json.dumps(hypothesis, sort_keys=True), hypothesis["status"], test_created_at))
                db.execute("INSERT INTO hypothesis_tests(test_id,hypothesis_id,diagnostic_execution_id,payload,created_at) VALUES(?,?,?,?,?)", (test["id"], test["hypothesis_id"], test["diagnostic_execution_id"], json.dumps(test, sort_keys=True), test_created_at))
                db.execute("UPDATE investigations SET payload=? WHERE investigation_id=?", (json.dumps(investigation, sort_keys=True), investigation["investigation_id"]))
                for t in transitions:
                    db.execute("INSERT INTO state_transitions(event_id,entity_type,entity_id,payload,created_at) VALUES(?,?,?,?,?)", (t["id"], t["entity_type"], t["entity_id"], json.dumps(t, sort_keys=True), t["created_at"]))
                db.commit()
            except Exception as e:
                db.rollback()
                raise e

    def put_research_case(self, research_case_id: str, payload: dict[str, Any], created_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO research_cases(research_case_id, payload, created_at) VALUES(?, ?, ?)",
                (research_case_id, json.dumps(payload, sort_keys=True), created_at),
            )

    def load_research_case(self, research_case_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT payload FROM research_cases WHERE research_case_id=?", (research_case_id,)
            ).fetchone()
            if not row:
                return None
            return json.loads(row[0])

    def put_graph_snapshot(self, graph_snapshot_id: str, research_case_id: str, payload: dict[str, Any], created_at: str) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO graph_snapshots(graph_snapshot_id, research_case_id, payload, created_at) VALUES(?, ?, ?, ?)",
                (graph_snapshot_id, research_case_id, json.dumps(payload, sort_keys=True), created_at),
            )

    def load_graph_snapshot(self, research_case_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT payload FROM graph_snapshots WHERE research_case_id=? ORDER BY created_at DESC LIMIT 1",
                (research_case_id,)
            ).fetchone()
            if not row:
                return None
            return json.loads(row[0])
