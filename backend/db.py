"""Authoritative integration state for EventOps Autopilot.

Guest and procurement tables share this SQLite file.  This store owns the event
brief, plan, workflow outputs, cross-module issues, disruptions, and audit trail.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.schemas import EventBrief


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"Cannot JSON encode {type(value).__name__}")


def dumps(value: Any) -> str:
    return json.dumps(value, default=_json_default, separators=(",", ":"))


def database_path_from_env() -> str:
    explicit = os.getenv("EVENTOPS_DB_PATH")
    if explicit:
        return explicit
    url = os.getenv("DATABASE_URL", "sqlite:///./eventops.db")
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise ValueError("Only sqlite DATABASE_URL values are supported")
    path = url[len(prefix) :]
    return path or "eventops.db"


class EventStore:
    """Thread-safe event-level store layered over the shared SQLite database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = str(db_path or database_path_from_env())
        self._lock = threading.RLock()
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if self.db_path != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _init_db(self) -> None:
        with self._lock, self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    brief_json TEXT NOT NULL,
                    plan_json TEXT,
                    guest_result_json TEXT,
                    vendor_result_json TEXT,
                    readiness_json TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS integration_issues (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(event_id) REFERENCES events(event_id)
                );
                CREATE TABLE IF NOT EXISTS integration_audit (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    source_mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    references_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY(event_id) REFERENCES events(event_id)
                );
                CREATE TABLE IF NOT EXISTS disruptions (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(event_id) REFERENCES events(event_id)
                );
                CREATE INDEX IF NOT EXISTS idx_integration_audit_event
                    ON integration_audit(event_id, timestamp);
                CREATE INDEX IF NOT EXISTS idx_integration_issues_event
                    ON integration_issues(event_id, status);
                """
            )

    def create_event(self, event_id: str, run_id: str, brief: EventBrief) -> None:
        now = utcnow().isoformat()
        with self._lock, self.connect() as db:
            db.execute(
                """INSERT INTO events
                   (event_id, run_id, status, brief_json, created_at, updated_at)
                   VALUES (?, ?, 'PLANNING', ?, ?, ?)""",
                (event_id, run_id, dumps(brief.model_dump(mode="json")), now, now),
            )
        self.record_audit(
            event_id,
            action="EVENT_CREATED",
            tool="event_store",
            source_mode="SIMULATED",
            status="SUCCESS",
            reason="Validated event request persisted",
            references=[run_id],
        )

    def event_exists(self, event_id: str) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM events WHERE event_id = ?", (event_id,)).fetchone() is not None

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if not row:
            return None
        value = dict(row)
        for column, target in (
            ("brief_json", "brief"),
            ("plan_json", "plan"),
            ("guest_result_json", "guest_result"),
            ("vendor_result_json", "vendor_result"),
            ("readiness_json", "readiness"),
        ):
            value[target] = json.loads(value[column]) if value.get(column) else None
        return value

    def update_event(self, event_id: str, **fields: Any) -> None:
        allowed = {
            "status",
            "plan",
            "guest_result",
            "vendor_result",
            "readiness",
            "last_error",
            "brief",
        }
        invalid = set(fields) - allowed
        if invalid:
            raise ValueError(f"Unsupported event fields: {sorted(invalid)}")
        assignments: list[str] = []
        values: list[Any] = []
        for name, value in fields.items():
            column = f"{name}_json" if name in {"plan", "guest_result", "vendor_result", "readiness", "brief"} else name
            assignments.append(f"{column} = ?")
            values.append(dumps(value) if column.endswith("_json") and value is not None else value)
        assignments.append("updated_at = ?")
        values.extend([utcnow().isoformat(), event_id])
        with self._lock, self.connect() as db:
            cursor = db.execute(
                f"UPDATE events SET {', '.join(assignments)} WHERE event_id = ?", values
            )
            if cursor.rowcount != 1:
                raise KeyError(event_id)

    def record_audit(
        self,
        event_id: str,
        *,
        action: str,
        tool: str,
        source_mode: str,
        status: str,
        reason: str,
        references: list[str] | None = None,
        audit_id: str | None = None,
    ) -> str:
        timestamp = utcnow().isoformat()
        audit_id = audit_id or "log_" + hashlib.sha256(
            f"{event_id}|{action}|{timestamp}".encode()
        ).hexdigest()[:18]
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO integration_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    audit_id,
                    event_id,
                    action,
                    tool,
                    source_mode,
                    status,
                    reason,
                    dumps(references or []),
                    timestamp,
                ),
            )
        return audit_id

    def get_audit(self, event_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM integration_audit WHERE event_id = ? ORDER BY timestamp, id",
                (event_id,),
            ).fetchall()
        return [dict(row) | {"references": json.loads(row["references_json"])} for row in rows]

    def record_issue(
        self,
        event_id: str,
        issue_type: str,
        message: str,
        *,
        severity: str = "CRITICAL",
        status: str = "OPEN",
        issue_id: str | None = None,
    ) -> str:
        issue_id = issue_id or "iss_" + hashlib.sha256(
            f"{event_id}|{issue_type}|{message}".encode()
        ).hexdigest()[:18]
        now = utcnow().isoformat()
        with self._lock, self.connect() as db:
            db.execute(
                """INSERT INTO integration_issues VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                   message=excluded.message, updated_at=excluded.updated_at""",
                (issue_id, event_id, issue_type, severity, status, message, now, now),
            )
        return issue_id

    def get_issues(self, event_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM integration_issues WHERE event_id = ? ORDER BY created_at, id",
                    (event_id,),
                )
            ]

    def begin_disruption(
        self, event_id: str, event_type: str, payload: dict[str, Any], idempotency_key: str
    ) -> tuple[dict[str, Any], bool]:
        with self._lock, self.connect() as db:
            existing = db.execute(
                "SELECT * FROM disruptions WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                value = dict(existing)
                value["result"] = json.loads(value["result_json"]) if value.get("result_json") else None
                return value, False
            now = utcnow().isoformat()
            disruption_id = "dis_" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:18]
            db.execute(
                "INSERT INTO disruptions VALUES (?, ?, ?, ?, ?, NULL, 'RECOVERING', ?, ?)",
                (disruption_id, event_id, idempotency_key, event_type, dumps(payload), now, now),
            )
        return {
            "id": disruption_id,
            "event_id": event_id,
            "event_type": event_type,
            "status": "RECOVERING",
            "result": None,
        }, True

    def finish_disruption(self, disruption_id: str, status: str, result: dict[str, Any]) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "UPDATE disruptions SET result_json = ?, status = ?, updated_at = ? WHERE id = ?",
                (dumps(result), status, utcnow().isoformat(), disruption_id),
            )

    def list_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            value = dict(row)
            for column, target in (
                ("brief_json", "brief"),
                ("plan_json", "plan"),
                ("guest_result_json", "guest_result"),
                ("vendor_result_json", "vendor_result"),
                ("readiness_json", "readiness"),
            ):
                value[target] = json.loads(value[column]) if value.get(column) else None
            results.append(value)
        return results


__all__ = ["EventStore", "database_path_from_env", "dumps", "utcnow"]
