"""Guest ranking, simulated negotiation, booking, and recovery workflow."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from backend.services.crustdata import EvidenceRef, GuestCandidate, search_speakers
from backend.simulator.guest_simulator import SimulatedGuestChannel

_channel: SimulatedGuestChannel | None = None


def get_guest_channel() -> SimulatedGuestChannel:
    global _channel
    if _channel is None:
        _channel = SimulatedGuestChannel()
    return _channel


def set_guest_channel(channel: SimulatedGuestChannel | None) -> None:
    """Dependency injection hook for tests and the integration owner."""
    global _channel
    _channel = channel


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9+#]+", value.lower()) if len(token) >= 3}


def rank_guest_candidate(
    candidate: GuestCandidate,
    topic: str,
    constraints: dict[str, Any] | None = None,
) -> tuple[float, str]:
    """Deterministically score only professional relevance evidence (0..1)."""
    constraints = constraints or {}
    topic_tokens = _tokens(topic)
    evidence_text = " ".join(
        [candidate.current_title or "", candidate.company_name or ""]
        + [f"{item.claim} {item.support}" for item in candidate.evidence]
    )
    evidence_tokens = _tokens(evidence_text)
    overlap = topic_tokens & evidence_tokens
    topic_score = len(overlap) / max(1, min(len(topic_tokens), 8))

    role_text = (candidate.current_title or "").lower()
    desired_roles = {str(role).lower() for role in constraints.get("desired_roles", [])}
    professional_roles = {
        "founder", "engineer", "scientist", "research", "professor", "director",
        "head", "lead", "architect", "mentor", "executive", "developer",
    }
    role_hits = [role for role in professional_roles | desired_roles if role and role in role_text]
    role_score = min(1.0, len(role_hits) / 2) if role_hits else 0.0
    experience_evidence = sum(
        1 for item in candidate.evidence if any(word in item.claim.lower() for word in ("title", "experience", "skill", "professional"))
    )
    experience_score = min(1.0, experience_evidence / 3)
    company_score = 1.0 if candidate.company_name else 0.0
    score = round(min(1.0, 0.55 * topic_score + 0.25 * role_score + 0.15 * experience_score + 0.05 * company_score), 4)
    explanation = (
        f"Matched topic terms: {', '.join(sorted(overlap)) or 'none'}; "
        f"role evidence: {', '.join(sorted(role_hits)) or 'limited'}; "
        f"professional evidence records: {experience_evidence}; "
        f"company evidence: {'present' if candidate.company_name else 'missing'}."
    )
    return score, explanation


def rank_candidates(
    candidates: Iterable[GuestCandidate], topic: str, constraints: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        score, explanation = rank_guest_candidate(candidate, topic, constraints)
        candidate.relevance_score = score
        ranked.append({"candidate": candidate, "explanation": explanation})
    return sorted(ranked, key=lambda item: (-item["candidate"].relevance_score, item["candidate"].id))


async def send_guest_invitation(
    event_id: str,
    candidate_id: str,
    terms: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    return await get_guest_channel().send_invitation(event_id, candidate_id, terms, idempotency_key)


async def poll_guest_reply(thread_id: str) -> dict[str, Any] | None:
    return await get_guest_channel().get_replies(thread_id)


async def confirm_guest_booking(
    event_id: str,
    candidate_id: str,
    slot: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    return await get_guest_channel().confirm_calendar(event_id, candidate_id, slot, idempotency_key)


def _slot_start_time(slot: dict[str, Any]) -> str:
    starts_at = str(slot.get("starts_at", ""))
    if "T" in starts_at:
        return starts_at.split("T", 1)[1][:5]
    return starts_at[:5]


def _choose_slot(slots: list[dict[str, Any]], start_after: str | None = None) -> dict[str, Any] | None:
    for slot in slots:
        if not start_after or _slot_start_time(slot) >= start_after:
            return dict(slot)
    return None


def _candidate_dict(candidate: GuestCandidate) -> dict[str, Any]:
    return candidate.model_dump(mode="json") if hasattr(candidate, "model_dump") else candidate.dict()


async def _coordinate_candidate(
    event_id: str,
    candidate: GuestCandidate,
    constraints: dict[str, Any],
    invitation_number: int,
    spent_inr: int,
) -> dict[str, Any]:
    slots = [dict(slot) for slot in constraints.get("slots", [])]
    if not slots and constraints.get("slot"):
        slots = [dict(constraints["slot"])]
    if not slots:
        return {"outcome": "BLOCKED", "reason": "No guest session slot was supplied"}
    slot = _choose_slot(slots)
    max_fee = int(constraints.get("max_honorarium_inr", 0))
    total_budget = int(constraints.get("guest_budget_inr", max_fee * max(1, int(constraints.get("required_count", 1)))))
    offered_fee = int(constraints.get("initial_honorarium_inr", 0))
    terms = {
        "slot": slot,
        "honorarium_inr": offered_fee,
        "invitation_text": (
            f"Hello {candidate.display_name}, would you join our {constraints.get('topic', 'event')} "
            f"session at {slot.get('starts_at')}? This is a local simulation and is not real outreach."
        ),
        "mode": "SIMULATED",
    }
    invitation = await send_guest_invitation(
        event_id, candidate.id, terms, f"{event_id}:{candidate.id}:invite:{invitation_number}"
    )
    candidate.invitation_status = "INVITED"
    reply = await poll_guest_reply(invitation["thread_id"])
    if reply is None or reply.get("response") == "NO_RESPONSE":
        return {"outcome": "PENDING", "candidate": candidate, "thread_id": invitation["thread_id"]}
    response = str(reply.get("response", "")).upper()
    if response in {"DECLINED", "CANCELLED"}:
        candidate.invitation_status = "CANCELLED" if response == "CANCELLED" else "DECLINED"
        return {"outcome": response, "candidate": candidate, "reply": reply}

    agreed_fee = offered_fee
    agreed_slot = slot
    if response == "CONDITIONAL":
        candidate.invitation_status = "CONDITIONAL"
        conditions = dict(reply.get("conditions") or {})
        requested_fee = int(conditions.get("honorarium_inr", 0))
        requested_start = conditions.get("start_after")
        alternative = _choose_slot(slots, str(requested_start) if requested_start else None)
        if requested_fee > max_fee:
            return {
                "outcome": "UNAVAILABLE",
                "candidate": candidate,
                "reason": f"Requested honorarium INR {requested_fee} exceeds cap INR {max_fee}",
            }
        if spent_inr + requested_fee > total_budget:
            return {"outcome": "UNAVAILABLE", "candidate": candidate, "reason": "Guest budget would be exceeded"}
        if alternative is None:
            return {"outcome": "UNAVAILABLE", "candidate": candidate, "reason": "No slot meets requested availability"}
        agreed_fee, agreed_slot = requested_fee, alternative
        revised = {"slot": agreed_slot, "honorarium_inr": agreed_fee, "mode": "SIMULATED"}
        await get_guest_channel().send_counteroffer(
            invitation["thread_id"], candidate.id, revised, round_number=1
        )
        reply = await poll_guest_reply(invitation["thread_id"])
        if not reply or reply.get("response") != "ACCEPTED":
            candidate.invitation_status = "DECLINED"
            return {"outcome": "DECLINED", "candidate": candidate, "reply": reply}
        response = "ACCEPTED"

    if response == "ACCEPTED":
        accepted_conditions = dict(reply.get("conditions") or {})
        agreed_fee = max(agreed_fee, int(accepted_conditions.get("honorarium_inr", 0)))
        if agreed_fee > max_fee or spent_inr + agreed_fee > total_budget:
            candidate.invitation_status = "DECLINED"
            return {"outcome": "UNAVAILABLE", "candidate": candidate, "reason": "Accepted terms violate guest budget policy"}
        candidate.invitation_status = "ACCEPTED"
        booking_slot = dict(agreed_slot) | {"honorarium_inr": agreed_fee}
        booking = await confirm_guest_booking(
            event_id,
            candidate.id,
            booking_slot,
            f"{event_id}:{candidate.id}:booking:{invitation_number}",
        )
        candidate.invitation_status = "CONFIRMED_SIMULATED"
        return {
            "outcome": "CONFIRMED_SIMULATED",
            "candidate": candidate,
            "booking": booking,
            "thread_id": invitation["thread_id"],
            "honorarium_inr": agreed_fee,
        }
    return {"outcome": "UNAVAILABLE", "candidate": candidate, "reason": f"Unsupported reply {response}"}


async def coordinate_event_guests(
    event_id: str,
    topic: str,
    required_count: int,
    constraints: dict[str, Any],
) -> dict[str, Any]:
    """Discover and coordinate guests; safe for direct use as a LangGraph node."""
    if required_count < 0:
        raise ValueError("required_count must be non-negative")
    constraints = dict(constraints)
    constraints["topic"] = topic
    constraints["required_count"] = required_count
    max_results = int(constraints.get("max_candidates", max(10, required_count * 3)))
    candidates = await search_speakers(event_id, topic, max_results=max_results)
    ranked = rank_candidates(candidates, topic, constraints)
    scenarios = constraints.get("guest_scenarios", {})
    for candidate_id, scenario in scenarios.items():
        get_guest_channel().set_candidate_scenario(candidate_id, scenario)

    confirmed: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    spent = 0
    max_attempts = min(len(ranked), int(constraints.get("max_invitation_attempts", max(3, required_count * 3))))
    attempted: set[str] = set()
    used_slot_starts: set[str] = set()
    for index, entry in enumerate(ranked[:max_attempts], start=1):
        if len(confirmed) >= required_count:
            break
        candidate = entry["candidate"]
        attempted.add(candidate.id)
        candidate_constraints = dict(constraints)
        candidate_constraints["slots"] = [
            slot
            for slot in constraints.get("slots", [])
            if str(slot.get("starts_at")) not in used_slot_starts
        ]
        result = await _coordinate_candidate(event_id, candidate, candidate_constraints, index, spent)
        if result["outcome"] == "CONFIRMED_SIMULATED":
            spent += int(result["honorarium_inr"])
            used_slot_starts.add(str(result["booking"]["slot"].get("starts_at")))
            confirmed.append(
                {
                    "candidate": _candidate_dict(candidate),
                    "booking": result["booking"],
                    "ranking_explanation": entry["explanation"],
                }
            )
        elif result["outcome"] == "PENDING":
            pending.append({"candidate": _candidate_dict(candidate), "thread_id": result["thread_id"]})
        else:
            issues.append(
                {
                    "candidate_id": candidate.id,
                    "type": result["outcome"],
                    "message": result.get("reason") or (result.get("reply") or {}).get("text", "Guest unavailable"),
                }
            )

    backups = [
        {"candidate": _candidate_dict(item["candidate"]), "ranking_explanation": item["explanation"]}
        for item in ranked
        if item["candidate"].id not in attempted
    ]
    enough = len(confirmed) >= required_count
    if not enough:
        issues.append(
            {
                "type": "NO_FEASIBLE_GUEST",
                "message": f"Confirmed {len(confirmed)} of {required_count} required simulated guests",
            }
        )
    evidence_ids = sorted(
        {
            evidence.source_id
            for entry in confirmed
            for evidence in next(
                item["candidate"].evidence for item in ranked if item["candidate"].id == entry["candidate"]["id"]
            )
        }
    )
    return {
        "event_id": event_id,
        "confirmed_guests": confirmed,
        "backup_candidates": backups,
        "pending_guests": pending,
        "issues": issues,
        "evidence_ids": evidence_ids,
        "guest_honorarium_committed_inr": spent,
        "status": "COMPLETE" if enough else "BLOCKED",
    }


async def recover_guest(
    event_id: str,
    cancelled_candidate_id: str,
    backup_candidates: list[GuestCandidate | dict[str, Any]],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    """Cancel an active booking and coordinate the best eligible backup."""
    cancelled = await get_guest_channel().cancel_booking(event_id, cancelled_candidate_id)
    active_starts = {
        str(json.loads(row["slot_json"]).get("starts_at"))
        for row in get_guest_channel().inspect_event(event_id)["bookings"]
        if row["status"] == "CONFIRMED_SIMULATED"
    }
    recovery_constraints = dict(constraints)
    recovery_constraints["slots"] = [
        slot for slot in constraints.get("slots", []) if str(slot.get("starts_at")) not in active_starts
    ]
    attempts = min(len(backup_candidates), int(constraints.get("max_recovery_attempts", 3)))
    issues: list[dict[str, Any]] = []
    for index, value in enumerate(backup_candidates[:attempts], start=1):
        candidate_data = value.get("candidate", value) if isinstance(value, dict) else value
        candidate = candidate_data if isinstance(candidate_data, GuestCandidate) else GuestCandidate.model_validate(candidate_data)
        result = await _coordinate_candidate(event_id, candidate, recovery_constraints, 1000 + index, 0)
        if result["outcome"] == "CONFIRMED_SIMULATED":
            return {
                "event_id": event_id,
                "status": "RECOVERED",
                "cancelled_booking": cancelled,
                "replacement": {
                    "candidate": _candidate_dict(candidate),
                    "booking": result["booking"],
                },
                "issues": issues,
            }
        issues.append(
            {"candidate_id": candidate.id, "type": result["outcome"], "message": result.get("reason", "Backup unavailable")}
        )
    return {
        "event_id": event_id,
        "status": "BLOCKED",
        "cancelled_booking": cancelled,
        "replacement": None,
        "issues": issues
        + [{"type": "NO_FEASIBLE_BACKUP", "message": "No eligible backup accepted feasible terms"}],
    }


__all__ = [
    "confirm_guest_booking",
    "coordinate_event_guests",
    "poll_guest_reply",
    "rank_candidates",
    "rank_guest_candidate",
    "recover_guest",
    "send_guest_invitation",
    "set_guest_channel",
]
