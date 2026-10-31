"""Tests for automatic vendor disruption recovery and attendance recalculation.
Covers:
- Vendor cancellation triggers backup replacement.
- Backup unavailable triggers alternative marketplace search.
- Cancellation fees accounted for in budget ledger.
- Attendance increase triggers re-optimization.
- Venue capacity excess produces blocked state.
- Complete end-to-end autonomous procurement and recovery workflow.
"""

from datetime import datetime, timedelta, timezone
import pytest

from backend.schemas import VendorOffer
from backend.services.procurement_store import ProcurementStore
from backend.services.vendor import VendorService
from backend.simulator.vendor_simulator import IST, VendorSimulator


@pytest.fixture
def recovery_service(tmp_path):
    """Isolated VendorService instance for recovery tests."""
    db_file = str(tmp_path / "test_recovery.db")
    store = ProcurementStore(db_path=db_file)
    simulator = VendorSimulator()
    return VendorService(store=store, simulator=simulator)


@pytest.mark.asyncio
async def test_vendor_cancellation_triggers_backup_replacement(recovery_service):
    """Test 10 & 12: Injected vendor cancellation triggers backup hold activation and accounts for fees."""
    service = recovery_service
    event_id = "evt_recovery_backup"
    event_start = datetime.now(timezone.utc) + timedelta(days=3)

    # 1. Procure resources
    procure_res = await service.procure_event_resources(
        event_id=event_id,
        requirements={
            "expected_attendance": 120,
            "venue_capacity": 150,
            "mandatory_resources": ["catering", "av"],
            "dietary_requirements": ["vegetarian_option"],
            "starts_at": event_start.isoformat(),
        },
        budget_inr=25000,
    )
    assert procure_res["status"] == "COMPLETE"
    assert len(procure_res["confirmed_orders"]) == 2
    assert len(procure_res["backup_holds"]) >= 1

    # Find catering order
    catering_order_dict = next(
        o for o in procure_res["confirmed_orders"]
        if "catering" in o["id"] or service.store.get_offer(o["offer_id"]).service == "catering"
    )
    failed_order_id = catering_order_dict["id"]
    original_cater_cost = catering_order_dict["committed_inr"]

    # 2. Trigger automatic recovery on cancellation
    rec_res = await service.recover_vendor(
        event_id=event_id,
        failed_order_id=failed_order_id,
    )

    assert rec_res["status"] == "RECOVERED"
    assert rec_res["recovery_source"] == "BACKUP_HOLD"
    assert rec_res["replacement_order"] is not None

    # Verify failed order marked CANCELLED
    failed_order = service.store.get_order_by_id(failed_order_id)
    assert failed_order.status == "CANCELLED"

    # Verify replacement order is active and CONFIRMED_SIMULATED
    rep_order = service.store.get_order_by_id(rec_res["replacement_order"]["id"])
    assert rep_order.status == "CONFIRMED_SIMULATED"

    # Verify budget ledger accounting (committed + fees <= 25000)
    ledger = service.store.calculate_budget_summary(event_id, total_budget_inr=25000)
    assert ledger["committed_inr"] <= 25000
    assert ledger["cancellation_fees_inr"] == rec_res["cancellation_fee_inr"]


@pytest.mark.asyncio
async def test_backup_unavailable_triggers_alternative_search(recovery_service):
    """Test 11: If backup hold is expired or unavailable, alternative vendor from marketplace is selected."""
    service = recovery_service
    event_id = "evt_alt_search"
    event_start = datetime.now(timezone.utc) + timedelta(days=3)

    # Procure initial resources
    procure_res = await service.procure_event_resources(
        event_id=event_id,
        requirements={
            "expected_attendance": 100,
            "venue_capacity": 150,
            "mandatory_resources": ["catering"],
            "dietary_requirements": ["vegetarian_option"],
            "starts_at": event_start.isoformat(),
        },
        budget_inr=30000,
    )
    assert procure_res["status"] == "COMPLETE"
    cater_order = procure_res["confirmed_orders"][0]

    # Expire all existing backup holds deliberately
    active_holds = service.store.get_active_holds(event_id)
    for h in active_holds:
        service.store.update_hold_status(h["id"], "EXPIRED")

    # Now recover: should search marketplace fallback
    rec_res = await service.recover_vendor(
        event_id=event_id,
        failed_order_id=cater_order["id"],
    )

    assert rec_res["status"] == "RECOVERED"
    assert rec_res["recovery_source"] == "MARKETPLACE_FALLBACK"
    assert rec_res["replacement_order"] is not None


