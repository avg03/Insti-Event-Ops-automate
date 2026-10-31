export type Mode = 'LIVE_DATA' | 'SIMULATED';

export type EventStatus =
  | 'PLANNING'
  | 'RUNNING'
  | 'READY_IN_SANDBOX'
  | 'READY'
  | 'NEEDS_RECOVERY'
  | 'IN_PROGRESS'
  | 'BLOCKED';

export interface EventBrief {
  title: string;
  topic: string;
  city: string;
  timezone: string;
  starts_at: string;
  ends_at: string;
  budget_inr: number;
  expected_attendance: number;
  venue_capacity: number;
  guest_count: number;
  mandatory_resources: string[];
  dietary_requirements: string[];
  promotion_requested: boolean;
}

export interface EvidenceRef {
  provider: string;
  source_id: string;
  collected_at: string;
  claim: string;
  support: string;
  mode: Mode;
}

export interface GuestCandidate {
  id: string;
  event_id: string;
  canonical_person_id: string | null;
  display_name: string;
  current_title: string | null;
  company_name: string | null;
  relevance_score: number;
  evidence: EvidenceRef[];
  invitation_status:
    | 'DISCOVERED'
    | 'INVITED'
    | 'CONDITIONAL'
    | 'DECLINED'
    | 'ACCEPTED'
    | 'CONFIRMED_SIMULATED'
    | 'CANCELLED';
}

export interface GuestBooking {
  booking_id: string;
  event_id: string;
  candidate_id: string;
  status: string;
  idempotency_key: string;
  created_at: string;
  slot: {
    starts_at: string;
    ends_at: string;
    honorarium_inr?: number;
  };
}

export interface VendorOffer {
  id: string;
  vendor_id: string;
  service: 'catering' | 'av' | 'seating' | 'other';
  quantity: number;
  capacity: number;
  total_price_inr: number;
  delivery_by: string;
  hold_expires_at: string | null;
  dietary_tags: string[];
  status: 'AVAILABLE' | 'HELD' | 'CONFIRMED' | 'EXPIRED' | 'CANCELLED';
  mode: 'SIMULATED';
}

export interface VendorOrder {
  id: string;
  event_id: string;
  offer_id: string;
  idempotency_key: string;
  status: 'CONFIRMED_SIMULATED' | 'CANCELLED' | 'FAILED';
  committed_inr: number;
  cancellation_fee_inr: number;
  mode: 'SIMULATED';
}

export interface Issue {
  id: string;
  event_id: string;
  type: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  status: 'OPEN' | 'RECOVERING' | 'RESOLVED' | 'BLOCKED';
  message: string;
  created_at?: string;
}

export interface ServiceReadiness {
  event_id: string;
  status: 'READY' | 'READY_IN_SANDBOX' | 'BLOCKED' | 'IN_PROGRESS' | 'NEEDS_RECOVERY';
  checks: Record<string, boolean>;
  blockers: string[];
  evidence_ids: string[];
  checked_at: string;
}

export interface TimelineItem {
  id: string;
  timestamp: string;
  action: string;
  tool: string;
  source_mode: Mode;
  status: 'SUCCESS' | 'FAILED' | 'SKIPPED';
  reason: string;
  references: string[];
}

export interface BudgetSummary {
  total_budget_inr: number;
  committed_inr: number;
  hold_liability_inr: number;
  cancellation_fees_inr: number;
  guest_committed_inr?: number;
  available_inr: number;
}

export interface EventState {
  event_id: string;
  run_id: string;
  status: EventStatus;
  brief: EventBrief;
  plan: {
    guest_slots: Array<{ starts_at: string; ends_at: string }>;
    max_honorarium_inr: number;
    guest_budget_inr: number;
    vendor_budget_inr: number;
    required_quantities: Record<string, number>;
  } | null;
  guest_coordination: {
    status: string;
    confirmed_guests: Array<{
      candidate: GuestCandidate;
      terms?: any;
      slot?: any;
    }>;
    backup_candidates: Array<{
      candidate: GuestCandidate;
      explanation?: string;
    }>;
    pending_guests?: any[];
    evidence_ids: string[];
    guest_honorarium_committed_inr: number;
    last_recovery?: any;
  } | null;
  vendor_procurement: {
    status: string;
    confirmed_orders: VendorOrder[];
    held_offers?: VendorOffer[];
    budget_summary?: BudgetSummary;
    last_recovery?: any;
    last_recalculation?: any;
  } | null;
  guest_bookings: GuestBooking[];
  orders: VendorOrder[];
  budget: BudgetSummary;
  readiness: ServiceReadiness | null;
  issues: Issue[];
  last_error: string | null;
  simulation_mode: boolean;
}

export interface EventSummary {
  event_id: string;
  run_id: string;
  status: EventStatus;
  brief: EventBrief;
  created_at: string;
  updated_at: string;
}

export interface ReelScene {
  scene: number;
  duration_seconds: number;
  visual: string;
  audio_voiceover: string;
  onscreen_text: string;
}

export interface CampaignPromotion {
  event_id: string;
  status: string;
  mode: Mode;
  generated_at: string;
  headline: string;
  poster_copy: {
    headline: string;
    subheadline: string;
    date_and_venue: string;
    featured_speakers: string[];
    key_takeaways: string[];
    registration_cta: string;
    hashtags: string[];
  };
  reel_storyboard: ReelScene[];
  schedule_summary: Array<{
    time: string;
    session: string;
    speaker: string;
  }>;
  disclaimer: string;
}
