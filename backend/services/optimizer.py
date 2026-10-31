"""Deterministic resource allocation and budget optimization engine.
Evaluates combinatorial allocations across mandatory resource categories subject to
hard constraints (budget, capacity, delivery deadline, dietary rules) and selects
the most economical feasible vendor combination with reserved backups.
"""

from __future__ import annotations

import itertools
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.schemas import VendorOffer


class ResourceOptimizer:
    """Deterministic constraint-based optimizer for event vendor procurement."""

    def __init__(self, reliability_weight: float = 0.0):
        self.reliability_weight = reliability_weight

    def filter_offers_for_service(
        self,
        service: str,
        offers: List[VendorOffer],
        required_quantity: int,
        delivery_deadline: Optional[datetime],
        dietary_requirements: List[str],
    ) -> Tuple[List[VendorOffer], List[str]]:
        """Filter candidate offers for a service category against hard constraints."""
        valid_offers: List[VendorOffer] = []
        disqualification_reasons: List[str] = []

        for offer in offers:
            reasons = []

            # 1. Capacity check
            if offer.capacity < required_quantity:
                reasons.append(
                    f"insufficient capacity ({offer.capacity} < required {required_quantity})"
                )

            # 2. Delivery deadline check
            if delivery_deadline is not None:
                # Normalize timezones if needed
                dl = delivery_deadline
                deliv = offer.delivery_by
                if dl.tzinfo is not None and deliv.tzinfo is None:
                    deliv = deliv.replace(tzinfo=dl.tzinfo)
                elif dl.tzinfo is None and deliv.tzinfo is not None:
                    dl = dl.replace(tzinfo=deliv.tzinfo)

                if deliv > dl:
                    reasons.append(
                        f"late delivery ({deliv.isoformat()} arrives after deadline {dl.isoformat()})"
                    )

            # 3. Dietary requirements check (for catering)
            if service == "catering" and dietary_requirements:
                offer_tags = set(tag.lower() for tag in offer.dietary_tags)
                missing_tags = [
                    tag for tag in dietary_requirements if tag.lower() not in offer_tags
                ]
                if missing_tags:
                    reasons.append(
                        f"missing mandatory dietary tags: {', '.join(missing_tags)}"
                    )

            # 4. Status check
            if offer.status not in ("AVAILABLE", "HELD"):
                reasons.append(f"invalid offer status: {offer.status}")

            if not reasons:
                valid_offers.append(offer)
            else:
                disqualification_reasons.append(
                    f"Offer {offer.id} ({offer.vendor_id}): " + "; ".join(reasons)
                )

        return valid_offers, disqualification_reasons

    def optimize(
        self,
        event_id: str,
        mandatory_resources: List[str],
        required_quantities: Dict[str, int],
        total_budget_inr: int,
        committed_cost_inr: int,
        hold_liability_inr: int,
        candidate_offers_by_service: Dict[str, List[VendorOffer]],
        delivery_deadline: Optional[datetime] = None,
        dietary_requirements: Optional[List[str]] = None,
        include_backup: bool = True,
    ) -> Dict[str, Any]:
        """Perform combinatorial deterministic optimization.

        Hard constraints:
          committed_cost + new_order_cost + hold_liability <= total_budget
          vendor_capacity >= required_quantity
          delivery_time <= required_deadline
          dietary_requirements satisfied
          mandatory resource categories covered
        """
        if dietary_requirements is None:
            dietary_requirements = []

        available_budget = total_budget_inr - (committed_cost_inr + hold_liability_inr)

        # Step 1: Filter valid candidate offers per category
        valid_candidates_by_service: Dict[str, List[VendorOffer]] = {}
        all_disqualifications: List[str] = []

        for service in mandatory_resources:
            qty = required_quantities.get(service, 1)
            raw_offers = candidate_offers_by_service.get(service, [])
            valid_offers, rejections = self.filter_offers_for_service(
                service=service,
                offers=raw_offers,
                required_quantity=qty,
                delivery_deadline=delivery_deadline,
                dietary_requirements=dietary_requirements,
            )
            valid_candidates_by_service[service] = valid_offers
            all_disqualifications.extend(rejections)

            if not valid_offers:
                # Hard blocker: a mandatory resource has zero valid candidates
                detail = "; ".join(rejections) if rejections else f"No quotes available for '{service}'"
                return {
                    "event_id": event_id,
                    "selected_offers": [],
                    "backup_offers": [],
                    "total_cost_inr": 0,
                    "remaining_budget_inr": available_budget,
                    "constraints_satisfied": False,
                    "reason": f"No feasible offers satisfy mandatory constraints for service '{service}'. Details: {detail}",
                    "disqualifications": all_disqualifications,
                }

        # Step 2: Cartesian product across all mandatory resource categories
        categories = list(mandatory_resources)
        offer_pools = [valid_candidates_by_service[c] for c in categories]

        feasible_combinations: List[Tuple[int, Tuple[VendorOffer, ...]]] = []
        cheapest_overall_cost = float("inf")
        cheapest_overall_combo: Optional[Tuple[VendorOffer, ...]] = None

        for combo in itertools.product(*offer_pools):
            combo_cost = sum(o.total_price_inr for o in combo)
            if combo_cost < cheapest_overall_cost:
                cheapest_overall_cost = combo_cost
                cheapest_overall_combo = combo

            if combo_cost <= available_budget:
                feasible_combinations.append((combo_cost, combo))

        if not feasible_combinations:
            deficit = cheapest_overall_cost - available_budget
            return {
                "event_id": event_id,
                "selected_offers": [],
                "backup_offers": [],
                "total_cost_inr": int(cheapest_overall_cost) if cheapest_overall_combo else 0,
                "remaining_budget_inr": available_budget,
                "constraints_satisfied": False,
                "reason": (
                    f"Cheapest valid vendor combination costs ₹{cheapest_overall_cost}, "
                    f"which exceeds available budget ₹{available_budget} by ₹{deficit}."
                ),
                "disqualifications": all_disqualifications,
            }

        # Step 3: Choose cheapest feasible primary combination
        feasible_combinations.sort(key=lambda x: x[0])
        best_cost, best_combo = feasible_combinations[0]
        selected_primary: List[VendorOffer] = list(best_combo)

        # Step 4: Identify backup offers
        backup_offers: List[VendorOffer] = []
        if include_backup:
            for primary in selected_primary:
                service = primary.service
                # Look for other valid offers in same service not from this primary vendor
                alternates = [
                    o for o in valid_candidates_by_service[service]
                    if o.vendor_id != primary.vendor_id and o.id != primary.id
                ]
                if alternates:
                    # Sort alternates by cost
                    alternates.sort(key=lambda o: o.total_price_inr)
                    backup_offers.append(alternates[0])

        total_cost_inr = sum(o.total_price_inr for o in selected_primary)
        remaining_budget = available_budget - total_cost_inr

        return {
            "event_id": event_id,
            "selected_offers": selected_primary,
            "backup_offers": backup_offers,
            "total_cost_inr": total_cost_inr,
            "remaining_budget_inr": remaining_budget,
            "constraints_satisfied": True,
            "reason": "Lowest-cost feasible vendor combination meeting all hard constraints",
            "disqualifications": all_disqualifications,
        }
