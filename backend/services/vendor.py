"""Vendor Procurement Subsystem.
Implements quotation retrieval, idempotent holds/bookings, budget optimization,
automatic cancellation recovery, bounded negotiation, and attendance recalculation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.schemas import AuditEvent, Issue, VendorOffer, VendorOrder
from backend.services.optimizer import ResourceOptimizer
from backend.services.procurement_store import ProcurementStore
from backend.simulator.vendor_simulator import IST, VendorSimulator


class VendorService:
    """Service governing vendor operations, financial accounting, and recovery workflows."""

    def __init__(
        self,
        store: Optional[ProcurementStore] = None,
        simulator: Optional[VendorSimulator] = None,
        optimizer: Optional[ResourceOptimizer] = None,
    ):
        self.store = store or ProcurementStore.get_instance()
        self.simulator = simulator or VendorSimulator()
        self.optimizer = optimizer or ResourceOptimizer()

    async def get_vendor_quotes(
        self,
        event_id: str,
        service: str,
        quantity: int,
        delivery_deadline: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> List[VendorOffer]:
        """Retrieve quotations from simulated suppliers and persist them in authoritative store."""
        quotes = self.simulator.get_quotes(
            event_id=event_id,
            service=service,
            quantity=quantity,
            event_starts_at=delivery_deadline,
            now=now,
        )
        for q in quotes:
            self.store.save_offer(event_id=event_id, offer=q)

        # Audit quote retrieval
        audit = AuditEvent(
            id=f"aud_quote_{uuid.uuid4().hex[:8]}",
            event_id=event_id,
            action="GET_VENDOR_QUOTES",
            tool="vendor_simulator.get_quotes",
            source_mode="SIMULATED",
            status="SUCCESS",
            reason=f"Retrieved {len(quotes)} simulated quotations for service '{service}' (quantity: {quantity})",
            references=[q.id for q in quotes],
            timestamp=datetime.now(timezone.utc),
        )
        self.store.record_audit(audit)
        return quotes

    async def hold_vendor_offer(
        self,
        event_id: str,
        offer_id: str,
        idempotency_key: str,
    ) -> Dict[str, Any]:
        """Reserve a tentative hold on a vendor offer with idempotency and expiry tracking."""
        offer = self.store.get_offer(offer_id)
        if not offer:
            raise ValueError(f"Offer {offer_id} not found.")

        # Check existing hold
        existing_hold = self.store.get_hold_by_key(idempotency_key)
        if existing_hold:
            return existing_hold

        expires_at = offer.hold_expires_at
        if expires_at is None:
            expires_at = datetime.now(timezone.utc)

        vendor = self.simulator.get_vendor(offer.vendor_id) or {}
        hold_liability = vendor.get("reliability_metadata", {}).get("hold_liability_inr", 0)

        hold_receipt = self.store.create_hold(
            event_id=event_id,
            offer_id=offer_id,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            hold_liability_inr=hold_liability,
        )

        audit = AuditEvent(
            id=f"aud_hold_{uuid.uuid4().hex[:8]}",
            event_id=event_id,
            action="HOLD_VENDOR_OFFER",
            tool="vendor_simulator.hold",
            source_mode="SIMULATED",
            status="SUCCESS",
            reason=f"Held offer {offer_id} tentatively until {expires_at.isoformat()}",
            references=[offer_id, hold_receipt["id"]],
            timestamp=datetime.now(timezone.utc),
        )
        self.store.record_audit(audit)
        return hold_receipt

    async def commit_vendor_order(
        self,
        event_id: str,
        offer_id: str,
        idempotency_key: str,
        total_budget_inr: Optional[int] = None,
    ) -> VendorOrder:
        """Atomically commit a sandbox vendor order.

        Enforces budget, checks existing idempotency key, validates hold expiry, and persists order.
        """
        if total_budget_inr is None:
            brief = self.store.get_event_brief(event_id)
            if brief:
                total_budget_inr = brief["budget_inr"]
            else:
                total_budget_inr = 1_000_000_000  # Default unconstrained if not registered

        order = self.store.commit_order_atomic(
            event_id=event_id,
            offer_id=offer_id,
            idempotency_key=idempotency_key,
            total_budget_inr=total_budget_inr,
        )

        audit = AuditEvent(
            id=f"aud_order_{uuid.uuid4().hex[:8]}",
            event_id=event_id,
            action="COMMIT_VENDOR_ORDER",
            tool="vendor_service.commit_order",
            source_mode="SIMULATED",
            status="SUCCESS",
            reason=f"Committed sandbox order {order.id} for offer {offer_id} (cost: ₹{order.committed_inr})",
            references=[order.id, offer_id, idempotency_key],
            timestamp=datetime.now(timezone.utc),
        )
        self.store.record_audit(audit)
        return order

    async def negotiate_vendor_quote(
        self,
        event_id: str,
        offer_id: str,
        target_budget_inr: int,
        round_number: int = 1,
    ) -> Dict[str, Any]:
        """Execute bounded deterministic negotiation through the simulator."""
        result = self.simulator.negotiate(
            offer_id=offer_id,
            target_price_inr=target_budget_inr,
            round_number=round_number,
        )
        # Update offer in store if modified
        updated_offer = self.simulator.offers.get(offer_id)
        if updated_offer:
            self.store.save_offer(event_id=event_id, offer=updated_offer)

        audit = AuditEvent(
            id=f"aud_neg_{uuid.uuid4().hex[:8]}",
            event_id=event_id,
            action="NEGOTIATE_VENDOR_QUOTE",
            tool="vendor_simulator.negotiate",
            source_mode="SIMULATED",
            status="SUCCESS" if result["status"] in ("ACCEPTED", "COUNTEROFFER") else "SKIPPED",
            reason=f"Negotiation round {round_number} result: {result['status']} ({result.get('reason')})",
            references=[offer_id],
            timestamp=datetime.now(timezone.utc),
        )
        self.store.record_audit(audit)
        return result

    async def procure_event_resources(
        self,
        event_id: str,
        requirements: Dict[str, Any],
        budget_inr: int,
    ) -> Dict[str, Any]:
        """High-level autonomous vendor procurement orchestration.

        Understands required quantities, retrieves quotes, optimizes combinations,
        reserves backup holds, and confirms primary sandbox orders.
        """
        attendance = int(requirements.get("expected_attendance", 120))
        venue_capacity = int(requirements.get("venue_capacity", 150))
        mandatory_resources = list(requirements.get("mandatory_resources", ["catering", "av"]))
        dietary_requirements = list(requirements.get("dietary_requirements", []))

        delivery_deadline = requirements.get("starts_at")
        if isinstance(delivery_deadline, str):
            delivery_deadline = datetime.fromisoformat(delivery_deadline)

        # 1. Capacity boundary check
        if attendance > venue_capacity:
            issue_msg = (
                f"Requested attendance {attendance} exceeds venue capacity {venue_capacity}."
            )
            issue = Issue(
                id=f"iss_cap_{uuid.uuid4().hex[:8]}",
                event_id=event_id,
                type="CAPACITY_EXCEEDED",
                severity="CRITICAL",
                status="BLOCKED",
                message=issue_msg,
            )
            self.store.record_issue(issue)
            self.store.save_event_brief(
                event_id=event_id,
                budget_inr=budget_inr,
                expected_attendance=attendance,
                venue_capacity=venue_capacity,
                starts_at=delivery_deadline,
                brief_data=requirements,
            )
            audit = AuditEvent(
                id=f"aud_cap_{uuid.uuid4().hex[:8]}",
                event_id=event_id,
                action="PROCURE_EVENT_RESOURCES",
                tool="procure_event_resources",
                source_mode="SIMULATED",
                status="FAILED",
                reason=issue_msg,
                references=[issue.id],
                timestamp=datetime.now(timezone.utc),
            )
            self.store.record_audit(audit)
            return {
                "event_id": event_id,
                "confirmed_orders": [],
                "backup_holds": [],
                "committed_inr": 0,
                "available_inr": budget_inr,
                "issues": [issue.model_dump()],
                "status": "BLOCKED",
                "reason": issue_msg,
            }

        # Save brief
        self.store.save_event_brief(
            event_id=event_id,
            budget_inr=budget_inr,
            expected_attendance=attendance,
            venue_capacity=venue_capacity,
            starts_at=delivery_deadline,
            brief_data=requirements,
        )

        # 2. Determine quantities per category
        required_quantities: Dict[str, int] = {}
        for resource in mandatory_resources:
            if resource == "catering":
                required_quantities[resource] = attendance
            elif resource == "seating":
                required_quantities[resource] = attendance
            elif resource == "av":
                required_quantities[resource] = 1
            else:
                required_quantities[resource] = int(requirements.get(f"{resource}_quantity", 1))

        # 3. Retrieve supplier quotations
        candidate_offers_by_service: Dict[str, List[VendorOffer]] = {}
        for resource in mandatory_resources:
            quotes = await self.get_vendor_quotes(
                event_id=event_id,
                service=resource,
                quantity=required_quantities[resource],
                delivery_deadline=delivery_deadline,
            )
            candidate_offers_by_service[resource] = quotes

        # Current committed ledger
        ledger = self.store.calculate_budget_summary(event_id, total_budget_inr=budget_inr)
        committed_cost_inr = ledger["committed_inr"]
        hold_liability_inr = ledger["hold_liability_inr"]

        # 4. Deterministic optimization
        opt_result = self.optimizer.optimize(
            event_id=event_id,
            mandatory_resources=mandatory_resources,
            required_quantities=required_quantities,
            total_budget_inr=budget_inr,
            committed_cost_inr=committed_cost_inr,
            hold_liability_inr=hold_liability_inr,
            candidate_offers_by_service=candidate_offers_by_service,
            delivery_deadline=delivery_deadline,
            dietary_requirements=dietary_requirements,
            include_backup=True,
        )

        # 5. Handle optimization failure with bounded negotiation if applicable
        if not opt_result["constraints_satisfied"]:
            # Check if attempting negotiation can close the gap
            negotiated_any = False
            for service, offers in candidate_offers_by_service.items():
                for off in offers:
                    # Attempt a discount negotiation toward target floor
                    neg_res = await self.negotiate_vendor_quote(
                        event_id=event_id,
                        offer_id=off.id,
                        target_budget_inr=int(off.total_price_inr * 0.9),
                        round_number=1,
                    )
                    if neg_res["status"] in ("ACCEPTED", "COUNTEROFFER"):
                        negotiated_any = True

            if negotiated_any:
                # Re-run optimizer with updated negotiated rates
                opt_result = self.optimizer.optimize(
                    event_id=event_id,
                    mandatory_resources=mandatory_resources,
                    required_quantities=required_quantities,
                    total_budget_inr=budget_inr,
                    committed_cost_inr=committed_cost_inr,
                    hold_liability_inr=hold_liability_inr,
                    candidate_offers_by_service=candidate_offers_by_service,
                    delivery_deadline=delivery_deadline,
                    dietary_requirements=dietary_requirements,
                    include_backup=True,
                )

        if not opt_result["constraints_satisfied"]:
            issue = Issue(
                id=f"iss_opt_{uuid.uuid4().hex[:8]}",
                event_id=event_id,
                type="BUDGET_EXCEEDED" if "budget" in opt_result["reason"].lower() else "TOOL_FAILURE",
                severity="CRITICAL",
                status="BLOCKED",
                message=opt_result["reason"],
            )
            self.store.record_issue(issue)
            return {
                "event_id": event_id,
                "confirmed_orders": [],
                "backup_holds": [],
                "committed_inr": committed_cost_inr,
                "available_inr": ledger["available_inr"],
                "issues": [issue.model_dump()],
                "status": "BLOCKED",
                "reason": opt_result["reason"],
            }

        # 6. Commit primary vendor orders
        confirmed_orders: List[VendorOrder] = []
        for offer in opt_result["selected_offers"]:
            idempotency_key = f"{event_id}_order_{offer.service}_{offer.id}"
            order = await self.commit_vendor_order(
                event_id=event_id,
                offer_id=offer.id,
                idempotency_key=idempotency_key,
                total_budget_inr=budget_inr,
            )
            confirmed_orders.append(order)

        # 7. Reserve backup vendor holds
        backup_holds: List[Dict[str, Any]] = []
        for b_offer in opt_result["backup_offers"]:
            idempotency_key = f"{event_id}_hold_{b_offer.service}_{b_offer.id}"
            hold = await self.hold_vendor_offer(
                event_id=event_id,
                offer_id=b_offer.id,
                idempotency_key=idempotency_key,
            )
            backup_holds.append(hold)

        final_ledger = self.store.calculate_budget_summary(event_id, total_budget_inr=budget_inr)

        return {
            "event_id": event_id,
            "confirmed_orders": [o.model_dump() for o in confirmed_orders],
            "backup_holds": backup_holds,
            "committed_inr": final_ledger["committed_inr"],
            "available_inr": final_ledger["available_inr"],
            "issues": [],
            "status": "COMPLETE",
        }

    async def recover_vendor(
        self,
        event_id: str,
        failed_order_id: str,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Automatic cancellation recovery workflow.

        1. Validates failed order.
        2. Marks it cancelled and calculates cancellation liability.
        3. Checks reserved backup holds.
        4. Rejects expired or unfit backup holds.
        5. Commits replacement order or searches marketplace.
        6. Recomputes budget and returns structured recovery evidence.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        order = self.store.get_order_by_id(failed_order_id)
        if not order:
            return {
                "event_id": event_id,
                "status": "BLOCKED",
                "reason": f"Order {failed_order_id} not found in database.",
            }

        brief = self.store.get_event_brief(event_id) or {}
        total_budget_inr = brief.get("budget_inr", 1_000_000_000)
        starts_at = datetime.fromisoformat(brief["starts_at"]) if brief.get("starts_at") else None
        attendance = brief.get("expected_attendance", 120)
        dietary_reqs = brief.get("brief", {}).get("dietary_requirements", [])

        failed_offer = self.store.get_offer(order.offer_id)
        if not failed_offer:
            return {
                "event_id": event_id,
                "status": "BLOCKED",
                "reason": f"Original offer {order.offer_id} for order {failed_order_id} not found.",
            }

        service_category = failed_offer.service

        # Calculate cancellation fee per supplier policy
        cancellation_fee = self.simulator.calculate_cancellation_fee(
            vendor_id=failed_offer.vendor_id,
            committed_inr=order.committed_inr,
        )

        # Atomically mark failed order cancelled with cancellation fee
        cancelled_order = self.store.cancel_order_atomic(
            order_id=failed_order_id,
            cancellation_fee_inr=cancellation_fee,
        )

        issue = Issue(
            id=f"iss_canc_{uuid.uuid4().hex[:8]}",
            event_id=event_id,
            type="VENDOR_CANCELLED",
            severity="CRITICAL",
            status="RECOVERING",
            message=f"Vendor {failed_offer.vendor_id} cancelled order {failed_order_id} for service '{service_category}'. Initiating recovery.",
        )
        self.store.record_issue(issue)

        # Check existing backup holds for this event and service
        active_holds = self.store.get_active_holds(event_id)
        candidate_backup_order: Optional[VendorOrder] = None
        recovery_source: str = ""

        for hold in active_holds:
            hold_offer = self.store.get_offer(hold["offer_id"])
            if not hold_offer or hold_offer.service != service_category:
                continue

            # Check hold expiry
            expires_at = datetime.fromisoformat(hold["expires_at"])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            if expires_at < now:
                # Hold is expired
                self.store.update_hold_status(hold["id"], "EXPIRED")
                self.store.update_offer_status(hold_offer.id, "EXPIRED")
                continue

            # Check capacity, deadline, dietary
            if hold_offer.capacity < attendance:
                continue
            if starts_at and hold_offer.delivery_by > starts_at:
                continue
            if service_category == "catering" and dietary_reqs:
                tags = set(t.lower() for t in hold_offer.dietary_tags)
                if any(d.lower() not in tags for d in dietary_reqs):
                    continue

            # Check budget feasibility
            budget_summary = self.store.calculate_budget_summary(event_id, total_budget_inr=total_budget_inr)
            if hold_offer.total_price_inr > budget_summary["available_inr"]:
                continue

            # Valid backup found! Commit backup
            backup_key = f"recovery_{failed_order_id}_{hold_offer.id}"
            try:
                candidate_backup_order = await self.commit_vendor_order(
                    event_id=event_id,
                    offer_id=hold_offer.id,
                    idempotency_key=backup_key,
                    total_budget_inr=total_budget_inr,
                )
                self.store.update_hold_status(hold["id"], "CONVERTED")
                recovery_source = "BACKUP_HOLD"
                break
            except Exception:
                continue

        # If backup hold was not committed, search alternative marketplace vendors
        if not candidate_backup_order:
            fresh_quotes = await self.get_vendor_quotes(
                event_id=event_id,
                service=service_category,
                quantity=attendance if service_category in ("catering", "seating") else 1,
                delivery_deadline=starts_at,
                now=now,
            )
            # Filter out cancelled vendor
            valid_alternates = [q for q in fresh_quotes if q.vendor_id != failed_offer.vendor_id]
            valid_offers, _ = self.optimizer.filter_offers_for_service(
                service=service_category,
                offers=valid_alternates,
                required_quantity=attendance if service_category in ("catering", "seating") else 1,
                delivery_deadline=starts_at,
                dietary_requirements=dietary_reqs,
            )

            # Sort by total price
            valid_offers.sort(key=lambda o: o.total_price_inr)

            for alt_offer in valid_offers:
                budget_summary = self.store.calculate_budget_summary(event_id, total_budget_inr=total_budget_inr)
                if alt_offer.total_price_inr <= budget_summary["available_inr"]:
                    alt_key = f"recovery_alt_{failed_order_id}_{alt_offer.id}"
                    try:
                        candidate_backup_order = await self.commit_vendor_order(
                            event_id=event_id,
                            offer_id=alt_offer.id,
                            idempotency_key=alt_key,
                            total_budget_inr=total_budget_inr,
                        )
                        recovery_source = "MARKETPLACE_FALLBACK"
                        break
                    except Exception:
                        continue

        if candidate_backup_order:
            # Resolved
            issue.status = "RESOLVED"
            issue.message = (
                f"Successfully recovered from cancellation of order {failed_order_id}. "
                f"Replacement order {candidate_backup_order.id} confirmed via {recovery_source}."
            )
            self.store.record_issue(issue)

            final_ledger = self.store.calculate_budget_summary(event_id, total_budget_inr=total_budget_inr)
            return {
                "event_id": event_id,
                "failed_order_id": failed_order_id,
                "replacement_order": candidate_backup_order.model_dump(),
                "recovery_source": recovery_source,
                "cancellation_fee_inr": cancellation_fee,
                "committed_inr": final_ledger["committed_inr"],
                "available_inr": final_ledger["available_inr"],
                "status": "RECOVERED",
                "issue_id": issue.id,
            }
        else:
            # Blocked
            issue.status = "BLOCKED"
            issue.message = (
                f"Recovery failed for order {failed_order_id} ({service_category}): "
                "no backup hold or marketplace alternative satisfies capacity, deadline, dietary, or budget limits."
            )
            self.store.record_issue(issue)

            final_ledger = self.store.calculate_budget_summary(event_id, total_budget_inr=total_budget_inr)
            return {
                "event_id": event_id,
                "failed_order_id": failed_order_id,
                "status": "BLOCKED",
                "reason": issue.message,
                "cancellation_fee_inr": cancellation_fee,
                "committed_inr": final_ledger["committed_inr"],
                "available_inr": final_ledger["available_inr"],
                "issue_id": issue.id,
            }

    async def recalculate_resources(
        self,
        event_id: str,
        new_attendance: int,
    ) -> Dict[str, Any]:
        """Attendance scaling and resource recalculation.

        Handles attendance surges or reductions, enforces venue limits, and resizes or replaces orders.
        """
        brief = self.store.get_event_brief(event_id)
        if not brief:
            return {
                "event_id": event_id,
                "status": "BLOCKED",
                "reason": f"Event {event_id} brief not registered.",
            }

        venue_capacity = brief["venue_capacity"]
        total_budget_inr = brief["budget_inr"]
        starts_at = datetime.fromisoformat(brief["starts_at"]) if brief.get("starts_at") else None
        dietary_reqs = brief.get("brief", {}).get("dietary_requirements", [])

        # 1. Hard venue capacity ceiling check
        if new_attendance > venue_capacity:
            issue = Issue(
                id=f"iss_cap_{uuid.uuid4().hex[:8]}",
                event_id=event_id,
                type="CAPACITY_EXCEEDED",
                severity="CRITICAL",
                status="BLOCKED",
                message=f"Attendance increase to {new_attendance} violates venue capacity {venue_capacity}.",
            )
            self.store.record_issue(issue)
            return {
                "event_id": event_id,
                "status": "BLOCKED",
                "reason": "CAPACITY_EXCEEDED",
                "message": issue.message,
                "new_attendance": new_attendance,
                "venue_capacity": venue_capacity,
            }

        # Update event record attendance
        self.store.save_event_brief(
            event_id=event_id,
            budget_inr=total_budget_inr,
            expected_attendance=new_attendance,
            venue_capacity=venue_capacity,
            starts_at=starts_at,
            brief_data=brief.get("brief"),
        )

        active_orders = self.store.get_active_orders(event_id)
        updated_orders: List[Dict[str, Any]] = []

        for order in active_orders:
            offer = self.store.get_offer(order.offer_id)
            if not offer or offer.service not in ("catering", "seating"):
                updated_orders.append(order.model_dump())
                continue

            vendor = self.simulator.get_vendor(offer.vendor_id) or {}
            max_cap = vendor.get("maximum_capacity", offer.capacity)

            if max_cap >= new_attendance:
                # Existing vendor can accommodate new attendance
                # Cancel old order and commit adjusted order with same vendor
                unit_price = vendor.get("price_per_unit", 0)
                delivery_fee = vendor.get("delivery_fee", 0)
                new_total = (unit_price * new_attendance) + delivery_fee

                # Replace offer and order
                new_offer = self.simulator.generate_quote(
                    event_id=event_id,
                    vendor_id=offer.vendor_id,
                    quantity=new_attendance,
                    event_starts_at=starts_at,
                )
                self.store.save_offer(event_id=event_id, offer=new_offer)

                # Cancel previous order without cancellation penalty (vendor resize)
                self.store.cancel_order_atomic(order.id, cancellation_fee_inr=0)

                # Commit new resized order
                new_key = f"resize_{event_id}_{order.id}_{new_attendance}"
                new_order = await self.commit_vendor_order(
                    event_id=event_id,
                    offer_id=new_offer.id,
                    idempotency_key=new_key,
                    total_budget_inr=total_budget_inr,
                )
                updated_orders.append(new_order.model_dump())
            else:
                # Current vendor capacity is exceeded! Must replace with higher capacity provider
                cancellation_fee = self.simulator.calculate_cancellation_fee(
                    vendor_id=offer.vendor_id,
                    committed_inr=order.committed_inr,
                )
                self.store.cancel_order_atomic(order.id, cancellation_fee_inr=cancellation_fee)

                # Fetch quotes for new attendance
                quotes = await self.get_vendor_quotes(
                    event_id=event_id,
                    service=offer.service,
                    quantity=new_attendance,
                    delivery_deadline=starts_at,
                )
                valid_offers, _ = self.optimizer.filter_offers_for_service(
                    service=offer.service,
                    offers=quotes,
                    required_quantity=new_attendance,
                    delivery_deadline=starts_at,
                    dietary_requirements=dietary_reqs,
                )
                valid_offers.sort(key=lambda o: o.total_price_inr)

                if not valid_offers:
                    issue = Issue(
                        id=f"iss_scale_{uuid.uuid4().hex[:8]}",
                        event_id=event_id,
                        type="CAPACITY_EXCEEDED",
                        severity="CRITICAL",
                        status="BLOCKED",
                        message=f"No provider can support scaled attendance of {new_attendance} for '{offer.service}'.",
                    )
                    self.store.record_issue(issue)
                    return {
                        "event_id": event_id,
                        "status": "BLOCKED",
                        "reason": issue.message,
                    }

                replacement_offer = valid_offers[0]
                rep_key = f"scale_rep_{event_id}_{order.id}_{new_attendance}"
                new_order = await self.commit_vendor_order(
                    event_id=event_id,
                    offer_id=replacement_offer.id,
                    idempotency_key=rep_key,
                    total_budget_inr=total_budget_inr,
                )
                updated_orders.append(new_order.model_dump())

        final_ledger = self.store.calculate_budget_summary(event_id, total_budget_inr=total_budget_inr)

        return {
            "event_id": event_id,
            "status": "RECALCULATED",
            "new_attendance": new_attendance,
            "updated_orders": updated_orders,
            "committed_inr": final_ledger["committed_inr"],
            "available_inr": final_ledger["available_inr"],
        }


# Global singleton service instance for easy import and invocation
_default_service: Optional[VendorService] = None


def get_vendor_service(db_path: str = "eventops.db") -> VendorService:
    global _default_service
    if _default_service is None or _default_service.store.db_path != db_path:
        store = ProcurementStore.get_instance(db_path=db_path)
        simulator = VendorSimulator()
        optimizer = ResourceOptimizer()
        _default_service = VendorService(store=store, simulator=simulator, optimizer=optimizer)
    return _default_service


# Top-level integration functions matching CONTRACTS.md and task requirements:


async def get_vendor_quotes(
    event_id: str,
    service: str,
    quantity: int,
) -> List[VendorOffer]:
    service_instance = get_vendor_service()
    return await service_instance.get_vendor_quotes(
        event_id=event_id,
        service=service,
        quantity=quantity,
    )


async def hold_vendor_offer(
    event_id: str,
    offer_id: str,
    idempotency_key: str,
) -> Dict[str, Any]:
    service_instance = get_vendor_service()
    return await service_instance.hold_vendor_offer(
        event_id=event_id,
        offer_id=offer_id,
        idempotency_key=idempotency_key,
    )


async def commit_vendor_order(
    event_id: str,
    offer_id: str,
    idempotency_key: str,
) -> VendorOrder:
    service_instance = get_vendor_service()
    return await service_instance.commit_vendor_order(
        event_id=event_id,
        offer_id=offer_id,
        idempotency_key=idempotency_key,
    )


async def procure_event_resources(
    event_id: str,
    requirements: Dict[str, Any],
    budget_inr: int,
) -> Dict[str, Any]:
    service_instance = get_vendor_service()
    return await service_instance.procure_event_resources(
        event_id=event_id,
        requirements=requirements,
        budget_inr=budget_inr,
    )


async def recover_vendor(
    event_id: str,
    failed_order_id: str,
) -> Dict[str, Any]:
    service_instance = get_vendor_service()
    return await service_instance.recover_vendor(
        event_id=event_id,
        failed_order_id=failed_order_id,
    )


async def recalculate_resources(
    event_id: str,
    new_attendance: int,
) -> Dict[str, Any]:
    service_instance = get_vendor_service()
    return await service_instance.recalculate_resources(
        event_id=event_id,
        new_attendance=new_attendance,
    )
