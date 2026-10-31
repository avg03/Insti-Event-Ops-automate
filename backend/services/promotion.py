"""Event promotional campaign generator (P1 feature).
Produces draft social copy, poster outlines, and reel storyboards.
All outputs are strictly marked DRAFT_SIMULATED.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.agent.model import llm_client
from backend.agent.prompts import promotional_tagline_prompt


async def generate_event_promotion(
    event_id: str,
    brief: dict[str, Any],
    guest_result: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate draft promotion assets for an event, enhanced by LLM when available."""
    title = brief.get("title", "Campus Technology Summit")
    topic = brief.get("topic", "Technology & Innovation")
    city = brief.get("city", "Mumbai")
    starts_at = brief.get("starts_at", "")
    ends_at = brief.get("ends_at", "")
    expected = brief.get("expected_attendance", 100)

    # Format dates
    start_str = starts_at
    if "T" in str(starts_at):
        try:
            dt = datetime.fromisoformat(str(starts_at).replace("Z", "+00:00"))
            start_str = dt.strftime("%B %d, %Y at %I:%M %p")
        except Exception:
            start_str = str(starts_at)

    confirmed_guests = []
    speaker_names = []
    if guest_result and isinstance(guest_result.get("confirmed_guests"), list):
        for item in guest_result["confirmed_guests"]:
            cand = item.get("candidate", item)
            name = cand.get("display_name", "Featured Expert")
            speaker_names.append(name)
            role = cand.get("current_title") or "Industry Leader"
            comp = cand.get("company_name") or ""
            line = f"{name} ({role}" + (f", {comp})" if comp else ")")
            confirmed_guests.append(line)

    guest_highlights = confirmed_guests or ["Distinguished Domain Practitioners", "Industry Experts"]

    hashtag_base = "".join(w.capitalize() for w in topic.split()[:3] if w.isalnum())
    hashtags = [
        f"#{hashtag_base}2026",
        f"#{city.replace(' ', '')}Events",
        "#InstiTech",
        "#CampusOps",
        "#AIInnovation",
    ]

    headline = f"{title}"
    subheadline = f"An exclusive deep dive into {topic}"

    # Try LLM enhancement if configured
    if llm_client.is_configured:
        try:
            prompt = promotional_tagline_prompt(title, topic, speaker_names)
            llm_text = await llm_client.generate_text(prompt)
            if llm_text:
                for line in llm_text.splitlines():
                    if line.upper().startswith("HEADLINE:"):
                        headline = line.split(":", 1)[1].strip()
                    elif line.upper().startswith("TAGLINE:"):
                        subheadline = line.split(":", 1)[1].strip()
        except Exception:
            pass

    poster_copy = {
        "headline": headline,
        "subheadline": subheadline,
        "date_and_venue": f"{start_str} | IIT Bombay Main Auditorium, {city}",
        "featured_speakers": guest_highlights,
        "key_takeaways": [
            f"Frontier developments and practical realities in {topic}",
            "Interactive Q&A and technical architecture breakdown",
            f"Curated networking session for {expected}+ student founders & researchers",
        ],
        "registration_cta": "Limited sandbox seating. Reserve your delegate pass now at insti-events.internal/rsvp",
        "hashtags": hashtags,
    }

    reel_storyboard = [
        {
            "scene": 1,
            "duration_seconds": 3,
            "visual": f"Fast-paced kinetic typography: '{title.upper()}' cutting to packed auditorium cheering.",
            "audio_voiceover": f"What happens when top practitioners in {topic} take the stage at IIT Bombay?",
            "onscreen_text": f"{title}\nIIT Bombay • {city}",
        },
        {
            "scene": 2,
            "duration_seconds": 4,
            "visual": "Split-screen candidate spotlight cards featuring verified Crustdata profile highlights.",
            "audio_voiceover": f"Meet our keynote lineup: {guest_highlights[0] if guest_highlights else 'Industry Leaders'}.",
            "onscreen_text": "VERIFIED INDUSTRY LEADERS\n[Crustdata Validated]",
        },
        {
            "scene": 3,
            "duration_seconds": 4,
            "visual": "B-roll of live technical debates, stage mic, audience taking notes, projector slides.",
            "audio_voiceover": "No generic overviews. Real case studies, verified benchmarks, and actionable architecture.",
            "onscreen_text": "DEEP DIVE • LIVE WORKSHOP • Q&A",
        },
        {
            "scene": 4,
            "duration_seconds": 4,
            "visual": "Graphic overlay of registration countdown timer with catering & seating perks badge.",
            "audio_voiceover": f"Only {expected} passes allocated. Registration closes once hall capacity is reached.",
            "onscreen_text": f"CAPACITY: {expected} DELEGATES\nFree RSVP Required",
        },
    ]

    schedule_summary = []
    if plan and isinstance(plan.get("guest_slots"), list) and plan["guest_slots"]:
        for idx, slot in enumerate(plan["guest_slots"]):
            speaker = confirmed_guests[idx] if idx < len(confirmed_guests) else f"Session {idx+1} Keynote"
            schedule_summary.append({
                "time": f"{slot.get('starts_at', '')} - {slot.get('ends_at', '')}",
                "session": f"Technical Session {idx + 1}",
                "speaker": speaker,
            })
    else:
        schedule_summary.append({
            "time": "16:00 - 17:15",
            "session": "Keynote & Research Foundations",
            "speaker": guest_highlights[0] if guest_highlights else "Keynote Speaker",
        })
        schedule_summary.append({
            "time": "17:30 - 18:45",
            "session": "Fireside Chat & Technical Panel",
            "speaker": guest_highlights[1] if len(guest_highlights) > 1 else "Industry Panelists",
        })

    return {
        "event_id": event_id,
        "status": "DRAFT_SIMULATED",
        "mode": "SIMULATED",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "headline": f"{title} — Official Delegate Briefing",
        "poster_copy": poster_copy,
        "reel_storyboard": reel_storyboard,
        "schedule_summary": schedule_summary,
        "llm_engine": llm_client.active_provider,
        "disclaimer": "This campaign brief is simulated for campus ops planning. No public ads or social broadcasts have been deployed.",
    }
