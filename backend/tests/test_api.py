"""API contract tests for FastAPI endpoints."""

import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from backend.main import app, orchestrator
from backend.schemas import EventBrief


@pytest.fixture
def client():
    return TestClient(app)


def test_list_events_and_promotion(client, monkeypatch):
    uid = uuid.uuid4().hex[:8]
    event_id = f"evt_test_api_{uid}"
    run_id = f"run_test_api_{uid}"
    brief = EventBrief(
        title="AI Systems Orientation",
        topic="Machine Learning Architecture",
        city="Mumbai",
        starts_at=datetime(2026, 11, 15, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 11, 15, 19, 0, tzinfo=timezone.utc),
        budget_inr=30000,
        expected_attendance=100,
        venue_capacity=120,
        guest_count=1,
        mandatory_resources=["catering", "av"],
        dietary_requirements=["vegetarian_option"],
    )
    orchestrator.event_store.create_event(event_id, run_id, brief)

    # Test list events
    resp = client.get("/api/events")
    assert resp.status_code == 200
    events = resp.json()
    assert any(e["event_id"] == event_id for e in events)

    # Test promotion
    resp = client.get(f"/api/events/{event_id}/promotion")
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_id"] == event_id
    assert data["status"] == "DRAFT_SIMULATED"
    assert "poster_copy" in data
    assert "reel_storyboard" in data
    assert len(data["reel_storyboard"]) >= 3
