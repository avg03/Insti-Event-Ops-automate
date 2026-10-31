"""End-to-end tests for the merged guest, vendor, graph, and verifier service."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

import backend.services.guest as guest_service
from backend.agent.graph import EventOpsOrchestrator
from backend.db import EventStore
from backend.schemas import EventBrief, EvidenceRef, GuestCandidate
from backend.services.procurement_store import ProcurementStore
from backend.services.vendor import VendorService
from backend.simulator.guest_simulator import SimulatedGuestChannel
from backend.simulator.vendor_simulator import VendorSimulator


@pytest.fixture
def integrated(tmp_path):
    db_path = str(tmp_path / "integrated.db")
    event_store = EventStore(db_path)
    procurement_store = ProcurementStore(db_path)
    guest_channel = SimulatedGuestChannel(db_path)
    vendor_service = VendorService(
        store=procurement_store, simulator=VendorSimulator()
    )
    return EventOpsOrchestrator(
        event_store=event_store,
        procurement_store=procurement_store,
        guest_channel=guest_channel,
        vendor_service=vendor_service,
    )


def make_brief(**changes) -> EventBrief:
    values = {
        "title": "AI Community Orientation",
        "topic": "AI research",
        "city": "Mumbai",
        "timezone": "Asia/Kolkata",
        "starts_at": "2026-11-12T16:00:00+05:30",
        "ends_at": "2026-11-12T19:00:00+05:30",
        "budget_inr": 25000,
        "expected_attendance": 120,
        "venue_capacity": 150,
        "guest_count": 1,
        "mandatory_resources": ["catering", "av"],
        "dietary_requirements": ["vegetarian_option"],
    }
    values.update(changes)
    return EventBrief.model_validate(values)


def make_candidate(event_id: str, identifier: str, title: str) -> GuestCandidate:
    return GuestCandidate(
        id=identifier,
        event_id=event_id,
        canonical_person_id=identifier,
        display_name=f"Candidate {identifier}",
        current_title=title,
        company_name="Example Labs",
        relevance_score=0,
        evidence=[
            EvidenceRef(
                provider="CRUSTDATA",
                source_id=identifier,
                collected_at=datetime.now(timezone.utc),
                claim=f"Current professional title: {title}",
                support="basic_profile.current_title",
                mode="LIVE_DATA",
            )
        ],
    )


async def create_and_run(
    orchestrator: EventOpsOrchestrator, event_id: str, brief: EventBrief
) -> dict:
    orchestrator.event_store.create_event(event_id, f"run_{event_id}", brief)
    await orchestrator.run_event(event_id)
    return orchestrator.get_event_state(event_id)


@pytest.mark.asyncio
async def test_complete_event_planning(integrated, monkeypatch):
    event_id = "evt_complete"
    candidates = [
        make_candidate(event_id, "expert_a", "AI Research Director"),
        make_candidate(event_id, "expert_b", "Machine Learning Engineer"),
    ]
    for candidate in candidates:
        integrated.guest_channel.set_candidate_scenario(
            candidate.id, {"behavior": "accept", "honorarium_inr": 1500}
        )
    monkeypatch.setattr(
        guest_service, "search_speakers", AsyncMock(return_value=candidates)
    )
    state = await create_and_run(
        integrated, event_id, make_brief(guest_count=2, topic="AI machine learning")
    )
    assert state["status"] == "READY"
    assert len([b for b in state["guest_bookings"] if b["status"] == "CONFIRMED_SIMULATED"]) == 2
    assert len([o for o in state["orders"] if o["status"] == "CONFIRMED_SIMULATED"]) == 2
    assert all(state["readiness"]["checks"].values())


@pytest.mark.asyncio
async def test_guest_decline_uses_next_ranked_candidate(integrated, monkeypatch):
    event_id = "evt_decline"
    declined = make_candidate(event_id, "first", "AI Director")
    accepted = make_candidate(event_id, "second", "AI Engineer")
    integrated.guest_channel.set_candidate_scenario(declined.id, {"behavior": "decline"})
    integrated.guest_channel.set_candidate_scenario(accepted.id, {"behavior": "accept"})
    monkeypatch.setattr(
        guest_service, "search_speakers", AsyncMock(return_value=[declined, accepted])
    )
    state = await create_and_run(
        integrated, event_id, make_brief(topic="AI Director")
    )
    assert state["status"] == "READY"
    confirmed = state["guest_coordination"]["confirmed_guests"]
    assert confirmed[0]["candidate"]["id"] == accepted.id
    assert any(issue["candidate_id"] == declined.id for issue in state["guest_coordination"]["issues"])


@pytest.mark.asyncio
async def test_guest_conditional_acceptance_changes_slot(integrated, monkeypatch):
    event_id = "evt_conditional"
    candidate = make_candidate(event_id, "conditional", "AI Researcher")
    integrated.guest_channel.set_candidate_scenario(
        candidate.id,
        {
            "behavior": "conditional",
            "request": {"start_after": "17:00", "honorarium_inr": 2000},
        },
    )
    monkeypatch.setattr(
        guest_service, "search_speakers", AsyncMock(return_value=[candidate])
    )
    state = await create_and_run(integrated, event_id, make_brief())
    assert state["status"] == "READY"
    booking = next(b for b in state["guest_bookings"] if b["status"] == "CONFIRMED_SIMULATED")
    assert booking["slot"]["starts_at"].startswith("2026-11-12T17:15")
    assert booking["slot"]["honorarium_inr"] == 2000


@pytest.mark.asyncio
async def test_vendor_cancellation_recovers_and_reverifies(integrated, monkeypatch):
    event_id = "evt_vendor_recovery"
    monkeypatch.setattr(guest_service, "search_speakers", AsyncMock(return_value=[]))
    state = await create_and_run(integrated, event_id, make_brief(guest_count=0))
    catering_order = next(
        order
        for order in integrated.procurement_store.get_active_orders(event_id)
        if integrated.procurement_store.get_offer(order.offer_id).service == "catering"
    )
    result = await integrated.simulate_disruption(
        event_id, "VENDOR_CANCELLED", {"target_id": catering_order.id}
    )
    assert result["recovery"]["status"] == "RECOVERED"
    assert result["status"] == "READY"
    assert integrated.procurement_store.get_order_by_id(catering_order.id).status == "CANCELLED"


@pytest.mark.asyncio
async def test_rerun_does_not_duplicate_bookings(integrated, monkeypatch):
    event_id = "evt_idempotent"
    candidate = make_candidate(event_id, "idempotent_guest", "AI Researcher")
    integrated.guest_channel.set_candidate_scenario(candidate.id, {"behavior": "accept"})
    monkeypatch.setattr(
        guest_service, "search_speakers", AsyncMock(return_value=[candidate])
    )
    await create_and_run(integrated, event_id, make_brief())
    guest_count = len(integrated.guest_channel.inspect_event(event_id)["bookings"])
    order_count = len(integrated.procurement_store.get_all_orders(event_id))
    await integrated.run_event(event_id)
    assert len(integrated.guest_channel.inspect_event(event_id)["bookings"]) == guest_count
    assert len(integrated.procurement_store.get_all_orders(event_id)) == order_count


@pytest.mark.asyncio
async def test_budget_overrun_is_rejected(integrated, monkeypatch):
    event_id = "evt_budget_block"
    monkeypatch.setattr(guest_service, "search_speakers", AsyncMock(return_value=[]))
    state = await create_and_run(
        integrated,
        event_id,
        make_brief(guest_count=0, budget_inr=1000, mandatory_resources=["catering"]),
    )
    assert state["status"] == "BLOCKED"
    assert state["readiness"]["checks"]["required_vendor_orders_confirmed"] is False
    assert integrated.procurement_store.get_active_orders(event_id) == []


@pytest.mark.asyncio
async def test_attendance_surge_reoptimizes_resources(integrated, monkeypatch):
    event_id = "evt_surge"
    monkeypatch.setattr(guest_service, "search_speakers", AsyncMock(return_value=[]))
    state = await create_and_run(
        integrated,
        event_id,
        make_brief(guest_count=0, expected_attendance=100, budget_inr=30000),
    )
    assert state["status"] == "READY"
    result = await integrated.simulate_disruption(
        event_id, "ATTENDANCE_CHANGED", {"new_count": 140}
    )
    assert result["recovery"]["status"] == "RECALCULATED"
    assert result["status"] == "READY"
    updated = integrated.get_event_state(event_id)
    assert updated["brief"]["expected_attendance"] == 140
    catering = next(
        integrated.procurement_store.get_offer(order.offer_id)
        for order in integrated.procurement_store.get_active_orders(event_id)
        if integrated.procurement_store.get_offer(order.offer_id).service == "catering"
    )
    assert catering.quantity >= 140


@pytest.mark.asyncio
async def test_unavailable_guest_backup_blocks_event(integrated, monkeypatch):
    event_id = "evt_no_backup"
    candidate = make_candidate(event_id, "only_guest", "AI Researcher")
    integrated.guest_channel.set_candidate_scenario(candidate.id, {"behavior": "accept"})
    monkeypatch.setattr(
        guest_service, "search_speakers", AsyncMock(return_value=[candidate])
    )
    state = await create_and_run(integrated, event_id, make_brief())
    assert state["status"] == "READY"
    result = await integrated.simulate_disruption(
        event_id, "GUEST_CANCELLED", {"target_id": candidate.id}
    )
    assert result["recovery"]["status"] == "BLOCKED"
    assert result["status"] == "BLOCKED"
    assert "required_guests_confirmed" in result["readiness"]["blockers"]


def test_fastapi_create_poll_timeline_and_verify(integrated, monkeypatch):
    from fastapi.testclient import TestClient
    import backend.main as main_module

    candidate_id = "api_guest"
    integrated.guest_channel.set_candidate_scenario(candidate_id, {"behavior": "accept"})

    async def api_candidates(event_id: str, topic: str, max_results: int = 10):
        return [make_candidate(event_id, candidate_id, "AI Researcher")]

    monkeypatch.setattr(guest_service, "search_speakers", api_candidates)
    monkeypatch.setattr(main_module, "orchestrator", integrated)
    with TestClient(main_module.app) as client:
        created = client.post(
            "/api/events", json=make_brief().model_dump(mode="json")
        )
        assert created.status_code == 202
        event_id = created.json()["event_id"]
        state = client.get(f"/api/events/{event_id}")
        assert state.status_code == 200
        assert state.json()["status"] == "READY"
        timeline = client.get(f"/api/events/{event_id}/timeline")
        assert timeline.status_code == 200
        assert any(item["action"] == "VERIFY_EVENT" for item in timeline.json()["items"])
        verified = client.post(f"/api/events/{event_id}/verify")
        assert verified.status_code == 200
        assert verified.json()["status"] == "READY"
