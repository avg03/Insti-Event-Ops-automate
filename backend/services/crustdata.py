"""Async Crustdata adapter for guest identity discovery.

Only this module talks to Crustdata.  It deliberately excludes contact fields from
normalised records because the hackathon permits identity research, not outreach.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal

import httpx
from pydantic import BaseModel, Field

_PERSON_LOOKUP_CACHE: dict[str, tuple[str, dict[str, Any]]] = {}

try:  # Integration owner will provide this module on the integrated branch.
    from backend.app.schemas import EvidenceRef, GuestCandidate
except (ImportError, ModuleNotFoundError):
    Mode = Literal["LIVE_DATA", "SIMULATED"]

    class EvidenceRef(BaseModel):
        provider: str
        source_id: str
        collected_at: datetime
        claim: str
        support: str
        mode: Mode

    class GuestCandidate(BaseModel):
        id: str
        event_id: str
        canonical_person_id: str | None
        display_name: str
        current_title: str | None
        company_name: str | None
        relevance_score: float = Field(ge=0, le=1)
        evidence: list[EvidenceRef]
        invitation_status: Literal[
            "DISCOVERED",
            "INVITED",
            "CONDITIONAL",
            "DECLINED",
            "ACCEPTED",
            "CONFIRMED_SIMULATED",
            "CANCELLED",
        ] = "DISCOVERED"


class CrustdataError(RuntimeError):
    """Base provider error with a stable machine-readable classification."""

    def __init__(self, message: str, *, code: str = "PROVIDER_FAILURE") -> None:
        super().__init__(message)
        self.code = code


class CrustdataRateLimitError(CrustdataError):
    def __init__(self, message: str = "Crustdata rate limit exhausted") -> None:
        super().__init__(message, code="RATE_LIMITED")


class CrustdataResponseError(CrustdataError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="INVALID_RESPONSE")


class UnsupportedEnrichmentIdentifier(CrustdataError):
    def __init__(self, person_id: str) -> None:
        super().__init__(
            f"Person {person_id!r} has no documented enrichment match input",
            code="UNSUPPORTED_IDENTIFIER",
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _first(mapping: dict[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value: Any = mapping
        for part in path:
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = value[part]
        if value not in (None, "", [], {}):
            return value
    return None


def _current_employment(profile: dict[str, Any]) -> dict[str, Any]:
    current = _first(
        profile,
        ("experience", "employment_details", "current"),
        ("employment_details", "current"),
    )
    if isinstance(current, list) and current:
        return current[0] if isinstance(current[0], dict) else {}
    return current if isinstance(current, dict) else {}


def _profile_url(profile: dict[str, Any]) -> str | None:
    value = _first(
        profile,
        ("basic_profile", "professional_network_url"),
        ("basic_profile", "professional_network_profile_url"),
        ("basic_profile", "linkedin_url"),
        ("basic_profile", "linkedin_profile_url"),
        ("linkedin_profile_url",),
        ("professional_network_profile_url",),
    )
    return str(value) if value else None


def normalize_person_profile(
    profile: dict[str, Any],
    event_id: str,
    *,
    collected_at: datetime | None = None,
) -> GuestCandidate:
    """Convert search/enrich records into the authoritative shared contract."""
    if not isinstance(profile, dict):
        raise CrustdataResponseError("Person profile must be an object")
    collected_at = collected_at or _utcnow()
    basic = profile.get("basic_profile") if isinstance(profile.get("basic_profile"), dict) else {}
    employment = _current_employment(profile)
    canonical = _first(profile, ("crustdata_person_id",), ("person_id",), ("id",))
    canonical_id = str(canonical) if canonical is not None else None
    name = _first(profile, ("basic_profile", "name"), ("name",), ("full_name",))
    display_name = str(name).strip() if name else "Unknown professional"
    title = _first(
        profile,
        ("basic_profile", "current_title"),
        ("basic_profile", "headline"),
        ("current_title",),
    ) or employment.get("title")
    company = employment.get("name") or employment.get("company_name") or _first(
        profile, ("current_company", "name"), ("company_name",)
    )
    identity = canonical_id or _profile_url(profile) or f"{display_name}|{title or ''}|{company or ''}"
    candidate_id = "guest_" + hashlib.sha256(str(identity).encode()).hexdigest()[:16]

    evidence: list[EvidenceRef] = []
    source_id = canonical_id or candidate_id
    evidence.append(
        EvidenceRef(
            provider="CRUSTDATA",
            source_id=source_id,
            collected_at=collected_at,
            claim=f"Professional identity returned for {display_name}",
            support="crustdata_person_id" if canonical_id else "basic_profile",
            mode="LIVE_DATA",
        )
    )
    if title:
        evidence.append(
            EvidenceRef(
                provider="CRUSTDATA",
                source_id=source_id,
                collected_at=collected_at,
                claim=f"Current professional title: {title}",
                support="basic_profile.current_title or experience.employment_details.current[0].title",
                mode="LIVE_DATA",
            )
        )
    if company:
        evidence.append(
            EvidenceRef(
                provider="CRUSTDATA",
                source_id=source_id,
                collected_at=collected_at,
                claim=f"Current company: {company}",
                support="experience.employment_details.current[0].name",
                mode="LIVE_DATA",
            )
        )
    for field in ("skills", "summary", "headline"):
        value = basic.get(field) or profile.get(field)
        if value:
            rendered = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
            evidence.append(
                EvidenceRef(
                    provider="CRUSTDATA",
                    source_id=source_id,
                    collected_at=collected_at,
                    claim=f"Professional {field}: {rendered[:500]}",
                    support=f"basic_profile.{field}",
                    mode="LIVE_DATA",
                )
            )

    return GuestCandidate(
        id=candidate_id,
        event_id=event_id,
        canonical_person_id=canonical_id,
        display_name=display_name,
        current_title=str(title) if title else None,
        company_name=str(company) if company else None,
        relevance_score=0.0,
        evidence=evidence,
    )


class CrustdataClient:
    PERSON_SEARCH_PATH = "/person/search"
    PERSON_ENRICH_PATH = "/person/enrich"
    COMPANY_SEARCH_PATH = "/company/search"
    COMPANY_ENRICH_PATH = "/company/enrich"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        timeout_seconds: float = 15.0,
        max_attempts: int = 3,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.api_key = api_key or os.getenv("CRUSTDATA_API_KEY")
        self.base_url = (base_url or os.getenv("CRUSTDATA_API_BASE", "https://api.crustdata.com")).rstrip("/")
        self.api_version = api_version or os.getenv("CRUSTDATA_API_VERSION", "2025-11-01")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self._client = client
        self._owns_client = client is None
        self._sleep = sleep
        self._person_cache: dict[str, tuple[str, dict[str, Any]]] = {}

    async def __aenter__(self) -> "CrustdataClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise CrustdataError("CRUSTDATA_API_KEY is not configured", code="NOT_CONFIGURED")
        return {
            "authorization": f"Bearer {self.api_key}",
            "x-api-version": self.api_version,
            "content-type": "application/json",
        }

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds)
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = await self._client.post(path, json=payload, headers=self._headers())
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    await self._sleep(0.15 * (2**attempt))
                    continue
                raise CrustdataError("Crustdata request timed out or failed in transit", code="TIMEOUT") from exc
            if response.status_code == 429:
                if attempt + 1 < self.max_attempts:
                    retry_after = response.headers.get("retry-after", "0")
                    try:
                        delay = min(float(retry_after), 2.0)
                    except ValueError:
                        delay = 0.15 * (2**attempt)
                    await self._sleep(delay)
                    continue
                raise CrustdataRateLimitError()
            if response.status_code >= 500 and attempt + 1 < self.max_attempts:
                await self._sleep(0.15 * (2**attempt))
                continue
            if response.status_code in (401, 403):
                raise CrustdataError("Crustdata authentication failed", code="AUTH_FAILED")
            if response.is_error:
                raise CrustdataError(
                    f"Crustdata returned HTTP {response.status_code}", code="HTTP_ERROR"
                )
            try:
                return response.json()
            except ValueError as exc:
                raise CrustdataResponseError("Crustdata returned malformed JSON") from exc
        raise CrustdataError("Crustdata request failed", code="PROVIDER_FAILURE") from last_error

    async def search_speakers(
        self, event_id: str, topic: str, max_results: int = 10
    ) -> list[GuestCandidate]:
        if not topic.strip() or max_results < 1:
            return []
        profiles: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(profiles) < max_results:
            payload: dict[str, Any] = {
                "filters": {
                    "op": "and",
                    "conditions": [
                        {
                            "field": "experience.employment_details.current.title",
                            "type": "(.)",
                            "value": topic.strip(),
                        }
                    ],
                },
                "limit": min(100, max_results - len(profiles)),
            }
            if cursor:
                payload["cursor"] = cursor
            data = await self._post(self.PERSON_SEARCH_PATH, payload)
            if not isinstance(data, dict) or not isinstance(data.get("profiles"), list):
                raise CrustdataResponseError("Person search response has no profiles list")
            page = [item for item in data["profiles"] if isinstance(item, dict)]
            profiles.extend(page)
            cursor = data.get("next_cursor")
            if not cursor or not page:
                break

        result: list[GuestCandidate] = []
        seen: set[str] = set()
        for profile in profiles:
            candidate = normalize_person_profile(profile, event_id)
            identity = candidate.canonical_person_id or re.sub(
                r"\W+", "", f"{candidate.display_name}{candidate.current_title}{candidate.company_name}".lower()
            )
            if identity in seen:
                continue
            seen.add(identity)
            result.append(candidate)
            if candidate.canonical_person_id:
                self._person_cache[candidate.canonical_person_id] = (event_id, profile)
                _PERSON_LOOKUP_CACHE[candidate.canonical_person_id] = (event_id, profile)
            if len(result) >= max_results:
                break
        return result

    async def enrich_speaker(self, canonical_person_id: str) -> GuestCandidate:
        cached = self._person_cache.get(str(canonical_person_id))
        if not cached:
            raise UnsupportedEnrichmentIdentifier(str(canonical_person_id))
        event_id, search_profile = cached
        url = _profile_url(search_profile)
        if not url:
            raise UnsupportedEnrichmentIdentifier(str(canonical_person_id))
        data = await self._post(
            self.PERSON_ENRICH_PATH,
            {
                "professional_network_profile_urls": [url],
                "fields": ["basic_profile", "experience", "education"],
            },
        )
        if not isinstance(data, list) or not data:
            raise CrustdataResponseError("Person enrich response must be a non-empty list")
        matches = data[0].get("matches") if isinstance(data[0], dict) else None
        if not isinstance(matches, list) or not matches or not isinstance(matches[0], dict):
            raise CrustdataResponseError("Person enrich returned no match")
        profile = matches[0].get("person_data")
        if not isinstance(profile, dict):
            raise CrustdataResponseError("Person enrich match has no person_data")
        return normalize_person_profile(profile, event_id)

    async def search_companies(self, filters: dict[str, Any], *, limit: int = 10) -> list[dict[str, Any]]:
        data = await self._post(
            self.COMPANY_SEARCH_PATH,
            {"filters": filters, "limit": max(1, min(limit, 100))},
        )
        if not isinstance(data, dict) or not isinstance(data.get("companies"), list):
            raise CrustdataResponseError("Company search response has no companies list")
        return [item for item in data["companies"] if isinstance(item, dict)]

    async def enrich_company(self, domain: str) -> dict[str, Any]:
        data = await self._post(
            self.COMPANY_ENRICH_PATH,
            {"domains": [domain], "fields": ["basic_info", "headcount", "funding", "hiring"]},
        )
        if not isinstance(data, list) or not data:
            raise CrustdataResponseError("Company enrich response must be a non-empty list")
        return data[0]


async def search_speakers(event_id: str, topic: str, max_results: int = 10) -> list[GuestCandidate]:
    async with CrustdataClient() as client:
        return await client.search_speakers(event_id, topic, max_results)


async def enrich_speaker(canonical_person_id: str) -> GuestCandidate:
    async with CrustdataClient() as client:
        cached = _PERSON_LOOKUP_CACHE.get(str(canonical_person_id))
        if cached:
            client._person_cache[str(canonical_person_id)] = cached
        return await client.enrich_speaker(canonical_person_id)


__all__ = [
    "CrustdataClient",
    "CrustdataError",
    "CrustdataRateLimitError",
    "CrustdataResponseError",
    "EvidenceRef",
    "GuestCandidate",
    "UnsupportedEnrichmentIdentifier",
    "enrich_speaker",
    "normalize_person_profile",
    "search_speakers",
]
