"""Tests for vendor simulation, quotations, negotiation, and idempotent bookings.
Covers:
- Quotations returned from multiple vendors.
- Idempotency and duplicate booking prevention.
- Expired hold rejection.
- Confirmed order persistence.
- Bounded negotiation policies.
"""

from datetime import datetime, timedelta, timezone
import pytest

from backend.schemas import VendorOffer
from backend.services.procurement_store import ProcurementStore
from backend.services.vendor import VendorService
from backend.simulator.vendor_simulator import IST, VendorSimulator


@pytest.fixture
def tmp_vendor_service(tmp_path):
    """Create an isolated VendorService backed by a temporary SQLite database."""
    db_file = str(tmp_path / "test_vendor.db")
    store = ProcurementStore(db_path=db_file)
    simulator = VendorSimulator()
    return VendorService(store=store, simulator=simulator)


@pytest.mark.asyncio
async def test_quotations_returned_from_multiple_vendors(tmp_vendor_service):
    """Test 1: Quotations returned from multiple vendors for primary categories."""
    service = tmp_vendor_service
    event_id = "evt_quote_test"
    now = datetime.now(IST)
    deadline = now + timedelta(days=2)

    # Catering quotes (at least 3 vendors in catalog)
    catering_quotes = await service.get_vendor_quotes(
        event_id=event_id,
        service="catering",
        quantity=120,
        delivery_deadline=deadline,
        now=now,
    )
    assert len(catering_quotes) >= 3
    for q in catering_quotes:
        assert isinstance(q, VendorOffer)
        assert q.service == "catering"
        assert q.total_price_inr > 0
        assert q.capacity > 0
        assert q.delivery_by is not None
        assert q.status == "AVAILABLE"
        assert q.mode == "SIMULATED"

    # AV quotes (at least 3 vendors in catalog)
    av_quotes = await service.get_vendor_quotes(
        event_id=event_id,
        service="av",
        quantity=1,
        delivery_deadline=deadline,
        now=now,
    )
    assert len(av_quotes) >= 3
    for q in av_quotes:
        assert q.service == "av"
        assert q.total_price_inr > 0


@pytest.mark.asyncio
async def test_duplicate_booking_prevented_by_idempotency(tmp_vendor_service):
    """Test 7: Duplicate booking prevented with idempotency key."""
    service = tmp_vendor_service
    event_id = "evt_idem_test"
    quotes = await service.get_vendor_quotes(event_id, "catering", 50)
    offer = quotes[0]

    key = "idem_key_unique_123"
    order1 = await service.commit_vendor_order(
        event_id=event_id,
        offer_id=offer.id,
        idempotency_key=key,
        total_budget_inr=50000,
    )
    assert order1.status == "CONFIRMED_SIMULATED"
    assert order1.idempotency_key == key

    # Concurrent or repeated commit call with the exact same key
    order2 = await service.commit_vendor_order(
        event_id=event_id,
        offer_id=offer.id,
        idempotency_key=key,
        total_budget_inr=50000,
    )
    assert order2.id == order1.id
    assert order2.committed_inr == order1.committed_inr

    # Check store active orders: must be exactly ONE order
    active_orders = service.store.get_active_orders(event_id)
    assert len(active_orders) == 1


@pytest.mark.asyncio
async def test_expired_hold_rejected(tmp_vendor_service):
    """Test 8: Expired hold cannot be committed."""
    service = tmp_vendor_service
    event_id = "evt_expired_hold"

    # Create an offer whose hold expired in the past
    past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    expired_offer = VendorOffer(
        id="off_expired_1",
        vendor_id="cater_a",
        service="catering",
        quantity=100,
        capacity=150,
        total_price_inr=8400,
        delivery_by=datetime.now(timezone.utc) + timedelta(days=1),
        hold_expires_at=past_time,
        status="HELD",
        mode="SIMULATED",
    )
    service.store.save_offer(event_id, expired_offer)

    with pytest.raises(ValueError, match="hold has expired"):
        await service.commit_vendor_order(
            event_id=event_id,
            offer_id=expired_offer.id,
            idempotency_key="key_expired_attempt",
            total_budget_inr=50000,
        )

    # Verify status transitioned to EXPIRED in database
    refreshed = service.store.get_offer(expired_offer.id)
    assert refreshed.status == "EXPIRED"


