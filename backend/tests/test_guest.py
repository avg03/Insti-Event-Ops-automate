from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

import backend.services.guest as guest_service
from backend.services.crustdata import EvidenceRef, GuestCandidate
from backend.simulator.guest_simulator import SimulatedGuestChannel


def candidate(identifier: str, title: str = "AI Research Lead") -> GuestCandidate:
    return GuestCandidate(
        id=identifier,
        event_id="evt",
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


@pytest.fixture
def channel(tmp_path, monkeypatch):
    value = SimulatedGuestChannel(db_path=tmp_path / "guest.db")
    guest_service.set_guest_channel(value)
    yield value
    guest_service.set_guest_channel(None)


def constraints(**extra):
    value = {
        "slots": [
            {"starts_at": "2026-11-12T16:00:00+05:30", "ends_at": "2026-11-12T16:45:00+05:30"},
            {"starts_at": "2026-11-12T17:15:00+05:30", "ends_at": "2026-11-12T18:00:00+05:30"},
        ],
        "max_honorarium_inr": 3000,
        "guest_budget_inr": 6000,
        "max_invitation_attempts": 5,
    }
    value.update(extra)
    return value


@pytest.mark.asyncio
async def test_guest_accepts_invitation(channel, monkeypatch):
    first = candidate("accept")
    channel.set_candidate_scenario(first.id, {"behavior": "accept", "honorarium_inr": 2000})
    monkeypatch.setattr(guest_service, "search_speakers", AsyncMock(return_value=[first]))
    result = await guest_service.coordinate_event_guests("evt", "AI research", 1, constraints())
    assert result["status"] == "COMPLETE"
    assert result["confirmed_guests"][0]["candidate"]["invitation_status"] == "CONFIRMED_SIMULATED"
    assert result["confirmed_guests"][0]["booking"]["mode"] == "SIMULATED"


@pytest.mark.asyncio
async def test_decline_selects_next_candidate(channel, monkeypatch):
    first, second = candidate("decline", "AI Director"), candidate("accept2", "AI Engineer")
    channel.set_candidate_scenario(first.id, {"behavior": "decline", "reason": "busy"})
    channel.set_candidate_scenario(second.id, {"behavior": "accept"})
    monkeypatch.setattr(guest_service, "search_speakers", AsyncMock(return_value=[first, second]))
    result = await guest_service.coordinate_event_guests("evt", "AI Director", 1, constraints())
    assert result["status"] == "COMPLETE"
    assert result["confirmed_guests"][0]["candidate"]["id"] == second.id
    assert any(issue["candidate_id"] == first.id for issue in result["issues"])


@pytest.mark.asyncio
async def test_guest_requests_different_time(channel, monkeypatch):
    first = candidate("later")
    channel.set_candidate_scenario(
        first.id,
        {"behavior": "conditional", "request": {"start_after": "17:00", "honorarium_inr": 2000}},
    )
    monkeypatch.setattr(guest_service, "search_speakers", AsyncMock(return_value=[first]))
    result = await guest_service.coordinate_event_guests("evt", "AI", 1, constraints())
    booking = result["confirmed_guests"][0]["booking"]
    assert booking["slot"]["starts_at"].startswith("2026-11-12T17:15")
    assert booking["slot"]["honorarium_inr"] == 2000


@pytest.mark.asyncio
async def test_excessive_honorarium_is_rejected(channel, monkeypatch):
    first = candidate("expensive")
    channel.set_candidate_scenario(
        first.id,
        {"behavior": "conditional", "request": {"honorarium_inr": 9000}},
    )
    monkeypatch.setattr(guest_service, "search_speakers", AsyncMock(return_value=[first]))
    result = await guest_service.coordinate_event_guests("evt", "AI", 1, constraints())
    assert result["status"] == "BLOCKED"
    assert any("exceeds cap" in issue["message"] for issue in result["issues"])
    assert channel.inspect_event("evt")["bookings"] == []


@pytest.mark.asyncio
async def test_guest_cancels_after_confirmation(channel):
    first = candidate("cancel")
    channel.set_candidate_scenario(first.id, {"behavior": "accept"})
    result = await guest_service._coordinate_candidate("evt", first, constraints(topic="AI", required_count=1), 1, 0)
    assert result["outcome"] == "CONFIRMED_SIMULATED"
    cancelled = await channel.cancel_booking("evt", first.id)
    assert cancelled["status"] == "CANCELLED"
    assert channel.inspect_event("evt")["bookings"][0]["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_backup_replaces_cancelled_guest(channel):
    primary, backup = candidate("primary"), candidate("backup")
    channel.set_candidate_scenario(primary.id, {"behavior": "accept"})
    channel.set_candidate_scenario(backup.id, {"behavior": "accept"})
    await guest_service._coordinate_candidate("evt", primary, constraints(topic="AI", required_count=1), 1, 0)
    result = await guest_service.recover_guest(
        "evt", primary.id, [backup], constraints(topic="AI", required_count=1)
    )
    assert result["status"] == "RECOVERED"
    assert result["replacement"]["candidate"]["id"] == backup.id
    active = [b for b in channel.inspect_event("evt")["bookings"] if b["status"] == "CONFIRMED_SIMULATED"]
    assert [b["candidate_id"] for b in active] == [backup.id]


@pytest.mark.asyncio
async def test_duplicate_invitation_is_idempotent(channel):
    channel.set_candidate_scenario("same", {"behavior": "accept"})
    terms = {"slot": constraints()["slots"][0]}
    first = await guest_service.send_guest_invitation("evt", "same", terms, "idem-1")
    second = await guest_service.send_guest_invitation("evt", "same", terms, "idem-1")
    assert first["invitation_id"] == second["invitation_id"]
    assert len(channel.inspect_event("evt")["invitations"]) == 1


@pytest.mark.asyncio
async def test_no_feasible_guest_returns_structured_block(channel, monkeypatch):
    first = candidate("nope")
    channel.set_candidate_scenario(first.id, {"behavior": "decline"})
    monkeypatch.setattr(guest_service, "search_speakers", AsyncMock(return_value=[first]))
    result = await guest_service.coordinate_event_guests("evt", "AI", 1, constraints())
    assert result["status"] == "BLOCKED"
    assert result["confirmed_guests"] == []
    assert any(issue["type"] == "NO_FEASIBLE_GUEST" for issue in result["issues"])
