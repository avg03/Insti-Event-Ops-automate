"""Persistent, deterministic local guest inbox and calendar simulator."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable(prefix: str, *parts: str) -> str:
    value = "|".join(parts)
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:18]}"


class SimulatedGuestChannel:
    """A local-only channel; it has no networking or real messaging capability."""

    def __init__(self, db_path: str | Path | None = None, scenario_path: str | Path | None = None) -> None:
        configured = db_path or os.getenv("GUEST_SIMULATOR_DB", "eventops_guest.db")
        self.db_path = str(configured)
        self.scenario_path = Path(scenario_path or Path(__file__).with_name("guest_scenarios.json"))
        self._overrides: dict[str, dict[str, Any]] = {}
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS guest_invitations (
                    invitation_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    terms_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS guest_messages (
                    message_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    response_type TEXT,
                    text TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    delivered INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS guest_bookings (
                    booking_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    slot_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'SIMULATED',
                    created_at TEXT NOT NULL,
                    cancelled_at TEXT
                );
                CREATE TABLE IF NOT EXISTS guest_audit (
                    audit_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    candidate_id TEXT,
                    action TEXT NOT NULL,
                    reference_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _scenario(self, candidate_id: str) -> dict[str, Any]:
        if candidate_id in self._overrides:
            return self._overrides[candidate_id]
        data = json.loads(self.scenario_path.read_text(encoding="utf-8"))
        personas = data.get("personas", [])
        if not personas:
            return {"behavior": "no_response"}
        index = int(hashlib.sha256(candidate_id.encode()).hexdigest(), 16) % len(personas)
        return dict(personas[index])

    def set_candidate_scenario(self, candidate_id: str, scenario: dict[str, Any]) -> None:
        """Select a test/demo persona without coupling it to a real identity."""
        self._overrides[candidate_id] = dict(scenario)

    def _reply_for(self, candidate_id: str, *, counteroffer: bool, terms: dict[str, Any]) -> dict[str, Any] | None:
        scenario = self._scenario(candidate_id)
        behavior = str(scenario.get("behavior", "no_response")).lower()
        if behavior == "no_response":
            return None
        if behavior == "decline":
            return {
                "response": "DECLINED",
                "text": f"I cannot attend due to {scenario.get('reason', 'a scheduling conflict')}.",
            }
        if behavior == "cancelled":
            return {"response": "CANCELLED", "text": "I need to cancel my participation."}
        requested = dict(scenario.get("request") or {})
        if behavior == "conditional" and not counteroffer:
            start_after = requested.get("start_after")
            fee = requested.get("honorarium_inr", 0)
            pieces = []
            if start_after:
                pieces.append(f"only after {start_after}")
            if fee:
                pieces.append(f"with an honorarium of INR {fee}")
            return {
                "response": "CONDITIONAL",
                "text": "I can attend, but " + " and ".join(pieces) + ".",
                "conditions": requested,
            }
        if behavior == "conditional" and counteroffer:
            offered_fee = int(terms.get("honorarium_inr", 0))
            required_fee = int(requested.get("honorarium_inr", 0))
            slot = terms.get("slot") or {}
            start = str(slot.get("starts_at", ""))
            required_start = str(requested.get("start_after", ""))
            start_ok = not required_start or ("T" in start and start.split("T", 1)[1][:5] >= required_start)
            if offered_fee >= required_fee and start_ok:
                return {"response": "ACCEPTED", "text": "I accept the revised simulated terms."}
            return {"response": "DECLINED", "text": "The revised terms do not meet my conditions."}
        return {
            "response": "ACCEPTED",
            "text": "I accept the simulated invitation.",
            "conditions": {"honorarium_inr": int(scenario.get("honorarium_inr", 0))},
        }

    async def send_invitation(
        self,
        event_id: str,
        candidate_id: str,
        terms: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        invitation_id = _stable("inv", event_id, candidate_id, idempotency_key)
        thread_id = _stable("thread", event_id, candidate_id)
        with self._connect() as db:
            existing = db.execute(
                "SELECT * FROM guest_invitations WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                return dict(existing) | {"terms": json.loads(existing["terms_json"]), "mode": "SIMULATED"}
            created = _now()
            db.execute(
                "INSERT INTO guest_invitations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (invitation_id, event_id, candidate_id, thread_id, idempotency_key, json.dumps(terms), "INVITED", created),
            )
            outbound_id = _stable("msg", invitation_id, "outbound")
            db.execute(
                "INSERT INTO guest_messages VALUES (?, ?, 'OUTBOUND', NULL, ?, ?, 1, ?)",
                (outbound_id, thread_id, terms.get("invitation_text", "Simulated guest invitation"), json.dumps(terms), created),
            )
            reply = self._reply_for(candidate_id, counteroffer=False, terms=terms)
            if reply:
                message_id = _stable("msg", invitation_id, "reply", reply["response"])
                db.execute(
                    "INSERT OR IGNORE INTO guest_messages VALUES (?, ?, 'INBOUND', ?, ?, ?, 0, ?)",
                    (message_id, thread_id, reply["response"], reply["text"], json.dumps(reply), created),
                )
            self._audit(db, event_id, candidate_id, "INVITATION_SENT", invitation_id, terms)
        return {
            "invitation_id": invitation_id,
            "thread_id": thread_id,
            "event_id": event_id,
            "candidate_id": candidate_id,
            "status": "INVITED",
            "terms": terms,
            "created_at": created,
            "mode": "SIMULATED",
        }

    async def send_counteroffer(
        self, thread_id: str, candidate_id: str, terms: dict[str, Any], round_number: int
    ) -> dict[str, Any]:
        message_id = _stable("msg", thread_id, "counteroffer", str(round_number))
        with self._connect() as db:
            invitation = db.execute(
                "SELECT event_id FROM guest_invitations WHERE thread_id = ?", (thread_id,)
            ).fetchone()
            if not invitation:
                raise KeyError(f"Unknown guest thread {thread_id}")
            existing = db.execute("SELECT * FROM guest_messages WHERE message_id = ?", (message_id,)).fetchone()
            if existing:
                return dict(existing)
            created = _now()
            db.execute(
                "INSERT INTO guest_messages VALUES (?, ?, 'OUTBOUND', NULL, ?, ?, 1, ?)",
                (message_id, thread_id, "Revised simulated offer", json.dumps(terms), created),
            )
            reply = self._reply_for(candidate_id, counteroffer=True, terms=terms)
            if reply:
                reply_id = _stable("msg", message_id, "reply", reply["response"])
                db.execute(
                    "INSERT OR IGNORE INTO guest_messages VALUES (?, ?, 'INBOUND', ?, ?, ?, 0, ?)",
                    (reply_id, thread_id, reply["response"], reply["text"], json.dumps(reply), created),
                )
            self._audit(db, invitation["event_id"], candidate_id, "COUNTEROFFER_SENT", message_id, terms)
        return {"message_id": message_id, "thread_id": thread_id, "mode": "SIMULATED"}

    async def get_replies(self, thread_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM guest_messages WHERE thread_id = ? AND direction = 'INBOUND' AND delivered = 0 ORDER BY created_at, rowid LIMIT 1",
                (thread_id,),
            ).fetchone()
            if not row:
                return None
            db.execute("UPDATE guest_messages SET delivered = 1 WHERE message_id = ?", (row["message_id"],))
            payload = json.loads(row["payload_json"])
            return payload | {
                "message_id": row["message_id"],
                "thread_id": thread_id,
                "created_at": row["created_at"],
                "mode": "SIMULATED",
            }

    async def confirm_calendar(
        self,
        event_id: str,
        candidate_id: str,
        slot: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        booking_id = _stable("booking", event_id, candidate_id, idempotency_key)
        with self._connect() as db:
            existing = db.execute(
                "SELECT * FROM guest_bookings WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                return dict(existing) | {"slot": json.loads(existing["slot_json"])}
            active = db.execute(
                "SELECT * FROM guest_bookings WHERE event_id = ? AND candidate_id = ? AND status = 'CONFIRMED_SIMULATED'",
                (event_id, candidate_id),
            ).fetchone()
            if active:
                return dict(active) | {"slot": json.loads(active["slot_json"])}
            created = _now()
            db.execute(
                "INSERT INTO guest_bookings VALUES (?, ?, ?, ?, ?, 'CONFIRMED_SIMULATED', 'SIMULATED', ?, NULL)",
                (booking_id, event_id, candidate_id, idempotency_key, json.dumps(slot), created),
            )
            self._audit(db, event_id, candidate_id, "CALENDAR_CONFIRMED", booking_id, slot)
        return {
            "booking_id": booking_id,
            "event_id": event_id,
            "candidate_id": candidate_id,
            "idempotency_key": idempotency_key,
            "slot": slot,
            "status": "CONFIRMED_SIMULATED",
            "mode": "SIMULATED",
            "created_at": created,
        }

    async def cancel_booking(self, event_id: str, candidate_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM guest_bookings WHERE event_id = ? AND candidate_id = ? AND status = 'CONFIRMED_SIMULATED' ORDER BY created_at DESC LIMIT 1",
                (event_id, candidate_id),
            ).fetchone()
            if not row:
                return None
            cancelled = _now()
            db.execute(
                "UPDATE guest_bookings SET status = 'CANCELLED', cancelled_at = ? WHERE booking_id = ?",
                (cancelled, row["booking_id"]),
            )
            self._audit(db, event_id, candidate_id, "BOOKING_CANCELLED", row["booking_id"], {})
            return dict(row) | {"status": "CANCELLED", "cancelled_at": cancelled}

    def inspect_event(self, event_id: str) -> dict[str, list[dict[str, Any]]]:
        """Read-back endpoint for tests, integration and judge-facing evidence."""
        with self._connect() as db:
            invitations = [dict(row) for row in db.execute("SELECT * FROM guest_invitations WHERE event_id = ?", (event_id,))]
            bookings = [dict(row) for row in db.execute("SELECT * FROM guest_bookings WHERE event_id = ?", (event_id,))]
            audits = [dict(row) for row in db.execute("SELECT * FROM guest_audit WHERE event_id = ?", (event_id,))]
        return {"invitations": invitations, "bookings": bookings, "audit": audits}

    @staticmethod
    def _audit(
        db: sqlite3.Connection,
        event_id: str,
        candidate_id: str | None,
        action: str,
        reference_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        created = _now()
        audit_id = _stable("audit", event_id, candidate_id or "", action, reference_id or "")
        db.execute(
            "INSERT OR IGNORE INTO guest_audit VALUES (?, ?, ?, ?, ?, ?, ?)",
            (audit_id, event_id, candidate_id, action, reference_id, json.dumps(payload), created),
        )


__all__ = ["SimulatedGuestChannel"]
