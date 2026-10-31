import React from 'react';
import { RefreshCw, PlusCircle, CheckCircle2, Clock, AlertTriangle, XCircle, ShieldCheck } from 'lucide-react';
import type { EventState, EventSummary } from '../types';

interface HeaderProps {
  currentEvent: EventState | null;
  eventsList: EventSummary[];
  selectedEventId: string;
  onSelectEvent: (id: string) => void;
  onNewEventClick: () => void;
  onRefresh: () => void;
  isLoading: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  currentEvent,
  eventsList,
  selectedEventId,
  onSelectEvent,
  onNewEventClick,
  onRefresh,
  isLoading,
}) => {
  const renderStatusBadge = () => {
    if (!currentEvent) return null;
    const s = currentEvent.status;
    if (s === 'READY_IN_SANDBOX' || s === 'READY') {
      return (
        <span className="badge badge-ready">
          <CheckCircle2 size={13} /> Ready (sandbox)
        </span>
      );
    }
    if (s === 'PLANNING' || s === 'RUNNING' || s === 'IN_PROGRESS') {
      return (
        <span className="badge badge-planning">
          <span className="pulse-dot" /> {s === 'PLANNING' ? 'Planning...' : 'Running...'}
        </span>
      );
    }
    if (s === 'NEEDS_RECOVERY') {
      return (
        <span className="badge badge-recovery">
          <AlertTriangle size={13} /> Needs Recovery
        </span>
      );
    }
    return (
      <span className="badge badge-blocked">
        <XCircle size={13} /> Blocked
      </span>
    );
  };

  return (
    <header className="top-header">
      <div className="header-left">
        <div className="header-title-group">
          <h1>{currentEvent?.brief?.title || 'Event Operations Console'}</h1>
          <div className="header-sub">
            {currentEvent ? (
              <span>
                {currentEvent.brief.city} • Expected: {currentEvent.brief.expected_attendance} • Budget: ₹
                {currentEvent.brief.budget_inr.toLocaleString('en-IN')}
              </span>
            ) : (
              <span>No event active</span>
            )}
          </div>
        </div>

        {eventsList.length > 0 && (
          <select
            className="form-select"
            style={{ width: 'auto', padding: '6px 10px', fontSize: '0.8rem' }}
            value={selectedEventId}
            onChange={(e) => onSelectEvent(e.target.value)}
          >
            {eventsList.map((ev) => (
              <option key={ev.event_id} value={ev.event_id}>
                {ev.brief?.title || ev.event_id} ({ev.status})
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="header-right">
        {renderStatusBadge()}

        <span className="badge badge-live-data" title="Crustdata Canonical Identity Enabled">
          <ShieldCheck size={13} /> Crustdata Live
        </span>

        <button
          className="btn btn-secondary"
          onClick={onRefresh}
          disabled={isLoading}
          title="Refresh current state"
          style={{ padding: '7px 12px' }}
        >
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          <span>Sync</span>
        </button>

        <button
          className="btn btn-primary"
          onClick={onNewEventClick}
          style={{ padding: '7px 14px' }}
        >
          <PlusCircle size={14} />
          <span>New Event</span>
        </button>
      </div>
    </header>
  );
};
