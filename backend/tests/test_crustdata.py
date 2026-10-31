from datetime import datetime, timezone

import httpx
import pytest

from backend.services.crustdata import (
    CrustdataClient,
    CrustdataRateLimitError,
    normalize_person_profile,
)


def test_crustdata_response_normalization_preserves_identity_and_evidence():
    profile = {
        "crustdata_person_id": 14540,
        "basic_profile": {"name": "Test Expert", "current_title": "AI Research Lead", "skills": ["ML", "AI"]},
        "experience": {"employment_details": {"current": [{"name": "Example Labs", "title": "AI Research Lead"}]}},
    }
    when = datetime(2026, 10, 31, tzinfo=timezone.utc)
    candidate = normalize_person_profile(profile, "evt_1", collected_at=when)
    assert candidate.canonical_person_id == "14540"
    assert candidate.display_name == "Test Expert"
    assert candidate.current_title == "AI Research Lead"
    assert candidate.company_name == "Example Labs"
    assert all(item.mode == "LIVE_DATA" for item in candidate.evidence)
    assert {item.source_id for item in candidate.evidence} == {"14540"}


def test_missing_professional_information_is_not_invented():
    candidate = normalize_person_profile({"crustdata_person_id": "p1", "basic_profile": {"name": "Sparse Person"}}, "evt")
    assert candidate.current_title is None
    assert candidate.company_name is None
    assert candidate.display_name == "Sparse Person"
    claims = " ".join(item.claim for item in candidate.evidence)
    assert "Current professional title" not in claims
    assert "Current company" not in claims


@pytest.mark.asyncio
async def test_duplicate_candidates_are_deduplicated_by_canonical_identity():
    payload = {
        "profiles": [
            {"crustdata_person_id": 7, "basic_profile": {"name": "Same Person"}},
            {"crustdata_person_id": 7, "basic_profile": {"name": "Same Person Updated"}},
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.crustdata.com")
    client = CrustdataClient(api_key="test", client=http, sleep=_no_sleep)
    results = await client.search_speakers("evt", "AI", 10)
    await http.aclose()
    assert len(results) == 1
    assert results[0].canonical_person_id == "7"


@pytest.mark.asyncio
async def test_enrich_uses_documented_profile_url_bridge_and_headers():
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/person/search":
            return httpx.Response(
                200,
                json={
                    "profiles": [
                        {
                            "crustdata_person_id": 8,
                            "basic_profile": {
                                "name": "Search Name",
                                "professional_network_profile_url": "https://professional.example/person/8",
                            },
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json=[
                {
                    "matched_on": "https://professional.example/person/8",
                    "matches": [
                        {
                            "person_data": {
                                "crustdata_person_id": 8,
                                "basic_profile": {"name": "Enriched Name", "current_title": "AI Lead"},
                            }
                        }
                    ],
                }
            ],
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.crustdata.com")
    client = CrustdataClient(api_key="secret-test-key", client=http, sleep=_no_sleep)
    await client.search_speakers("evt", "AI", 1)
    enriched = await client.enrich_speaker("8")
    await http.aclose()
    assert enriched.display_name == "Enriched Name"
    assert [call.url.path for call in calls] == ["/person/search", "/person/enrich"]
    assert all(call.headers["x-api-version"] == "2025-11-01" for call in calls)
    assert all(call.headers["authorization"] == "Bearer secret-test-key" for call in calls)


async def _no_sleep(_: float) -> None:
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "rate_limit"])
async def test_timeout_or_429_uses_bounded_retries(failure: str):
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if failure == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(429, headers={"retry-after": "0"}, json={"detail": "limited"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.crustdata.com")
    client = CrustdataClient(api_key="test", client=http, max_attempts=3, sleep=_no_sleep)
    expected = CrustdataRateLimitError if failure == "rate_limit" else Exception
    with pytest.raises(expected) as error:
        await client.search_speakers("evt", "AI", 2)
    await http.aclose()
    assert calls == 3
    if failure == "timeout":
        assert getattr(error.value, "code", None) == "TIMEOUT"