@pytest.mark.asyncio
async def test_confirmed_order_persisted(tmp_vendor_service):
    """Test 9: Confirmed order persisted in DB and accessible by verification query."""
    service = tmp_vendor_service
    event_id = "evt_persist_test"
    quotes = await service.get_vendor_quotes(event_id, "av", 1)
    offer = quotes[0]

    key = "order_persist_key_456"
    order = await service.commit_vendor_order(
        event_id=event_id,
        offer_id=offer.id,
        idempotency_key=key,
        total_budget_inr=20000,
    )

    persisted_order = service.store.get_order_by_id(order.id)
    assert persisted_order is not None
    assert persisted_order.id == order.id
    assert persisted_order.status == "CONFIRMED_SIMULATED"
    assert persisted_order.committed_inr == offer.total_price_inr

    # Ledger audit
    ledger = service.store.calculate_budget_summary(event_id, total_budget_inr=20000)
    assert ledger["committed_inr"] == offer.total_price_inr
    assert ledger["available_inr"] == 20000 - offer.total_price_inr


@pytest.mark.asyncio
async def test_bounded_negotiation(tmp_vendor_service):
    """Test negotiation rounds, floor enforcement, and maximum rounds termination."""
    service = tmp_vendor_service
    event_id = "evt_neg_test"

    # cater_a: unit 80, min 50, fee 400. For qty 100 -> base 8000 + 400 = 8400. Floor unit 72 -> floor total 7600.
    quotes = await service.get_vendor_quotes(event_id, "catering", 100)
    cater_a_quote = next(q for q in quotes if q.vendor_id == "cater_a")
    assert cater_a_quote.total_price_inr == 8400

    # Round 1: Target within floor (target = 7800 >= floor 7600) -> ACCEPTED
    res1 = await service.negotiate_vendor_quote(
        event_id=event_id,
        offer_id=cater_a_quote.id,
        target_budget_inr=7800,
        round_number=1,
    )
    assert res1["status"] == "ACCEPTED"
    assert res1["counter_price_inr"] == 7800

    # Verify updated quote in store
    updated = service.store.get_offer(cater_a_quote.id)
    assert updated.total_price_inr == 7800

    # Test below floor: target = 6000 (< floor 7600)
    quotes2 = await service.get_vendor_quotes(event_id, "catering", 100)
    cater_a_quote2 = next(q for q in quotes2 if q.vendor_id == "cater_a")

    # Round 1: below floor -> COUNTEROFFER at floor (7600)
    res_below1 = await service.negotiate_vendor_quote(
        event_id=event_id,
        offer_id=cater_a_quote2.id,
        target_budget_inr=6000,
        round_number=1,
    )
    assert res_below1["status"] == "COUNTEROFFER"
    assert res_below1["counter_price_inr"] == 7600

    # Round 4: Exceeds max rounds -> REJECTED
    res_max = await service.negotiate_vendor_quote(
        event_id=event_id,
        offer_id=cater_a_quote2.id,
        target_budget_inr=6000,
        round_number=4,
    )
    assert res_max["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_concurrent_booking_budget_overspend_prevented(tmp_vendor_service):
    """Test concurrent booking attempts cannot breach budget limits."""
    import asyncio
    service = tmp_vendor_service
    event_id = "evt_concurrent_budget"
    total_budget = 10000

    # Register event with ₹10,000 budget
    service.store.save_event_brief(
        event_id=event_id,
        budget_inr=total_budget,
        expected_attendance=50,
        venue_capacity=100,
    )

    # Two offers costing ₹6,000 each (combined ₹12,000 > ₹10,000)
    offer1 = VendorOffer(
        id="off_c1",
        vendor_id="v1",
        service="catering",
        quantity=50,
        capacity=100,
        total_price_inr=6000,
        delivery_by=datetime.now(timezone.utc) + timedelta(days=1),
        status="AVAILABLE",
    )
    offer2 = VendorOffer(
        id="off_c2",
        vendor_id="v2",
        service="av",
        quantity=1,
        capacity=100,
        total_price_inr=6000,
        delivery_by=datetime.now(timezone.utc) + timedelta(days=1),
        status="AVAILABLE",
    )
    service.store.save_offer(event_id, offer1)
    service.store.save_offer(event_id, offer2)

    async def try_book(offer, key):
        try:
            return await service.commit_vendor_order(
                event_id=event_id,
                offer_id=offer.id,
                idempotency_key=key,
                total_budget_inr=total_budget,
            )
        except ValueError as e:
            return e

    # Run both bookings concurrently
    res1, res2 = await asyncio.gather(
        try_book(offer1, "conc_key_1"),
        try_book(offer2, "conc_key_2"),
    )

    # Exactly one should succeed, and one should fail with budget exceeded
    successes = [r for r in (res1, res2) if not isinstance(r, Exception)]
    failures = [r for r in (res1, res2) if isinstance(r, Exception)]

    assert len(successes) == 1
    assert len(failures) == 1
    assert "Budget exceeded" in str(failures[0])

    ledger = service.store.calculate_budget_summary(event_id, total_budget_inr=total_budget)
    assert ledger["committed_inr"] <= total_budget

