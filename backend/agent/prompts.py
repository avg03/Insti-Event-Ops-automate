"""Prompts for LLM-assisted event planning and negotiation."""

def speaker_invitation_prompt(
    speaker_name: str,
    speaker_title: str,
    company: str,
    event_title: str,
    topic: str,
    date_str: str,
    honorarium_inr: int,
) -> str:
    return f"""Draft a professional, personalized speaker invitation for an academic & industry technology summit.

Speaker Name: {speaker_name}
Current Role: {speaker_title} at {company}
Event: {event_title}
Topic: {topic}
Date: {date_str}
Offered Honorarium: INR {honorarium_inr}

Requirements:
- Acknowledge their specific domain experience at {company}.
- Keep tone hospitable, academically grounded, and respectful.
- Mention the proposed session duration and honorarium.
- Maximum 150 words.
"""


def promotional_tagline_prompt(title: str, topic: str, speaker_names: list[str]) -> str:
    speakers_text = ", ".join(speaker_names) if speaker_names else "Distinguished Industry Experts"
    return f"""Create a compelling headline and viral event tagline for a campus technology summit at IIT Bombay.

Title: {title}
Topic: {topic}
Speakers: {speakers_text}

Format as:
HEADLINE: <catchy headline>
TAGLINE: <one sentence punchy hook>
"""
