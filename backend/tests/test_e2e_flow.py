"""End-to-end test verifying full workflow from HTTP creation to verifier pass and recovery."""

import asyncio
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from backend.main import app, orchestrator
from backend.schemas import EventBrief


def test_full_e2e_event_lifecycle():
    client = TestClient(app)
    
    # 1. Create Event via HTTP API
    payload = {
        "title": "IIT Bombay Autonomous Systems Colloquium",
        "topic": "Machine Learning",
        "city": "Mumbai",
        "timezone": "Asia/Kolkata",
        "starts_at": "2026-11-20T16:00:00+05:30",
        "ends_at": "2026-11-20T19:00:00+05:30",
        "budget_inr": 25000,
        "expected_attendance": 120,
        "venue_capacity": 150,
        "guest_count": 2,
        "mandatory_resources": ["catering", "av"],
        "dietary_requirements": ["vegetarian_option"],
        "promotion_requested": True,
    }
    create_resp = client.post("/api/events", json=payload)
    assert create_resp.status_code == 202
    data = create_resp.json()
    event_id = data["event_id"]
    assert event_id.startswith("evt_")
    assert data["status"] == "PLANNING"

    # 2. Run orchestrator safely (synchronously in test)
    asyncio.run(orchestrator.run_event(event_id))

    # 3. Verify event state via GET /api/events/{id}
    state_resp = client.get(f"/api/events/{event_id}")
    assert state_resp.status_code == 200
    state = state_resp.json()
    assert state["status"] in ("READY_IN_SANDBOX", "READY")
    assert state["simulation_mode"] is True
    assert len(state["orders"]) > 0

    # 4. Verify timeline via GET /api/events/{id}/timeline
    timeline_resp = client.get(f"/api/events/{event_id}/timeline")
    assert timeline_resp.status_code == 200
    timeline = timeline_resp.json()["items"]
    assert len(timeline) >= 4
    actions = [item["action"] for item in timeline]
    assert "EVENT_CREATED" in actions
    assert "VALIDATE_EVENT" in actions
    assert "GENERATE_EVENT_PLAN" in actions

    # 5. Verify Promotion campaign via GET /api/events/{id}/promotion
    promo_resp = client.get(f"/api/events/{event_id}/promotion")
    assert promo_resp.status_code == 200
    promo = promo_resp.json()
    assert promo["status"] == "DRAFT_SIMULATED"
    assert len(promo["reel_storyboard"]) == 4
    assert len(promo["poster_copy"]["featured_speakers"]) >= 1

    # 6. Simulate Vendor Cancellation (Disruption recovery)
    active_order = [o for o in state["orders"] if o["status"] == "CONFIRMED_SIMULATED"][0]
    disrupt_resp = client.post(
        f"/api/events/{event_id}/simulate",
        json={"event_type": "VENDOR_CANCELLED", "target_id": active_order["id"]},
    )
    assert disrupt_resp.status_code == 202
    disrupt_result = disrupt_resp.json()
    assert disrupt_result["status"] in ("READY_IN_SANDBOX", "READY")
    assert disrupt_result["recovery"]["status"] == "RECOVERED"
    assert disrupt_result["recovery"]["replacement_order"] is not None

    # 7. Check final event state after recovery
    updated_state = client.get(f"/api/events/{event_id}").json()
    assert updated_state["status"] in ("READY_IN_SANDBOX", "READY")
    
    # Old order should be cancelled, replacement order should be confirmed
    order_statuses = {o["id"]: o["status"] for o in updated_state["orders"]}
    assert order_statuses[active_order["id"]] == "CANCELLED"
    active_orders = [o for o in updated_state["orders"] if o["status"] == "CONFIRMED_SIMULATED"]
    assert len(active_orders) >= 1
