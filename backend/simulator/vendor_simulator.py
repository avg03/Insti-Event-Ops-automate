"""Local deterministic vendor simulator for EventOps Autopilot.
No external network calls or real monetary transactions are permitted.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from backend.schemas import VendorOffer


# Default India timezone (Asia/Kolkata: UTC+05:30)
IST = timezone(timedelta(hours=5, minutes=30))


class VendorSimulator:
    """Deterministic simulated vendor marketplace."""

    MAX_NEGOTIATION_ROUNDS = 3

    def __init__(self, scenarios_path: Optional[Path | str] = None):
        if scenarios_path is None:
            scenarios_path = Path(__file__).parent / "vendor_scenarios.json"
        self.scenarios_path = Path(scenarios_path)
        self.vendors: Dict[str, Dict[str, Any]] = {}
        self.offers: Dict[str, VendorOffer] = {}
        self.negotiation_history: Dict[str, List[Dict[str, Any]]] = {}
        self.load_scenarios()

    def load_scenarios(self) -> None:
        """Load vendor profiles and behavioral policies from JSON scenario definition."""
        if not self.scenarios_path.exists():
            raise FileNotFoundError(f"Vendor scenarios file not found at {self.scenarios_path}")
        with open(self.scenarios_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for v in data.get("vendors", []):
            self.vendors[v["vendor_id"]] = v

    def get_vendor(self, vendor_id: str) -> Optional[Dict[str, Any]]:
        return self.vendors.get(vendor_id)

    def list_vendors(self, service: Optional[str] = None) -> List[Dict[str, Any]]:
        if service:
            return [v for v in self.vendors.values() if v.get("service_category") == service]
        return list(self.vendors.values())

    def generate_quote(
        self,
        event_id: str,
        vendor_id: str,
        quantity: int,
        event_starts_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> VendorOffer:
        """Generate a deterministic normalized VendorOffer for a vendor and quantity."""
        vendor = self.vendors.get(vendor_id)
        if not vendor:
            raise ValueError(f"Unknown vendor_id: {vendor_id}")

        if now is None:
            now = datetime.now(IST)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=IST)

        if event_starts_at is None:
            event_starts_at = now + timedelta(days=5)
        elif event_starts_at.tzinfo is None:
            event_starts_at = event_starts_at.replace(tzinfo=IST)

        # Quantity and capacity calculations
        service = vendor["service_category"]
        min_order = vendor.get("minimum_order", 1)
        effective_quantity = max(quantity, min_order)
        unit_price = vendor.get("price_per_unit", 0)
        delivery_fee = vendor.get("delivery_fee", 0)
        total_price = (unit_price * effective_quantity) + delivery_fee
        capacity = vendor.get("maximum_capacity", effective_quantity)

        # Delivery time calculations
        behavior = vendor.get("behavior", "normal")
        lead_time = timedelta(minutes=vendor.get("delivery_lead_time_minutes", 60))

        if behavior == "late_delivery":
            # Intentional failure scenario: delivery arrives 30 minutes after event starts
            delivery_by = event_starts_at + timedelta(minutes=30)
        else:
            # Deliver safely before event start
            delivery_by = event_starts_at - timedelta(minutes=30)

        # Hold expiration calculation
        hold_minutes = vendor.get("reliability_metadata", {}).get("hold_minutes", 60)
        hold_expires_at = now + timedelta(minutes=hold_minutes)

        # Dietary tags for catering
        dietary_tags = []
        if service == "catering":
            dietary_tags = list(vendor.get("supported_requirements", []))

        offer_id = f"off_{vendor_id}_{uuid.uuid4().hex[:8]}"
        offer = VendorOffer(
            id=offer_id,
            vendor_id=vendor_id,
            service=service,
            quantity=effective_quantity,
            capacity=capacity,
            total_price_inr=total_price,
            delivery_by=delivery_by,
            hold_expires_at=hold_expires_at,
            dietary_tags=dietary_tags,
            status="AVAILABLE",
            mode="SIMULATED",
        )

        self.offers[offer_id] = offer
        self.negotiation_history[offer_id] = [
            {
                "round": 0,
                "action": "QUOTE_ISSUED",
                "price_inr": total_price,
                "timestamp": now.isoformat(),
            }
        ]
        return offer

    def get_quotes(
        self,
        event_id: str,
        service: str,
        quantity: int,
        event_starts_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> List[VendorOffer]:
        """Retrieve quotations from all vendors in the category."""
        matching_vendors = [v for v in self.vendors.values() if v.get("service_category") == service]
        offers = []
        for v in matching_vendors:
            offer = self.generate_quote(
                event_id=event_id,
                vendor_id=v["vendor_id"],
                quantity=quantity,
                event_starts_at=event_starts_at,
                now=now,
            )
            offers.append(offer)
        return offers

    def negotiate(
        self,
        offer_id: str,
        target_price_inr: int,
        round_number: int = 1,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Execute bounded deterministic negotiation.

        Simulated vendor responds with:
          - ACCEPTED: target price is met and within floor
          - COUNTEROFFER: vendor counters with feasible price
          - REJECTED: target is below floor or max rounds exceeded
          - UNAVAILABLE: vendor inventory/capacity not available
        """
        offer = self.offers.get(offer_id)
        if not offer:
            return {
                "offer_id": offer_id,
                "status": "UNAVAILABLE",
                "counter_price_inr": None,
                "reason": f"Offer {offer_id} not found in marketplace",
                "round": round_number,
            }

        vendor = self.vendors.get(offer.vendor_id)
        if not vendor:
            return {
                "offer_id": offer_id,
                "status": "UNAVAILABLE",
                "counter_price_inr": None,
                "reason": f"Vendor {offer.vendor_id} not found",
                "round": round_number,
            }

        if now is None:
            now = datetime.now(IST)

        history = self.negotiation_history.setdefault(offer_id, [])

        # Check maximum rounds limit
        if round_number > self.MAX_NEGOTIATION_ROUNDS or len(history) > self.MAX_NEGOTIATION_ROUNDS:
            result = {
                "offer_id": offer_id,
                "status": "REJECTED",
                "counter_price_inr": None,
                "reason": f"Exceeded maximum negotiation rounds ({self.MAX_NEGOTIATION_ROUNDS})",
                "round": round_number,
            }
            history.append(result)
            return result

        behavior = vendor.get("behavior", "normal")
        if behavior == "strict_no_discount":
            result = {
                "offer_id": offer_id,
                "status": "REJECTED",
                "counter_price_inr": offer.total_price_inr,
                "reason": "Vendor maintains strict non-negotiable standard rate",
                "round": round_number,
            }
            history.append(result)
            return result

        # Compute price floor (vendor's lowest acceptable price)
        unit_floor = vendor.get("negotiation_floor", vendor.get("price_per_unit", 0))
        delivery_fee = vendor.get("delivery_fee", 0)
        floor_total = (unit_floor * offer.quantity) + delivery_fee

        if target_price_inr >= offer.total_price_inr:
            # Target is already at or above current quote
            result = {
                "offer_id": offer_id,
                "status": "ACCEPTED",
                "counter_price_inr": offer.total_price_inr,
                "reason": "Target price meets current vendor quotation",
                "round": round_number,
            }
            history.append(result)
            return result

        if target_price_inr >= floor_total:
            if behavior == "counteroffer_negotiator":
                # Counteroffer midway between standard quote and target
                counter = (offer.total_price_inr + target_price_inr) // 2
                result = {
                    "offer_id": offer_id,
                    "status": "COUNTEROFFER",
                    "counter_price_inr": counter,
                    "reason": f"Vendor counteroffers compromise rate of ₹{counter}",
                    "round": round_number,
                }
                # Update offer's price with counter
                updated_offer = offer.model_copy(update={"total_price_inr": counter})
                self.offers[offer_id] = updated_offer
            else:
                # Accept target directly
                result = {
                    "offer_id": offer_id,
                    "status": "ACCEPTED",
                    "counter_price_inr": target_price_inr,
                    "reason": f"Vendor accepted negotiated rate of ₹{target_price_inr}",
                    "round": round_number,
                }
                updated_offer = offer.model_copy(update={"total_price_inr": target_price_inr})
                self.offers[offer_id] = updated_offer
        else:
            # Target is below floor
            if round_number < self.MAX_NEGOTIATION_ROUNDS:
                result = {
                    "offer_id": offer_id,
                    "status": "COUNTEROFFER",
                    "counter_price_inr": floor_total,
                    "reason": f"Target ₹{target_price_inr} is below cost threshold; counteroffer at floor ₹{floor_total}",
                    "round": round_number,
                }
                updated_offer = offer.model_copy(update={"total_price_inr": floor_total})
                self.offers[offer_id] = updated_offer
            else:
                result = {
                    "offer_id": offer_id,
                    "status": "REJECTED",
                    "counter_price_inr": None,
                    "reason": f"Target ₹{target_price_inr} below floor ₹{floor_total}; negotiation terminated",
                    "round": round_number,
                }

        history.append(result)
        return result

    def calculate_cancellation_fee(self, vendor_id: str, committed_inr: int) -> int:
        """Calculate cancellation fee based on vendor policy."""
        vendor = self.vendors.get(vendor_id)
        if not vendor:
            return 0
        policy = vendor.get("cancellation_policy", {})
        fixed_fee = policy.get("cancellation_fee_inr", 0)
        percentage_fee = (committed_inr * policy.get("fee_percentage", 0)) // 100
        return max(fixed_fee, percentage_fee)
