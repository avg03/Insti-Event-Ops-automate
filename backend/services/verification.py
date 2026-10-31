"""Independent deterministic readiness verification over persisted records."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from backend.db import EventStore
from backend.schemas import ServiceReadiness
from backend.services.procurement_store import ProcurementStore
from backend.simulator.guest_simulator import SimulatedGuestChannel


def _parse_time(value: str | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _overlap(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return _parse_time(first["starts_at"]) < _parse_time(second["ends_at"]) and _parse_time(
        second["starts_at"]
    ) < _parse_time(first["ends_at"])


class EventVerifier:
    def __init__(
        self,
        event_store: EventStore,
        procurement_store: ProcurementStore,
        guest_channel: SimulatedGuestChannel,
    ) -> None:
        self.event_store = event_store
        self.procurement_store = procurement_store
        self.guest_channel = guest_channel

    def verify(self, event_id: str) -> ServiceReadiness:
        event = self.event_store.get_event(event_id)
        if not event:
            raise KeyError(event_id)
        brief = event["brief"]
        guest_state = self.guest_channel.inspect_event(event_id)
        active_guest_rows = [
            row for row in guest_state["bookings"] if row["status"] == "CONFIRMED_SIMULATED"
        ]
        guest_slots = [json.loads(row["slot_json"]) for row in active_guest_rows]
        active_orders = self.procurement_store.get_active_orders(event_id)
        offers = [self.procurement_store.get_offer(order.offer_id) for order in active_orders]
        offers = [offer for offer in offers if offer is not None]

        required_guests = int(brief.get("guest_count", 0))
        expected_attendance = int(brief["expected_attendance"])
        venue_capacity = int(brief["venue_capacity"])
        mandatory_resources = list(brief.get("mandatory_resources", []))
        event_start = _parse_time(brief["starts_at"])

        no_guest_conflicts = all(
            not _overlap(guest_slots[i], guest_slots[j])
            for i in range(len(guest_slots))
            for j in range(i + 1, len(guest_slots))
        )
        services = {offer.service for offer in offers}
        resource_orders_confirmed = all(resource in services for resource in mandatory_resources)
        resource_quantities_cover = True
        deliveries_on_time = True
        for resource in mandatory_resources:
            matching = [offer for offer in offers if offer.service == resource]
            if not matching:
                resource_quantities_cover = False
                deliveries_on_time = False
                continue
            required_quantity = expected_attendance if resource in {"catering", "seating"} else 1
            if not any(
                offer.quantity >= required_quantity and offer.capacity >= expected_attendance
                for offer in matching
            ):
                resource_quantities_cover = False
            if not all(offer.delivery_by <= event_start for offer in matching):
                deliveries_on_time = False

        vendor_ledger = self.procurement_store.calculate_budget_summary(
            event_id, total_budget_inr=int(brief["budget_inr"])
        )
        guest_commitment = sum(int(slot.get("honorarium_inr", 0)) for slot in guest_slots)
        total_commitment = (
            vendor_ledger["committed_inr"]
            + vendor_ledger["hold_liability_inr"]
            + guest_commitment
        )
        integration_issues = self.event_store.get_issues(event_id)
        procurement_issues = self.procurement_store.get_issues(event_id)
        unresolved_critical = [
            issue
            for issue in integration_issues
            if issue["severity"] == "CRITICAL" and issue["status"] in {"OPEN", "RECOVERING", "BLOCKED"}
        ] + [
            issue.model_dump()
            for issue in procurement_issues
            if issue.severity == "CRITICAL" and issue.status in {"OPEN", "RECOVERING", "BLOCKED"}
        ]
        evidence_ids = sorted(set((event.get("guest_result") or {}).get("evidence_ids", [])))
        identity_evidence = required_guests == 0 or len(evidence_ids) >= required_guests

        checks = {
            "required_guests_confirmed": len(active_guest_rows) >= required_guests,
            "guest_schedules_non_conflicting": no_guest_conflicts,
            "guest_identity_evidence_present": identity_evidence,
            "required_vendor_orders_confirmed": resource_orders_confirmed,
            "resource_quantities_cover_attendance": resource_quantities_cover,
            "vendor_deliveries_on_time": deliveries_on_time,
            "budget_within_limit": total_commitment <= int(brief["budget_inr"]),
            "venue_capacity_respected": expected_attendance <= venue_capacity,
            "no_unresolved_critical_issues": not unresolved_critical,
        }
        blockers = [name for name, passed in checks.items() if not passed]
        workflow_incomplete = event.get("guest_result") is None or event.get("vendor_result") is None
        if workflow_incomplete and event["status"] not in {"BLOCKED", "FAILED"}:
            status = "IN_PROGRESS"
        elif blockers:
            status = "BLOCKED"
        else:
            status = "READY"
        result = ServiceReadiness(
            event_id=event_id,
            status=status,
            checks=checks,
            blockers=blockers,
            evidence_ids=evidence_ids,
            checked_at=datetime.now(timezone.utc),
        )
        self.event_store.update_event(event_id, readiness=result.model_dump(mode="json"))
        self.event_store.record_audit(
            event_id,
            action="VERIFY_EVENT",
            tool="deterministic_verifier",
            source_mode="SIMULATED",
            status="SUCCESS" if status == "READY" else "FAILED",
            reason=("All readiness checks passed" if status == "READY" else ", ".join(blockers) or "Workflow incomplete"),
            references=evidence_ids,
        )
        return result


def verify_event(
    event_id: str,
    *,
    event_store: EventStore,
    procurement_store: ProcurementStore,
    guest_channel: SimulatedGuestChannel,
) -> ServiceReadiness:
    return EventVerifier(event_store, procurement_store, guest_channel).verify(event_id)


__all__ = ["EventVerifier", "verify_event"]
