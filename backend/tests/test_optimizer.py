"""Tests for deterministic budget and resource allocation optimizer.
Covers:
- Cheapest valid offer selected.
- Cheapest offer rejected due to insufficient capacity.
- Delivery time constraint enforced.
- Dietary requirements enforced.
- Budget limit enforced.
- Explicit failure reasons when no feasible combination exists.
- Backup vendor reservation strategy.
"""

from datetime import datetime, timedelta, timezone
import pytest

from backend.schemas import VendorOffer
from backend.services.optimizer import ResourceOptimizer


IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
def optimizer():
    return ResourceOptimizer()


def test_cheapest_valid_offer_selected(optimizer):
    """Test 2: Cheapest valid combination selected among feasible options."""
    now = datetime.now(IST)
    event_start = now + timedelta(days=2)

    # Catering offers
    cater_cheap = VendorOffer(
        id="cater_1",
        vendor_id="v_cater_cheap",
        service="catering",
        quantity=120,
        capacity=150,
        total_price_inr=9600,
        delivery_by=event_start - timedelta(hours=1),
        dietary_tags=["vegetarian_option"],
        status="AVAILABLE",
        mode="SIMULATED",
    )
    cater_expensive = VendorOffer(
        id="cater_2",
        vendor_id="v_cater_exp",
        service="catering",
        quantity=120,
        capacity=200,
        total_price_inr=14000,
        delivery_by=event_start - timedelta(hours=1),
        dietary_tags=["vegetarian_option"],
        status="AVAILABLE",
        mode="SIMULATED",
    )

    # AV offers
    av_cheap = VendorOffer(
        id="av_1",
        vendor_id="v_av_cheap",
        service="av",
        quantity=1,
        capacity=150,
        total_price_inr=3000,
        delivery_by=event_start - timedelta(hours=2),
        dietary_tags=[],
        status="AVAILABLE",
        mode="SIMULATED",
    )
    av_expensive = VendorOffer(
        id="av_2",
        vendor_id="v_av_exp",
        service="av",
        quantity=1,
        capacity=300,
        total_price_inr=5000,
        delivery_by=event_start - timedelta(hours=2),
        dietary_tags=[],
        status="AVAILABLE",
        mode="SIMULATED",
    )

    result = optimizer.optimize(
        event_id="evt_opt_1",
        mandatory_resources=["catering", "av"],
        required_quantities={"catering": 120, "av": 1},
        total_budget_inr=25000,
        committed_cost_inr=0,
        hold_liability_inr=0,
        candidate_offers_by_service={
            "catering": [cater_expensive, cater_cheap],
            "av": [av_expensive, av_cheap],
        },
        delivery_deadline=event_start,
        dietary_requirements=["vegetarian_option"],
    )

    assert result["constraints_satisfied"] is True
    assert result["total_cost_inr"] == 9600 + 3000  # 12600
    assert result["remaining_budget_inr"] == 25000 - 12600

    selected_ids = {o.id for o in result["selected_offers"]}
    assert selected_ids == {"cater_1", "av_1"}

    # Backup offers check
    backup_ids = {o.id for o in result["backup_offers"]}
    assert backup_ids == {"cater_2", "av_2"}


def test_cheapest_offer_rejected_due_to_insufficient_capacity(optimizer):
    """Test 3: Cheapest offer rejected if capacity is less than required quantity."""
    now = datetime.now(IST)
    event_start = now + timedelta(days=2)

    # Cheap caterer with capacity 100 (< 120 required)
    cater_small = VendorOffer(
        id="cater_small",
        vendor_id="cater_c",
        service="catering",
        quantity=120,
        capacity=100,  # Insufficient!
        total_price_inr=7500,
        delivery_by=event_start - timedelta(hours=1),
        dietary_tags=["vegetarian_option"],
        status="AVAILABLE",
        mode="SIMULATED",
    )
    cater_fit = VendorOffer(
        id="cater_fit",
        vendor_id="cater_a",
        service="catering",
        quantity=120,
        capacity=150,  # Fits!
        total_price_inr=10000,
        delivery_by=event_start - timedelta(hours=1),
        dietary_tags=["vegetarian_option"],
        status="AVAILABLE",
        mode="SIMULATED",
    )

    av_offer = VendorOffer(
        id="av_fit",
        vendor_id="av_a",
        service="av",
        quantity=1,
        capacity=150,
        total_price_inr=3000,
        delivery_by=event_start - timedelta(hours=2),
        dietary_tags=[],
        status="AVAILABLE",
        mode="SIMULATED",
    )

    result = optimizer.optimize(
        event_id="evt_opt_cap",
        mandatory_resources=["catering", "av"],
        required_quantities={"catering": 120, "av": 1},
        total_budget_inr=25000,
        committed_cost_inr=0,
        hold_liability_inr=0,
        candidate_offers_by_service={
            "catering": [cater_small, cater_fit],
            "av": [av_offer],
        },
        delivery_deadline=event_start,
        dietary_requirements=["vegetarian_option"],
    )

    assert result["constraints_satisfied"] is True
    # cater_small was rejected despite lower cost
    selected_cater = next(o for o in result["selected_offers"] if o.service == "catering")
    assert selected_cater.id == "cater_fit"
    assert selected_cater.capacity >= 120