@pytest.mark.asyncio
async def test_cancellation_fees_included_correctly(recovery_service):
    """Test 12: Cancellation fee from vendor policy is correctly tracked in the ledger."""
    service = recovery_service
    event_id = "evt_fee_ledger"
    event_start = datetime.now(timezone.utc) + timedelta(days=3)

    # Let's commit an order for Bombay Gourmet Hospitality (cater_b) which has ₹500 cancellation fee
    offer_b = service.simulator.generate_quote(
        event_id=event_id,
        vendor_id="cater_b",
        quantity=100,
        event_starts_at=event_start,
    )
    service.store.save_offer(event_id, offer_b)
    service.store.save_event_brief(
        event_id=event_id,
        budget_inr=25000,
        expected_attendance=100,
        venue_capacity=150,
        starts_at=event_start,
    )

    order = await service.commit_vendor_order(
        event_id=event_id,
        offer_id=offer_b.id,
        idempotency_key="key_b_order",
        total_budget_inr=25000,
    )
    assert order.committed_inr == offer_b.total_price_inr

    # Trigger recovery on order
    rec_res = await service.recover_vendor(event_id=event_id, failed_order_id=order.id)
    assert rec_res["cancellation_fee_inr"] == 500

    ledger = service.store.calculate_budget_summary(event_id, total_budget_inr=25000)
    assert ledger["cancellation_fees_inr"] == 500


@pytest.mark.asyncio
async def test_attendance_increase_triggers_reoptimization(recovery_service):
    """Test 13: Attendance increase causes automatic resource resizing or vendor replacement."""
    service = recovery_service
    event_id = "evt_scale_test"
    event_start = datetime.now(timezone.utc) + timedelta(days=3)

    # 1. Start with 100 attendance, venue cap 150
    procure_res = await service.procure_event_resources(
        event_id=event_id,
        requirements={
            "expected_attendance": 100,
            "venue_capacity": 150,
            "mandatory_resources": ["catering"],
            "dietary_requirements": ["vegetarian_option"],
            "starts_at": event_start.isoformat(),
        },
        budget_inr=25000,
    )
    assert procure_res["status"] == "COMPLETE"
    initial_order = procure_res["confirmed_orders"][0]

    # 2. Scale attendance up to 140 (within venue capacity 150)
    scale_res = await service.recalculate_resources(
        event_id=event_id,
        new_attendance=140,
    )

    assert scale_res["status"] == "RECALCULATED"
    assert scale_res["new_attendance"] == 140
    assert len(scale_res["updated_orders"]) >= 1

    # Check that new order quantity is 140
    updated_order_dict = scale_res["updated_orders"][0]
    updated_offer = service.store.get_offer(updated_order_dict["offer_id"])
    assert updated_offer.quantity >= 140


@pytest.mark.asyncio
async def test_venue_capacity_excess_produces_blocked_state(recovery_service):
    """Test 14: Attendance increase beyond venue capacity yields BLOCKED status."""
    service = recovery_service
    event_id = "evt_venue_excess"
    event_start = datetime.now(timezone.utc) + timedelta(days=3)

    # Initial procurement with attendance 120, venue capacity 150
    await service.procure_event_resources(
        event_id=event_id,
        requirements={
            "expected_attendance": 120,
            "venue_capacity": 150,
            "mandatory_resources": ["catering", "av"],
            "starts_at": event_start.isoformat(),
        },
        budget_inr=25000,
    )

    # Attempt to scale attendance to 180 (> venue capacity 150)
    scale_res = await service.recalculate_resources(
        event_id=event_id,
        new_attendance=180,
    )

    assert scale_res["status"] == "BLOCKED"
    assert scale_res["reason"] == "CAPACITY_EXCEEDED"
    assert "violates venue capacity 150" in scale_res["message"]

    # Verify issue was persisted in DB
    issues = service.store.get_issues(event_id)
    assert any(i.type == "CAPACITY_EXCEEDED" and i.status == "BLOCKED" for i in issues)


@pytest.mark.asyncio
async def test_end_to_end_procure_and_recovery_flow(recovery_service):
    """Comprehensive test covering Section 15 workflow:
    Get quotes -> Optimize -> Confirm order -> Inject cancellation -> Recover -> Validate budget.
    """
    service = recovery_service
    event_id = "evt_hackathon_demo"
    event_start = datetime.now(timezone.utc) + timedelta(days=4)

    # 1. Procure resources
    res = await service.procure_event_resources(
        event_id=event_id,
        requirements={
            "expected_attendance": 120,
            "venue_capacity": 150,
            "mandatory_resources": ["catering", "av"],
            "dietary_requirements": ["vegetarian_option"],
            "starts_at": event_start.isoformat(),
        },
        budget_inr=25000,
    )

    assert res["status"] == "COMPLETE"
    assert len(res["confirmed_orders"]) == 2
    assert res["committed_inr"] <= 25000
    assert res["available_inr"] >= 0

    catering_order = next(
        o for o in res["confirmed_orders"]
        if service.store.get_offer(o["offer_id"]).service == "catering"
    )

    # 2. Injected simulated cancellation
    recovery = await service.recover_vendor(
        event_id=event_id,
        failed_order_id=catering_order["id"],
    )

    assert recovery["status"] == "RECOVERED"
    assert recovery["replacement_order"]["status"] == "CONFIRMED_SIMULATED"
    assert recovery["committed_inr"] <= 25000

    # 3. Verify audit trail in DB
    audits = service.store.get_audit_events(event_id)
    assert len(audits) >= 3
    assert any(a.action == "COMMIT_VENDOR_ORDER" for a in audits)
