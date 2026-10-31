"""Authoritative shared contracts and schemas as defined in CONTRACTS.md.
All monetary amounts are integers in INR (no floats).
"""

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator

Mode = Literal['LIVE_DATA', 'SIMULATED']


class EventBrief(BaseModel):
    title: str
    topic: str
    city: str = 'Mumbai'
    timezone: str = 'Asia/Kolkata'
    starts_at: datetime
    ends_at: datetime
    budget_inr: int = Field(gt=0)
    expected_attendance: int = Field(gt=0)
    venue_capacity: int = Field(gt=0)
    guest_count: int = Field(default=2, ge=0)
    mandatory_resources: list[str] = ['catering', 'av']
    dietary_requirements: list[str] = []
    promotion_requested: bool = True

    @model_validator(mode='after')
    def check_schedule(self):
        if self.ends_at <= self.starts_at:
            raise ValueError('ends_at must be after starts_at')
        return self


class EvidenceRef(BaseModel):
    provider: str            # CRUSTDATA etc.
    source_id: str           # immutable ref/person/company ID
    collected_at: datetime
    claim: str
    support: str             # field/path/URL when available, not invented
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
        'DISCOVERED', 'INVITED', 'CONDITIONAL', 'DECLINED', 'ACCEPTED', 'CONFIRMED_SIMULATED', 'CANCELLED'
    ] = 'DISCOVERED'


class VendorOffer(BaseModel):
    id: str
    vendor_id: str
    service: Literal['catering', 'av', 'seating', 'other']
    quantity: int = Field(gt=0)
    capacity: int = Field(gt=0)
    total_price_inr: int = Field(ge=0)
    delivery_by: datetime
    hold_expires_at: datetime | None = None
    dietary_tags: list[str] = []
    status: Literal['AVAILABLE', 'HELD', 'CONFIRMED', 'EXPIRED', 'CANCELLED'] = 'AVAILABLE'
    mode: Literal['SIMULATED'] = 'SIMULATED'


class VendorOrder(BaseModel):
    id: str
    event_id: str
    offer_id: str
    idempotency_key: str
    status: Literal['CONFIRMED_SIMULATED', 'CANCELLED', 'FAILED']
    committed_inr: int
    cancellation_fee_inr: int = 0
    mode: Literal['SIMULATED'] = 'SIMULATED'


class Issue(BaseModel):
    id: str
    event_id: str
    type: Literal[
        'VENDOR_CANCELLED', 'GUEST_CANCELLED', 'ATTENDANCE_CHANGED',
        'HOLD_EXPIRED', 'BUDGET_EXCEEDED', 'CAPACITY_EXCEEDED',
        'TOOL_FAILURE', 'UNVERIFIED_IDENTITY'
    ]
    severity: Literal['INFO', 'WARNING', 'CRITICAL']
    status: Literal['OPEN', 'RECOVERING', 'RESOLVED', 'BLOCKED']
    message: str


class ReadinessResult(BaseModel):
    event_id: str
    status: Literal['READY_IN_SANDBOX', 'NEEDS_RECOVERY', 'BLOCKED']
    checks: dict[str, bool]
    blockers: list[str]
    evidence_ids: list[str]
    checked_at: datetime


class AuditEvent(BaseModel):
    id: str
    event_id: str
    action: str
    tool: str
    source_mode: Mode
    status: Literal['SUCCESS', 'FAILED', 'SKIPPED']
    reason: str
    references: list[str] = []
    timestamp: datetime


class ServiceReadiness(BaseModel):
    """Integrated service readiness returned by the deterministic verifier."""

    event_id: str
    status: Literal['READY', 'BLOCKED', 'IN_PROGRESS']
    checks: dict[str, bool]
    blockers: list[str]
    evidence_ids: list[str]
    checked_at: datetime


class DisruptionRequest(BaseModel):
    event_type: Literal['VENDOR_CANCELLED', 'GUEST_CANCELLED', 'ATTENDANCE_CHANGED']
    target_id: str | None = None
    new_count: int | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def validate_payload(self):
        if self.event_type in ('VENDOR_CANCELLED', 'GUEST_CANCELLED') and not self.target_id:
            raise ValueError('target_id is required for cancellation events')
        if self.event_type == 'ATTENDANCE_CHANGED' and self.new_count is None:
            raise ValueError('new_count is required for attendance changes')
        return self


class EventCreateResponse(BaseModel):
    event_id: str
    status: Literal['PLANNING']
    run_id: str


class TimelineResponse(BaseModel):
    items: list[dict[str, Any]]
