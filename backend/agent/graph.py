"""LangGraph orchestration for the integrated EventOps service."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any, Awaitable, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.db import EventStore
from backend.schemas import EventBrief, ServiceReadiness
from backend.services.crustdata import CrustdataError
from backend.services.guest import coordinate_event_guests, recover_guest, set_guest_channel
from backend.services.procurement_store import ProcurementStore
from backend.services.vendor import VendorService
from backend.services.verification import EventVerifier
from backend.simulator.guest_simulator import SimulatedGuestChannel
from backend.simulator.vendor_simulator import VendorSimulator

GuestCoordinator = Callable[[str, str, int, dict[str, Any]], Awaitable[dict[str, Any]]]


class WorkflowState(TypedDict, total=False):
    event_id: str
    brief: dict[str, Any]
    plan: dict[str, Any]
    guest_result: dict[str, Any]
    vendor_result: dict[str, Any]
    readiness: dict[str, Any]
    validation_failed: bool


class EventOpsOrchestrator:
    def __init__(
        self,
        *,
        db_path: str | None = None,
        event_store: EventStore | None = None,
        procurement_store: ProcurementStore | None = None,
        guest_channel: SimulatedGuestChannel | None = None,
        vendor_service: VendorService | None = None,
        guest_coordinator: GuestCoordinator = coordinate_event_guests,
    ) -> None:
        self.event_store = event_store or EventStore(db_path)
        shared_path = self.event_store.db_path
        self.procurement_store = procurement_store or ProcurementStore.get_instance(shared_path)
        self.guest_channel = guest_channel or SimulatedGuestChannel(shared_path)
        set_guest_channel(self.guest_channel)
        self.vendor_service = vendor_service or VendorService(
            store=self.procurement_store, simulator=VendorSimulator()
        )
        self.guest_coordinator = guest_coordinator
        self.verifier = EventVerifier(
            self.event_store, self.procurement_store, self.guest_channel
        )
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(WorkflowState)
        builder.add_node("validate", self._validate_node)
        builder.add_node("plan", self._plan_node)
        builder.add_node("guests", self._guest_node)
        builder.add_node("vendors", self._vendor_node)
        builder.add_node("verify", self._verify_node)
        builder.add_node("finalize", self._finalize_node)
        builder.add_edge(START, "validate")
        builder.add_conditional_edges(
            "validate",
            lambda state: "blocked" if state.get("validation_failed") else "valid",
            {"blocked": "verify", "valid": "plan"},
        )
        builder.add_edge("plan", "guests")
        builder.add_edge("guests", "vendors")
        builder.add_edge("vendors", "verify")
        builder.add_edge("verify", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile()

    async def _validate_node(self, state: WorkflowState) -> WorkflowState:
        event = self.event_store.get_event(state["event_id"])
        if not event:
            raise KeyError(state["event_id"])
        brief = EventBrief.model_validate(event["brief"])
        self.event_store.update_event(state["event_id"], status="RUNNING", last_error=None)
        if brief.expected_attendance > brief.venue_capacity:
            message = (
                f"Expected attendance {brief.expected_attendance} exceeds venue capacity "
                f"{brief.venue_capacity}"
            )
            self.event_store.record_issue(
                state["event_id"], "CAPACITY_EXCEEDED", message, status="BLOCKED"
            )
            self.event_store.update_event(state["event_id"], status="BLOCKED", last_error=message)
            return {"brief": brief.model_dump(mode="json"), "validation_failed": True}
        self.event_store.record_audit(
            state["event_id"],
            action="VALIDATE_EVENT",
            tool="pydantic",
            source_mode="SIMULATED",
            status="SUCCESS",
            reason="Event constraints validated",
        )
        return {"brief": brief.model_dump(mode="json"), "validation_failed": False}

    async def _plan_node(self, state: WorkflowState) -> WorkflowState:
        brief = EventBrief.model_validate(state["brief"])
        slots: list[dict[str, str]] = []
        cursor = brief.starts_at + timedelta(minutes=15)
        for _ in range(6):
            end = cursor + timedelta(minutes=45)
            if end > brief.ends_at:
                break
            slots.append(
                {"starts_at": cursor.isoformat(), "ends_at": end.isoformat()}
            )
            cursor = end + timedelta(minutes=15)
        if len(slots) < brief.guest_count:
            message = "Event duration cannot fit the required number of non-overlapping guest sessions"
            self.event_store.record_issue(
                state["event_id"], "SCHEDULE_CONFLICT", message, status="BLOCKED"
            )
            self.event_store.update_event(state["event_id"], status="BLOCKED", last_error=message)
        guest_budget = min(brief.budget_inr, brief.guest_count * 3000)
        plan = {
            "guest_slots": slots,
            "max_honorarium_inr": 3000,
            "guest_budget_inr": guest_budget,
            "vendor_budget_inr": max(0, brief.budget_inr - guest_budget),
            "required_quantities": {
                resource: brief.expected_attendance if resource in {"catering", "seating"} else 1
                for resource in brief.mandatory_resources
            },
        }
        self.event_store.update_event(state["event_id"], plan=plan)
        self.event_store.record_audit(
            state["event_id"],
            action="GENERATE_EVENT_PLAN",
            tool="deterministic_planner",
            source_mode="SIMULATED",
            status="SUCCESS",
            reason="Generated guest slots and resource budget allocation",
        )
        return {"plan": plan}

    async def _guest_node(self, state: WorkflowState) -> WorkflowState:
        event = self.event_store.get_event(state["event_id"])
        if event and event.get("guest_result") is not None:
            return {"guest_result": event["guest_result"]}
        brief = EventBrief.model_validate(state["brief"])
        if brief.guest_count == 0:
            result = {
                "event_id": state["event_id"],
                "confirmed_guests": [],
                "backup_candidates": [],
                "pending_guests": [],
                "issues": [],
                "evidence_ids": [],
                "guest_honorarium_committed_inr": 0,
                "status": "COMPLETE",
            }
        else:
            constraints = {
                "slots": state["plan"]["guest_slots"],
                "max_honorarium_inr": state["plan"]["max_honorarium_inr"],
                "guest_budget_inr": state["plan"]["guest_budget_inr"],
                "max_invitation_attempts": max(3, brief.guest_count * 3),
            }
            try:
                result = await self.guest_coordinator(
                    state["event_id"], brief.topic, brief.guest_count, constraints
                )
            except CrustdataError as exc:
                result = {
                    "event_id": state["event_id"],
                    "confirmed_guests": [],
                    "backup_candidates": [],
                    "pending_guests": [],
                    "issues": [{"type": exc.code, "message": str(exc)}],
                    "evidence_ids": [],
                    "guest_honorarium_committed_inr": 0,
                    "status": "BLOCKED",
                }
        self.event_store.update_event(state["event_id"], guest_result=result)
        if result["status"] != "COMPLETE":
            self.event_store.record_issue(
                state["event_id"],
                "GUEST_COORDINATION_BLOCKED",
                "; ".join(issue.get("message", "Guest unavailable") for issue in result.get("issues", [])),
                status="BLOCKED",
            )
        self.event_store.record_audit(
            state["event_id"],
            action="COORDINATE_GUESTS",
            tool="guest_service",
            source_mode="SIMULATED",
            status="SUCCESS" if result["status"] == "COMPLETE" else "FAILED",
            reason=f"Guest coordination finished with status {result['status']}",
            references=result.get("evidence_ids", []),
        )
        return {"guest_result": result}

    async def _vendor_node(self, state: WorkflowState) -> WorkflowState:
        event = self.event_store.get_event(state["event_id"])
        if event and event.get("vendor_result") is not None:
            return {"vendor_result": event["vendor_result"]}
        brief = EventBrief.model_validate(state["brief"])
        guest_spend = int(state.get("guest_result", {}).get("guest_honorarium_committed_inr", 0))
        vendor_budget = max(0, brief.budget_inr - guest_spend)
        result = await self.vendor_service.procure_event_resources(
            state["event_id"],
            requirements=brief.model_dump(mode="json"),
            budget_inr=vendor_budget,
        )
        self.event_store.update_event(state["event_id"], vendor_result=result)
        self.event_store.record_audit(
            state["event_id"],
            action="PROCURE_RESOURCES",
            tool="vendor_service",
            source_mode="SIMULATED",
            status="SUCCESS" if result["status"] == "COMPLETE" else "FAILED",
            reason=f"Vendor procurement finished with status {result['status']}",
            references=[order["id"] for order in result.get("confirmed_orders", [])],
        )
        return {"vendor_result": result}

    async def _verify_node(self, state: WorkflowState) -> WorkflowState:
        result = self.verifier.verify(state["event_id"])
        return {"readiness": result.model_dump(mode="json")}

    async def _finalize_node(self, state: WorkflowState) -> WorkflowState:
        readiness = ServiceReadiness.model_validate(state["readiness"])
        self.event_store.update_event(state["event_id"], status=readiness.status)
        return state

    async def run_event(self, event_id: str) -> dict[str, Any]:
        set_guest_channel(self.guest_channel)
        try:
            result = await self.graph.ainvoke({"event_id": event_id})
            return result
        except Exception as exc:
            self.event_store.update_event(event_id, status="BLOCKED", last_error=str(exc))
            self.event_store.record_issue(
                event_id, "WORKFLOW_FAILURE", str(exc), status="BLOCKED"
            )
            self.event_store.record_audit(
                event_id,
                action="WORKFLOW_FAILED",
                tool="langgraph",
                source_mode="SIMULATED",
                status="FAILED",
                reason=str(exc),
            )
            raise

    async def simulate_disruption(
        self, event_id: str, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        set_guest_channel(self.guest_channel)
        event = self.event_store.get_event(event_id)
        if not event:
            raise KeyError(event_id)
        key_material = f"{event_id}|{event_type}|{payload}"
        idempotency_key = hashlib.sha256(key_material.encode()).hexdigest()
        disruption, created = self.event_store.begin_disruption(
            event_id, event_type, payload, idempotency_key
        )
        if not created:
            return disruption["result"] or disruption

        self.event_store.update_event(event_id, status="IN_PROGRESS")
        if event_type == "VENDOR_CANCELLED":
            result = await self.vendor_service.recover_vendor(event_id, payload["target_id"])
            current_orders = [
                order.model_dump(mode="json")
                for order in self.procurement_store.get_active_orders(event_id)
            ]
            vendor_result = dict(event.get("vendor_result") or {}) | {
                "confirmed_orders": current_orders,
                "status": "COMPLETE" if result["status"] == "RECOVERED" else "BLOCKED",
                "last_recovery": result,
            }
            self.event_store.update_event(event_id, vendor_result=vendor_result)
        elif event_type == "GUEST_CANCELLED":
            guest_result = dict(event.get("guest_result") or {})
            constraints = {
                "slots": (event.get("plan") or {}).get("guest_slots", []),
                "max_honorarium_inr": (event.get("plan") or {}).get("max_honorarium_inr", 3000),
                "guest_budget_inr": (event.get("plan") or {}).get("guest_budget_inr", 0),
                "topic": event["brief"]["topic"],
                "required_count": event["brief"]["guest_count"],
            }
            backups = [item.get("candidate", item) for item in guest_result.get("backup_candidates", [])]
            result = await recover_guest(
                event_id, payload["target_id"], backups, constraints
            )
            guest_result["confirmed_guests"] = [
                item
                for item in guest_result.get("confirmed_guests", [])
                if item.get("candidate", {}).get("id") != payload["target_id"]
            ]
            if result["status"] == "RECOVERED":
                replacement = result["replacement"]
                guest_result["confirmed_guests"].append(replacement)
                replacement_id = replacement["candidate"]["id"]
                guest_result["backup_candidates"] = [
                    item
                    for item in guest_result.get("backup_candidates", [])
                    if item.get("candidate", item).get("id") != replacement_id
                ]
                evidence = replacement["candidate"].get("evidence", [])
                guest_result["evidence_ids"] = sorted(
                    set(guest_result.get("evidence_ids", []))
                    | {item["source_id"] for item in evidence}
                )
                guest_result["status"] = "COMPLETE"
            else:
                guest_result["status"] = "BLOCKED"
            guest_result["last_recovery"] = result
            self.event_store.update_event(event_id, guest_result=guest_result)
        elif event_type == "ATTENDANCE_CHANGED":
            new_count = int(payload["new_count"])
            result = await self.vendor_service.recalculate_resources(event_id, new_count)
            brief = dict(event["brief"])
            brief["expected_attendance"] = new_count
            current_orders = [
                order.model_dump(mode="json")
                for order in self.procurement_store.get_active_orders(event_id)
            ]
            vendor_result = dict(event.get("vendor_result") or {}) | {
                "confirmed_orders": current_orders,
                "status": "COMPLETE" if result["status"] == "RECALCULATED" else "BLOCKED",
                "last_recalculation": result,
            }
            self.event_store.update_event(
                event_id, brief=brief, vendor_result=vendor_result
            )
        else:
            raise ValueError(f"Unsupported disruption type {event_type}")

        recovered = result["status"] in {"RECOVERED", "RECALCULATED"}
        issue_id = self.event_store.record_issue(
            event_id,
            event_type,
            result.get("reason") or result.get("message") or f"{event_type} handled",
            status="RESOLVED" if recovered else "BLOCKED",
        )
        readiness = self.verifier.verify(event_id)
        final_status = readiness.status
        self.event_store.update_event(event_id, status=final_status)
        response = {
            "issue_id": issue_id,
            "event_id": event_id,
            "recovery": result,
            "readiness": readiness.model_dump(mode="json"),
            "status": final_status,
        }
        self.event_store.finish_disruption(disruption["id"], final_status, response)
        self.event_store.record_audit(
            event_id,
            action=event_type,
            tool="recovery_router",
            source_mode="SIMULATED",
            status="SUCCESS" if recovered else "FAILED",
            reason=f"Recovery completed with readiness {final_status}",
            references=[issue_id],
        )
        return response

    def get_event_state(self, event_id: str) -> dict[str, Any] | None:
        event = self.event_store.get_event(event_id)
        if not event:
            return None
        guest_state = self.guest_channel.inspect_event(event_id)
        guest_bookings = []
        for row in guest_state["bookings"]:
            value = dict(row)
            value["slot"] = json.loads(value.pop("slot_json"))
            guest_bookings.append(value)
        orders = [
            order.model_dump(mode="json")
            for order in self.procurement_store.get_all_orders(event_id)
        ]
        total = int(event["brief"]["budget_inr"])
        vendor_ledger = self.procurement_store.calculate_budget_summary(
            event_id, total_budget_inr=total
        )
        guest_committed = sum(
            int(item["slot"].get("honorarium_inr", 0))
            for item in guest_bookings
            if item["status"] == "CONFIRMED_SIMULATED"
        )
        budget = dict(vendor_ledger) | {
            "guest_committed_inr": guest_committed,
            "available_inr": max(
                0,
                total
                - vendor_ledger["committed_inr"]
                - vendor_ledger["hold_liability_inr"]
                - guest_committed,
            ),
        }
        return {
            "event_id": event_id,
            "run_id": event["run_id"],
            "status": event["status"],
            "brief": event["brief"],
            "plan": event["plan"],
            "guest_coordination": event["guest_result"],
            "vendor_procurement": event["vendor_result"],
            "guest_bookings": guest_bookings,
            "orders": orders,
            "budget": budget,
            "readiness": event["readiness"],
            "issues": self.event_store.get_issues(event_id)
            + [issue.model_dump(mode="json") for issue in self.procurement_store.get_issues(event_id)],
            "last_error": event["last_error"],
            "simulation_mode": True,
        }

    def get_timeline(self, event_id: str, after_id: str | None = None) -> list[dict[str, Any]]:
        if not self.event_store.event_exists(event_id):
            raise KeyError(event_id)
        items = [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "action": row["action"],
                "tool": row["tool"],
                "source_mode": row["source_mode"],
                "status": row["status"],
                "reason": row["reason"],
                "references": row["references"],
            }
            for row in self.event_store.get_audit(event_id)
        ]
        items.extend(
            {
                "id": item.id,
                "timestamp": item.timestamp.isoformat(),
                "action": item.action,
                "tool": item.tool,
                "source_mode": item.source_mode,
                "status": item.status,
                "reason": item.reason,
                "references": item.references,
            }
            for item in self.procurement_store.get_audit_events(event_id)
        )
        items.extend(
            {
                "id": row["audit_id"],
                "timestamp": row["created_at"],
                "action": row["action"],
                "tool": "guest_simulator",
                "source_mode": "SIMULATED",
                "status": "SUCCESS",
                "reason": row["action"],
                "references": [row["reference_id"]] if row["reference_id"] else [],
            }
            for row in self.guest_channel.inspect_event(event_id)["audit"]
        )
        items.sort(key=lambda item: (item["timestamp"], item["id"]))
        if after_id:
            positions = [index for index, item in enumerate(items) if item["id"] == after_id]
            if positions:
                items = items[positions[-1] + 1 :]
        return items


__all__ = ["EventOpsOrchestrator", "WorkflowState"]
