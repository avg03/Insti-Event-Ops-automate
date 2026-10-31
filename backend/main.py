"""FastAPI entry point for EventOps Autopilot."""

from __future__ import annotations

import os
import uuid
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from backend.agent.graph import EventOpsOrchestrator
from backend.agent.model import llm_client
from backend.schemas import (
    DisruptionRequest,
    EventBrief,
    EventCreateResponse,
    ServiceReadiness,
    TimelineResponse,
)
from backend.services.promotion import generate_event_promotion

app = FastAPI(title="EventOps Autopilot", version="1.0.0")

default_origins = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]
env_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
cors_origins = list(set(default_origins + env_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = EventOpsOrchestrator()


async def _run_safely(event_id: str) -> None:
    try:
        await orchestrator.run_event(event_id)
    except Exception:
        # run_event persists the failure and audit record.  Background execution
        # must not turn the already accepted HTTP response into a transport error.
        return


@app.get("/api/system/status")
async def get_system_status() -> dict[str, Any]:
    return {
        "status": "HEALTHY",
        "simulation_mode": True,
        "crustdata_configured": bool(os.getenv("CRUSTDATA_API_KEY")),
        "crustdata_api_base": os.getenv("CRUSTDATA_API_BASE", "https://api.crustdata.com"),
        "llm_provider": llm_client.active_provider,
        "llm_configured": llm_client.is_configured,
    }


@app.post(
    "/api/events",
    response_model=EventCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_event(brief: EventBrief, background_tasks: BackgroundTasks) -> EventCreateResponse:
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    orchestrator.event_store.create_event(event_id, run_id, brief)
    background_tasks.add_task(_run_safely, event_id)
    return EventCreateResponse(event_id=event_id, run_id=run_id, status="PLANNING")


@app.get("/api/events")
async def list_events(limit: int = Query(default=25, ge=1, le=100)) -> list[dict[str, Any]]:
    return orchestrator.event_store.list_events(limit=limit)


@app.get("/api/events/{event_id}")
async def get_event(event_id: str) -> dict[str, Any]:
    result = orchestrator.get_event_state(event_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return result


@app.get("/api/events/{event_id}/promotion")
async def get_promotion(event_id: str) -> dict[str, Any]:
    event = orchestrator.event_store.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return await generate_event_promotion(
        event_id=event_id,
        brief=event.get("brief") or {},
        guest_result=event.get("guest_result"),
        plan=event.get("plan"),
    )


@app.get("/api/events/{event_id}/timeline", response_model=TimelineResponse)
async def get_timeline(
    event_id: str, after_id: str | None = Query(default=None)
) -> TimelineResponse:
    try:
        items = orchestrator.get_timeline(event_id, after_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Event not found") from exc
    return TimelineResponse(items=items)


@app.post("/api/events/{event_id}/simulate", status_code=status.HTTP_202_ACCEPTED)
async def simulate_event(event_id: str, request: DisruptionRequest) -> dict[str, Any]:
    payload = request.model_dump(exclude_none=True)
    payload.pop("event_type", None)
    try:
        return await orchestrator.simulate_disruption(event_id, request.event_type, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Event or target not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/events/{event_id}/verify", response_model=ServiceReadiness)
async def verify_event(event_id: str) -> ServiceReadiness:
    try:
        result = orchestrator.verifier.verify(event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Event not found") from exc
    orchestrator.event_store.update_event(event_id, status=result.status)
    return result