def test_delivery_time_constraint_enforced(optimizer):
    """Test 4: Offers arriving after delivery deadline are strictly rejected."""
    now = datetime.now(IST)
    event_start = now + timedelta(days=2)

    # AV equipment arriving 30 minutes AFTER event start
    av_late = VendorOffer(
        id="av_late",
        vendor_id="v_late",
        service="av",
        quantity=1,
        capacity=150,
        total_price_inr=2000,  # cheaper
        delivery_by=event_start + timedelta(minutes=30),  # LATE
        dietary_tags=[],
        status="AVAILABLE",
        mode="SIMULATED",
    )
    av_ontime = VendorOffer(
        id="av_ontime",
        vendor_id="v_ontime",
        service="av",
        quantity=1,
        capacity=150,
        total_price_inr=3500,
        delivery_by=event_start - timedelta(hours=1),
        dietary_tags=[],
        status="AVAILABLE",
        mode="SIMULATED",
    )

    valid_offers, rejections = optimizer.filter_offers_for_service(
        service="av",
        offers=[av_late, av_ontime],
        required_quantity=1,
        delivery_deadline=event_start,
        dietary_requirements=[],
    )

    assert len(valid_offers) == 1
    assert valid_offers[0].id == "av_ontime"
    assert any("late delivery" in r for r in rejections)


def test_dietary_requirements_enforced(optimizer):
    """Test 5: Catering offers missing required dietary tags are rejected."""
    now = datetime.now(IST)
    event_start = now + timedelta(days=2)

    # Non-veg only or missing vegetarian_option
    cater_no_veg = VendorOffer(
        id="cater_meat",
        vendor_id="v_meat",
        service="catering",
        quantity=100,
        capacity=150,
        total_price_inr=6000,
        delivery_by=event_start - timedelta(hours=1),
        dietary_tags=["halal_meat_only"],
        status="AVAILABLE",
        mode="SIMULATED",
    )
    cater_veg = VendorOffer(
        id="cater_veg",
        vendor_id="v_veg",
        service="catering",
        quantity=100,
        capacity=150,
        total_price_inr=9000,
        delivery_by=event_start - timedelta(hours=1),
        dietary_tags=["vegetarian_option", "jain_option"],
        status="AVAILABLE",
        mode="SIMULATED",
    )

    valid_offers, rejections = optimizer.filter_offers_for_service(
        service="catering",
        offers=[cater_no_veg, cater_veg],
        required_quantity=100,
        delivery_deadline=event_start,
        dietary_requirements=["vegetarian_option"],
    )

    assert len(valid_offers) == 1
    assert valid_offers[0].id == "cater_veg"
    assert any("missing mandatory dietary tags" in r for r in rejections)


def test_budget_limit_enforced(optimizer):
    """Test 6: Combinations exceeding budget ceiling are rejected."""
    now = datetime.now(IST)
    event_start = now + timedelta(days=2)

    cater_offer = VendorOffer(
        id="cater_high",
        vendor_id="cater_d",
        service="catering",
        quantity=100,
        capacity=150,
        total_price_inr=18000,
        delivery_by=event_start - timedelta(hours=1),
        dietary_tags=["vegetarian_option"],
        status="AVAILABLE",
        mode="SIMULATED",
    )
    av_offer = VendorOffer(
        id="av_high",
        vendor_id="av_d",
        service="av",
        quantity=1,
        capacity=150,
        total_price_inr=8000,
        delivery_by=event_start - timedelta(hours=1),
        dietary_tags=[],
        status="AVAILABLE",
        mode="SIMULATED",
    )

    # Total cost is 26000. Hard budget is 20000.
    result = optimizer.optimize(
        event_id="evt_budget_test",
        mandatory_resources=["catering", "av"],
        required_quantities={"catering": 100, "av": 1},
        total_budget_inr=20000,
        committed_cost_inr=0,
        hold_liability_inr=0,
        candidate_offers_by_service={
            "catering": [cater_offer],
            "av": [av_offer],
        },
        delivery_deadline=event_start,
        dietary_requirements=["vegetarian_option"],
    )

    assert result["constraints_satisfied"] is False
    assert "exceeds available budget" in result["reason"]
    assert result["total_cost_inr"] == 26000


def test_no_feasible_combination_returns_explicit_reasons(optimizer):
    """Test 15: Disqualification reasons are explicitly returned when no feasible combination exists."""
    now = datetime.now(IST)
    event_start = now + timedelta(days=2)

    # AV offers: all deliver late
    av_late = VendorOffer(
        id="av_bad",
        vendor_id="av_late",
        service="av",
        quantity=1,
        capacity=150,
        total_price_inr=3000,
        delivery_by=event_start + timedelta(hours=1),
        dietary_tags=[],
        status="AVAILABLE",
        mode="SIMULATED",
    )

    result = optimizer.optimize(
        event_id="evt_no_feasible",
        mandatory_resources=["av"],
        required_quantities={"av": 1},
        total_budget_inr=10000,
        committed_cost_inr=0,
        hold_liability_inr=0,
        candidate_offers_by_service={"av": [av_late]},
        delivery_deadline=event_start,
    )

    assert result["constraints_satisfied"] is False
    assert "No feasible offers satisfy mandatory constraints for service 'av'" in result["reason"]
    assert len(result["disqualifications"]) > 0
