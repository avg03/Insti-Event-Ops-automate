import type {
  CampaignPromotion,
  EventBrief,
  EventState,
  EventSummary,
  ServiceReadiness,
  TimelineItem,
} from './types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorDetail = `HTTP ${res.status}: ${res.statusText}`;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // ignored
    }
    throw new Error(errorDetail);
  }
  return res.json() as Promise<T>;
}

export async function fetchEvents(): Promise<EventSummary[]> {
  const res = await fetch(`${API_BASE}/api/events?limit=50`);
  return handleResponse<EventSummary[]>(res);
}

export async function fetchEvent(eventId: string): Promise<EventState> {
  const res = await fetch(`${API_BASE}/api/events/${eventId}`);
  return handleResponse<EventState>(res);
}

export async function createEvent(brief: EventBrief): Promise<{ event_id: string; run_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(brief),
  });
  return handleResponse<{ event_id: string; run_id: string; status: string }>(res);
}

export async function fetchTimeline(eventId: string, afterId?: string): Promise<TimelineItem[]> {
  const url = afterId
    ? `${API_BASE}/api/events/${eventId}/timeline?after_id=${encodeURIComponent(afterId)}`
    : `${API_BASE}/api/events/${eventId}/timeline`;
  const res = await fetch(url);
  const data = await handleResponse<{ items: TimelineItem[] }>(res);
  return data.items || [];
}

export async function simulateDisruption(
  eventId: string,
  eventType: 'VENDOR_CANCELLED' | 'GUEST_CANCELLED' | 'ATTENDANCE_CHANGED',
  payload: { target_id?: string; new_count?: number }
): Promise<any> {
  const res = await fetch(`${API_BASE}/api/events/${eventId}/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event_type: eventType,
      ...payload,
    }),
  });
  return handleResponse<any>(res);
}

export async function verifyEvent(eventId: string): Promise<ServiceReadiness> {
  const res = await fetch(`${API_BASE}/api/events/${eventId}/verify`, {
    method: 'POST',
  });
  return handleResponse<ServiceReadiness>(res);
}

export async function fetchPromotion(eventId: string): Promise<CampaignPromotion> {
  const res = await fetch(`${API_BASE}/api/events/${eventId}/promotion`);
  return handleResponse<CampaignPromotion>(res);
}
