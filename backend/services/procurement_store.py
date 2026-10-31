"""Transaction-safe SQLite persistence layer for vendor procurement, holds, orders, and audits.
Implements idempotency, atomic locks, and strict budget/capacity accounting.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from backend.schemas import AuditEvent, Issue, VendorOffer, VendorOrder


class ProcurementStore:
    """Thread-safe SQLite store for procurement state."""

    _instances: Dict[str, "ProcurementStore"] = {}
    _lock = threading.Lock()

    def __init__(self, db_path: str = "eventops.db"):
        self.db_path = db_path
        self._tx_lock = threading.Lock()
        self._init_db()

    @classmethod
    def get_instance(cls, db_path: str = "eventops.db") -> "ProcurementStore":
        with cls._lock:
            if db_path not in cls._instances:
                cls._instances[db_path] = cls(db_path=db_path)
            return cls._instances[db_path]

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        if self.db_path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    def _init_db(self) -> None:
        """Create tables if they do not exist."""
        with self._tx_lock:
            conn = self._get_connection()
            try:
                with conn:
                    # Event registry
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS procurement_events (
                            event_id TEXT PRIMARY KEY,
                            budget_inr INTEGER NOT NULL,
                            expected_attendance INTEGER NOT NULL,
                            venue_capacity INTEGER NOT NULL,
                            starts_at TEXT,
                            ends_at TEXT,
                            brief_json TEXT,
                            created_at TEXT NOT NULL
                        );
                    """)

                    # Offers table
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS procurement_offers (
                            id TEXT PRIMARY KEY,
                            event_id TEXT NOT NULL,
                            vendor_id TEXT NOT NULL,
                            service TEXT NOT NULL,
                            quantity INTEGER NOT NULL,
                            capacity INTEGER NOT NULL,
                            total_price_inr INTEGER NOT NULL,
                            delivery_by TEXT NOT NULL,
                            hold_expires_at TEXT,
                            dietary_tags TEXT NOT NULL,
                            status TEXT NOT NULL,
                            mode TEXT NOT NULL DEFAULT 'SIMULATED',
                            created_at TEXT NOT NULL
                        );
                    """)

                    # Holds table with unique idempotency_key
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS procurement_holds (
                            id TEXT PRIMARY KEY,
                            event_id TEXT NOT NULL,
                            offer_id TEXT NOT NULL,
                            idempotency_key TEXT UNIQUE NOT NULL,
                            expires_at TEXT NOT NULL,
                            hold_liability_inr INTEGER NOT NULL DEFAULT 0,
                            status TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            FOREIGN KEY (offer_id) REFERENCES procurement_offers(id)
                        );
                    """)

                    # Orders table with unique idempotency_key
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS procurement_orders (
                            id TEXT PRIMARY KEY,
                            event_id TEXT NOT NULL,
                            offer_id TEXT NOT NULL,
                            idempotency_key TEXT UNIQUE NOT NULL,
                            status TEXT NOT NULL,
                            committed_inr INTEGER NOT NULL,
                            cancellation_fee_inr INTEGER NOT NULL DEFAULT 0,
                            mode TEXT NOT NULL DEFAULT 'SIMULATED',
                            created_at TEXT NOT NULL,
                            FOREIGN KEY (offer_id) REFERENCES procurement_offers(id)
                        );
                    """)

                    # Issues table
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS procurement_issues (
                            id TEXT PRIMARY KEY,
                            event_id TEXT NOT NULL,
                            type TEXT NOT NULL,
                            severity TEXT NOT NULL,
                            status TEXT NOT NULL,
                            message TEXT NOT NULL,
                            created_at TEXT NOT NULL
                        );
                    """)

                    # Audit events table
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS procurement_audit_events (
                            id TEXT PRIMARY KEY,
                            event_id TEXT NOT NULL,
                            action TEXT NOT NULL,
                            tool TEXT NOT NULL,
                            source_mode TEXT NOT NULL,
                            status TEXT NOT NULL,
                            reason TEXT NOT NULL,
                            references_json TEXT NOT NULL,
                            timestamp TEXT NOT NULL
                        );
                    """)

                    # Indices
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_event ON procurement_orders(event_id);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_holds_event ON procurement_holds(event_id);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_event ON procurement_offers(event_id);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_event ON procurement_issues(event_id);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_event ON procurement_audit_events(event_id, timestamp);")
            finally:
                conn.close()

    # Event Brief Management
    def save_event_brief(
        self,
        event_id: str,
        budget_inr: int,
        expected_attendance: int,
        venue_capacity: int,
        starts_at: Optional[datetime] = None,
        ends_at: Optional[datetime] = None,
        brief_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO procurement_events (
                        event_id, budget_inr, expected_attendance, venue_capacity,
                        starts_at, ends_at, brief_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(event_id) DO UPDATE SET
                        budget_inr = excluded.budget_inr,
                        expected_attendance = excluded.expected_attendance,
                        venue_capacity = excluded.venue_capacity,
                        starts_at = excluded.starts_at,
                        ends_at = excluded.ends_at,
                        brief_json = excluded.brief_json;
                """, (
                    event_id,
                    budget_inr,
                    expected_attendance,
                    venue_capacity,
                    starts_at.isoformat() if starts_at else None,
                    ends_at.isoformat() if ends_at else None,
                    json.dumps(brief_data or {}),
                    datetime.now(timezone.utc).isoformat(),
                ))
        finally:
            conn.close()

    def get_event_brief(self, event_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.execute("SELECT * FROM procurement_events WHERE event_id = ?", (event_id,))
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            if res.get("brief_json"):
                res["brief"] = json.loads(res["brief_json"])
            return res
        finally:
            conn.close()

    # Offer Management
    def save_offer(self, event_id: str, offer: VendorOffer) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO procurement_offers (
                        id, event_id, vendor_id, service, quantity, capacity,
                        total_price_inr, delivery_by, hold_expires_at,
                        dietary_tags, status, mode, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        total_price_inr = excluded.total_price_inr,
                        status = excluded.status,
                        hold_expires_at = excluded.hold_expires_at;
                """, (
                    offer.id,
                    event_id,
                    offer.vendor_id,
                    offer.service,
                    offer.quantity,
                    offer.capacity,
                    offer.total_price_inr,
                    offer.delivery_by.isoformat(),
                    offer.hold_expires_at.isoformat() if offer.hold_expires_at else None,
                    json.dumps(offer.dietary_tags),
                    offer.status,
                    offer.mode,
                    datetime.now(timezone.utc).isoformat(),
                ))
        finally:
            conn.close()

    def get_offer(self, offer_id: str) -> Optional[VendorOffer]:
        conn = self._get_connection()
        try:
            cur = conn.execute("SELECT * FROM procurement_offers WHERE id = ?", (offer_id,))
            row = cur.fetchone()
            if not row:
                return None
            return VendorOffer(
                id=row["id"],
                vendor_id=row["vendor_id"],
                service=row["service"],
                quantity=row["quantity"],
                capacity=row["capacity"],
                total_price_inr=row["total_price_inr"],
                delivery_by=datetime.fromisoformat(row["delivery_by"]),
                hold_expires_at=datetime.fromisoformat(row["hold_expires_at"]) if row["hold_expires_at"] else None,
                dietary_tags=json.loads(row["dietary_tags"]),
                status=row["status"],
                mode=row["mode"],
            )
        finally:
            conn.close()

    def update_offer_status(self, offer_id: str, status: str) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("UPDATE procurement_offers SET status = ? WHERE id = ?", (status, offer_id))
        finally:
            conn.close()

    # Hold Management
    def create_hold(
        self,
        event_id: str,
        offer_id: str,
        idempotency_key: str,
        expires_at: datetime,
        hold_liability_inr: int = 0,
    ) -> Dict[str, Any]:
        """Atomically create a tentative hold with idempotency check."""
        with self._tx_lock:
            conn = self._get_connection()
            try:
                with conn:
                    # Check existing hold with this idempotency key
                    cur = conn.execute(
                        "SELECT * FROM procurement_holds WHERE idempotency_key = ?",
                        (idempotency_key,),
                    )
                    existing = cur.fetchone()
                    if existing:
                        return dict(existing)

                    hold_id = f"hold_{uuid.uuid4().hex[:8]}"
                    created_at = datetime.now(timezone.utc).isoformat()
                    conn.execute("""
                        INSERT INTO procurement_holds (
                            id, event_id, offer_id, idempotency_key, expires_at,
                            hold_liability_inr, status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        hold_id,
                        event_id,
                        offer_id,
                        idempotency_key,
                        expires_at.isoformat(),
                        hold_liability_inr,
                        "HELD",
                        created_at,
                    ))
                    conn.execute(
                        "UPDATE procurement_offers SET status = 'HELD', hold_expires_at = ? WHERE id = ?",
                        (expires_at.isoformat(), offer_id),
                    )
                    return {
                        "id": hold_id,
                        "event_id": event_id,
                        "offer_id": offer_id,
                        "idempotency_key": idempotency_key,
                        "expires_at": expires_at.isoformat(),
                        "hold_liability_inr": hold_liability_inr,
                        "status": "HELD",
                        "created_at": created_at,
                    }
            finally:
                conn.close()

    def get_hold_by_key(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "SELECT * FROM procurement_holds WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_active_holds(self, event_id: str) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "SELECT * FROM procurement_holds WHERE event_id = ? AND status = 'HELD'",
                (event_id,),
            )
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def update_hold_status(self, hold_id: str, status: str) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("UPDATE procurement_holds SET status = ? WHERE id = ?", (status, hold_id))
        finally:
            conn.close()

    # Order Management & Commitments
    def get_order_by_key(self, idempotency_key: str) -> Optional[VendorOrder]:
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "SELECT * FROM procurement_orders WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return VendorOrder(
                id=row["id"],
                event_id=row["event_id"],
                offer_id=row["offer_id"],
                idempotency_key=row["idempotency_key"],
                status=row["status"],
                committed_inr=row["committed_inr"],
                cancellation_fee_inr=row["cancellation_fee_inr"],
                mode=row["mode"],
            )
        finally:
            conn.close()

    def get_order_by_id(self, order_id: str) -> Optional[VendorOrder]:
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "SELECT * FROM procurement_orders WHERE id = ?",
                (order_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return VendorOrder(
                id=row["id"],
                event_id=row["event_id"],
                offer_id=row["offer_id"],
                idempotency_key=row["idempotency_key"],
                status=row["status"],
                committed_inr=row["committed_inr"],
                cancellation_fee_inr=row["cancellation_fee_inr"],
                mode=row["mode"],
            )
        finally:
            conn.close()

    def get_active_orders(self, event_id: str) -> List[VendorOrder]:
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "SELECT * FROM procurement_orders WHERE event_id = ? AND status = 'CONFIRMED_SIMULATED'",
                (event_id,),
            )
            return [
                VendorOrder(
                    id=row["id"],
                    event_id=row["event_id"],
                    offer_id=row["offer_id"],
                    idempotency_key=row["idempotency_key"],
                    status=row["status"],
                    committed_inr=row["committed_inr"],
                    cancellation_fee_inr=row["cancellation_fee_inr"],
                    mode=row["mode"],
                )
                for row in cur.fetchall()
            ]
        finally:
            conn.close()

    def get_all_orders(self, event_id: str) -> List[VendorOrder]:
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "SELECT * FROM procurement_orders WHERE event_id = ?",
                (event_id,),
            )
            return [
                VendorOrder(
                    id=row["id"],
                    event_id=row["event_id"],
                    offer_id=row["offer_id"],
                    idempotency_key=row["idempotency_key"],
                    status=row["status"],
                    committed_inr=row["committed_inr"],
                    cancellation_fee_inr=row["cancellation_fee_inr"],
                    mode=row["mode"],
                )
                for row in cur.fetchall()
            ]
        finally:
            conn.close()

    def calculate_budget_summary(self, event_id: str, total_budget_inr: Optional[int] = None) -> Dict[str, int]:
        """Compute exact financial ledger: total, committed, hold_liability, cancellation_fees, and available."""
        conn = self._get_connection()
        try:
            if total_budget_inr is None:
                cur = conn.execute("SELECT budget_inr FROM procurement_events WHERE event_id = ?", (event_id,))
                row = cur.fetchone()
                total_budget_inr = row["budget_inr"] if row else 0

            # Active orders committed
            cur = conn.execute(
                "SELECT SUM(committed_inr) as active_sum FROM procurement_orders WHERE event_id = ? AND status = 'CONFIRMED_SIMULATED'",
                (event_id,),
            )
            active_sum = cur.fetchone()["active_sum"] or 0

            # Cancellation fees from cancelled orders
            cur = conn.execute(
                "SELECT SUM(cancellation_fee_inr) as fee_sum FROM procurement_orders WHERE event_id = ? AND status = 'CANCELLED'",
                (event_id,),
            )
            fee_sum = cur.fetchone()["fee_sum"] or 0

            # Active hold liabilities
            cur = conn.execute(
                "SELECT SUM(hold_liability_inr) as hold_sum FROM procurement_holds WHERE event_id = ? AND status = 'HELD'",
                (event_id,),
            )
            hold_sum = cur.fetchone()["hold_sum"] or 0

            committed_total = active_sum + fee_sum
            available = total_budget_inr - (committed_total + hold_sum)
            return {
                "total_inr": total_budget_inr,
                "committed_inr": committed_total,
                "active_orders_inr": active_sum,
                "cancellation_fees_inr": fee_sum,
                "hold_liability_inr": hold_sum,
                "available_inr": max(0, available),
            }
        finally:
            conn.close()

    def commit_order_atomic(
        self,
        event_id: str,
        offer_id: str,
        idempotency_key: str,
        total_budget_inr: int,
    ) -> VendorOrder:
        """Atomically commit an order under transaction lock.

        Validates offer, hold expiry, budget ceiling, and checks existing idempotency key.
        """
        with self._tx_lock:
            conn = self._get_connection()
            try:
                with conn:
                    # 1. Idempotency check: if order already exists with this key, return it immediately
                    cur = conn.execute(
                        "SELECT * FROM procurement_orders WHERE idempotency_key = ?",
                        (idempotency_key,),
                    )
                    existing = cur.fetchone()
                    if existing:
                        return VendorOrder(
                            id=existing["id"],
                            event_id=existing["event_id"],
                            offer_id=existing["offer_id"],
                            idempotency_key=existing["idempotency_key"],
                            status=existing["status"],
                            committed_inr=existing["committed_inr"],
                            cancellation_fee_inr=existing["cancellation_fee_inr"],
                            mode=existing["mode"],
                        )

                    # 2. Offer validation
                    cur = conn.execute("SELECT * FROM procurement_offers WHERE id = ?", (offer_id,))
                    offer_row = cur.fetchone()
                    if not offer_row:
                        raise ValueError(f"Offer {offer_id} does not exist.")

                    offer_status = offer_row["status"]
                    if offer_status not in ("AVAILABLE", "HELD"):
                        raise ValueError(f"Offer {offer_id} is not bookable (current status: {offer_status}).")

                    # 3. Expiration validation if held
                    if offer_row["hold_expires_at"]:
                        expires_at = datetime.fromisoformat(offer_row["hold_expires_at"])
                        now_utc = datetime.now(timezone.utc)
                        is_expired = False
                        if expires_at.tzinfo is not None:
                            if expires_at < now_utc:
                                is_expired = True
                        else:
                            if expires_at < datetime.now():
                                is_expired = True
                        if is_expired:
                            conn.execute("UPDATE procurement_offers SET status = 'EXPIRED' WHERE id = ?", (offer_id,))
                            conn.commit()
                            raise ValueError(f"Offer {offer_id} hold has expired at {expires_at.isoformat()}.")

                    cost_inr = offer_row["total_price_inr"]

                    # 4. Budget check
                    cur = conn.execute(
                        "SELECT SUM(committed_inr) as active_sum FROM procurement_orders WHERE event_id = ? AND status = 'CONFIRMED_SIMULATED'",
                        (event_id,),
                    )
                    active_sum = cur.fetchone()["active_sum"] or 0

                    cur = conn.execute(
                        "SELECT SUM(cancellation_fee_inr) as fee_sum FROM procurement_orders WHERE event_id = ? AND status = 'CANCELLED'",
                        (event_id,),
                    )
                    fee_sum = cur.fetchone()["fee_sum"] or 0

                    cur = conn.execute(
                        "SELECT SUM(hold_liability_inr) as hold_sum FROM procurement_holds WHERE event_id = ? AND status = 'HELD' AND offer_id != ?",
                        (event_id, offer_id),
                    )
                    hold_sum = cur.fetchone()["hold_sum"] or 0

                    if (active_sum + fee_sum + hold_sum + cost_inr) > total_budget_inr:
                        raise ValueError(
                            f"Budget exceeded: current obligations ₹{active_sum + fee_sum + hold_sum} + new order ₹{cost_inr} > total budget ₹{total_budget_inr}"
                        )

                    # 5. Insert order
                    order_id = f"ord_{offer_row['service']}_{uuid.uuid4().hex[:8]}"
                    created_at = datetime.now(timezone.utc).isoformat()
                    conn.execute("""
                        INSERT INTO procurement_orders (
                            id, event_id, offer_id, idempotency_key, status,
                            committed_inr, cancellation_fee_inr, mode, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        order_id,
                        event_id,
                        offer_id,
                        idempotency_key,
                        "CONFIRMED_SIMULATED",
                        cost_inr,
                        0,
                        "SIMULATED",
                        created_at,
                    ))

                    # 6. Mark offer as CONFIRMED
                    conn.execute("UPDATE procurement_offers SET status = 'CONFIRMED' WHERE id = ?", (offer_id,))

                    # 7. Convert hold if associated
                    conn.execute(
                        "UPDATE procurement_holds SET status = 'CONVERTED' WHERE offer_id = ? AND status = 'HELD'",
                        (offer_id,),
                    )

                    return VendorOrder(
                        id=order_id,
                        event_id=event_id,
                        offer_id=offer_id,
                        idempotency_key=idempotency_key,
                        status="CONFIRMED_SIMULATED",
                        committed_inr=cost_inr,
                        cancellation_fee_inr=0,
                        mode="SIMULATED",
                    )
            finally:
                conn.close()

    def cancel_order_atomic(
        self,
        order_id: str,
        cancellation_fee_inr: int = 0,
    ) -> VendorOrder:
        """Mark an order cancelled and record its cancellation liability."""
        with self._tx_lock:
            conn = self._get_connection()
            try:
                with conn:
                    cur = conn.execute("SELECT * FROM procurement_orders WHERE id = ?", (order_id,))
                    row = cur.fetchone()
                    if not row:
                        raise ValueError(f"Order {order_id} does not exist.")

                    conn.execute("""
                        UPDATE procurement_orders
                        SET status = 'CANCELLED',
                            cancellation_fee_inr = ?
                        WHERE id = ?
                    """, (cancellation_fee_inr, order_id))

                    conn.execute("""
                        UPDATE procurement_offers
                        SET status = 'CANCELLED'
                        WHERE id = ?
                    """, (row["offer_id"],))

                    return VendorOrder(
                        id=row["id"],
                        event_id=row["event_id"],
                        offer_id=row["offer_id"],
                        idempotency_key=row["idempotency_key"],
                        status="CANCELLED",
                        committed_inr=row["committed_inr"],
                        cancellation_fee_inr=cancellation_fee_inr,
                        mode="SIMULATED",
                    )
            finally:
                conn.close()

    # Issue Tracking
    def record_issue(self, issue: Issue) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO procurement_issues (
                        id, event_id, type, severity, status, message, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        status = excluded.status,
                        message = excluded.message;
                """, (
                    issue.id,
                    issue.event_id,
                    issue.type,
                    issue.severity,
                    issue.status,
                    issue.message,
                    datetime.now(timezone.utc).isoformat(),
                ))
        finally:
            conn.close()

    def get_issues(self, event_id: str) -> List[Issue]:
        conn = self._get_connection()
        try:
            cur = conn.execute("SELECT * FROM procurement_issues WHERE event_id = ?", (event_id,))
            return [
                Issue(
                    id=row["id"],
                    event_id=row["event_id"],
                    type=row["type"],
                    severity=row["severity"],
                    status=row["status"],
                    message=row["message"],
                )
                for row in cur.fetchall()
            ]
        finally:
            conn.close()

    # Audit Logging
    def record_audit(self, audit: AuditEvent) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO procurement_audit_events (
                        id, event_id, action, tool, source_mode, status,
                        reason, references_json, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    audit.id,
                    audit.event_id,
                    audit.action,
                    audit.tool,
                    audit.source_mode,
                    audit.status,
                    audit.reason,
                    json.dumps(audit.references),
                    audit.timestamp.isoformat(),
                ))
        finally:
            conn.close()

    def get_audit_events(self, event_id: str) -> List[AuditEvent]:
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "SELECT * FROM procurement_audit_events WHERE event_id = ? ORDER BY timestamp ASC",
                (event_id,),
            )
            return [
                AuditEvent(
                    id=row["id"],
                    event_id=row["event_id"],
                    action=row["action"],
                    tool=row["tool"],
                    source_mode=row["source_mode"],
                    status=row["status"],
                    reason=row["reason"],
                    references=json.loads(row["references_json"]),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                )
                for row in cur.fetchall()
            ]
        finally:
            conn.close()
