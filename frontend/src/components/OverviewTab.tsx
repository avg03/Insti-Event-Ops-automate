import React from 'react';
import {
  CheckCircle2,
  XCircle,
  Clock,
  ShieldCheck,
  TrendingUp,
  AlertCircle,
  FileCheck2,
} from 'lucide-react';
import type { EventState, TimelineItem } from '../types';

interface OverviewTabProps {
  event: EventState;
  timeline: TimelineItem[];
  onTriggerDisruptionTab: () => void;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({
  event,
  timeline,
  onTriggerDisruptionTab,
}) => {
  const readiness = event.readiness;
  const checks = readiness?.checks || {};
  const totalChecks = Object.keys(checks).length;
  const passedChecks = Object.values(checks).filter(Boolean).length;

  const budget = event.budget || {
    total_budget_inr: event.brief.budget_inr,
    committed_inr: 0,
    hold_liability_inr: 0,
    cancellation_fees_inr: 0,
    guest_committed_inr: 0,
    available_inr: event.brief.budget_inr,
  };

  const totalBudget = budget.total_budget_inr || event.brief.budget_inr;
  const vendorCommitted = budget.committed_inr || 0;
  const guestCommitted = budget.guest_committed_inr || 0;
  const holdLiability = budget.hold_liability_inr || 0;
  const availableBudget = budget.available_inr || 0;

  const vendorPct = Math.min(100, (vendorCommitted / totalBudget) * 100);
  const guestPct = Math.min(100, (guestCommitted / totalBudget) * 100);
  const holdPct = Math.min(100, (holdLiability / totalBudget) * 100);
  const availPct = Math.max(0, 100 - (vendorPct + guestPct + holdPct));

  const confirmedGuestsCount =
    event.guest_coordination?.confirmed_guests?.length ||
    event.guest_bookings?.filter((b) => b.status === 'CONFIRMED_SIMULATED').length ||
    0;

  const confirmedOrdersCount =
    event.vendor_procurement?.confirmed_orders?.length ||
    event.orders?.filter((o) => o.status === 'CONFIRMED_SIMULATED').length ||
    0;

  const openIssues = event.issues?.filter((i) => i.status === 'OPEN' || i.status === 'RECOVERING') || [];

  return (
    <div>
      {/* Top Stats Row */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Readiness</div>
          <div className="stat-value" style={{ color: event.status === 'READY_IN_SANDBOX' || event.status === 'READY' ? 'var(--moss-green)' : 'var(--text-primary)' }}>
            {event.status === 'READY_IN_SANDBOX' || event.status === 'READY'
              ? 'Ready (sandbox)'
              : event.status === 'NEEDS_RECOVERY'
              ? 'Needs Recovery'
              : event.status}
          </div>
          <div className="stat-subtext">
            {totalChecks > 0 ? `${passedChecks}/${totalChecks} invariant checks passed` : 'Pending execution'}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Confirmed Guests</div>
          <div className="stat-value">
            {confirmedGuestsCount} / {event.brief.guest_count}
          </div>
          <div className="stat-subtext">
            <span className="badge badge-simulated" style={{ fontSize: '0.65rem' }}>
              Simulated Calendar
            </span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Committed Spend</div>
          <div className="stat-value">
            ₹{(vendorCommitted + guestCommitted).toLocaleString('en-IN')}
          </div>
          <div className="stat-subtext">
            ₹{availableBudget.toLocaleString('en-IN')} contingency reserve
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Active Issues</div>
          <div className="stat-value" style={{ color: openIssues.length > 0 ? 'var(--danger)' : 'var(--moss-green)' }}>
            {openIssues.length}
          </div>
          <div className="stat-subtext">
            {openIssues.length > 0 ? (
              <button
                onClick={onTriggerDisruptionTab}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--primary)',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.75rem',
                  textDecoration: 'underline',
                  padding: 0,
                }}
              >
                Inspect in Recovery Lab →
              </button>
            ) : (
              'All constraints satisfied'
            )}
          </div>
        </div>
      </div>

      {/* Budget Allocation Card */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3>Budget Allocation & Reserves</h3>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Total Envelope: ₹{totalBudget.toLocaleString('en-IN')} • Strict integer arithmetic without double counting
            </div>
          </div>
          <span className="badge badge-simulated">Sandbox Ledger</span>
        </div>

        <div className="budget-bar-container">
          <div className="budget-bar">
            <div
              className="budget-segment segment-vendor"
              style={{ width: `${vendorPct}%` }}
              title={`Vendor committed: ₹${vendorCommitted}`}
            />
            <div
              className="budget-segment segment-guest"
              style={{ width: `${guestPct}%` }}
              title={`Guest honorariums: ₹${guestCommitted}`}
            />
            <div
              className="budget-segment segment-hold"
              style={{ width: `${holdPct}%` }}
              title={`Hold liability: ₹${holdLiability}`}
            />
            <div
              className="budget-segment segment-available"
              style={{ width: `${availPct}%` }}
              title={`Available: ₹${availableBudget}`}
            />
          </div>

          <div className="budget-legend">
            <div className="legend-item">
              <span className="legend-dot" style={{ backgroundColor: 'var(--primary)' }} />
              <span>Vendors: ₹{vendorCommitted.toLocaleString('en-IN')} ({vendorPct.toFixed(1)}%)</span>
            </div>
            <div className="legend-item">
              <span className="legend-dot" style={{ backgroundColor: '#558B6E' }} />
              <span>Guest Honorariums: ₹{guestCommitted.toLocaleString('en-IN')} ({guestPct.toFixed(1)}%)</span>
            </div>
            {holdLiability > 0 && (
              <div className="legend-item">
                <span className="legend-dot" style={{ backgroundColor: 'var(--amber)' }} />
                <span>Held Reserves: ₹{holdLiability.toLocaleString('en-IN')} ({holdPct.toFixed(1)}%)</span>
              </div>
            )}
            <div className="legend-item">
              <span className="legend-dot" style={{ backgroundColor: '#D3CEBE' }} />
              <span>Unallocated Available: ₹{availableBudget.toLocaleString('en-IN')} ({availPct.toFixed(1)}%)</span>
            </div>
          </div>
        </div>
      </div>

      {/* Two Column Grid: Timeline & Invariants */}
      <div className="two-col-grid">
        {/* Timeline */}
        <div className="card">
          <div className="card-header">
            <div>
              <h3>Agent Execution Stream</h3>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Real-time autonomous audit trail & tool calls
              </div>
            </div>
            <span className="badge badge-live-data">
              <ShieldCheck size={12} /> Provable
            </span>
          </div>

          <div className="timeline-stream">
            {timeline.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
                Waiting for agent events...
              </div>
            ) : (
              timeline.map((item) => (
                <div
                  key={item.id}
                  className={`timeline-item ${item.status === 'SUCCESS' ? 'success' : item.status === 'FAILED' ? 'failed' : ''}`}
                >
                  <div style={{ flex: 1 }}>
                    <div className="timeline-meta">
                      <span className="timeline-action">{item.action}</span>
                      <span className={`badge ${item.source_mode === 'LIVE_DATA' ? 'badge-live-data' : 'badge-simulated'}`} style={{ fontSize: '0.65rem', padding: '1px 6px' }}>
                        {item.source_mode === 'LIVE_DATA' ? 'Crustdata' : 'Simulated'}
                      </span>
                      <span className="timeline-time">
                        {item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : ''}
                      </span>
                    </div>
                    <div className="timeline-reason">{item.reason}</div>
                    <div style={{ fontSize: '0.725rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                      Tool: <code>{item.tool}</code>
                      {item.references?.length > 0 && ` • Refs: ${item.references.join(', ')}`}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Readiness Checklist & Confirmed Resources */}
        <div>
          <div className="card">
            <div className="card-header">
              <div>
                <h3>Deterministic Verifier Checklist</h3>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Evaluated independently on raw database state
                </div>
              </div>
              <span className="badge badge-ready">
                <FileCheck2 size={12} /> Verifier
              </span>
            </div>

            <div className="checklist">
              {totalChecks === 0 ? (
                <div style={{ padding: '12px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  Awaiting verifier pass...
                </div>
              ) : (
                Object.entries(checks).map(([name, passed]) => (
                  <div key={name} className={`check-item ${passed ? 'passed' : 'failed'}`}>
                    {passed ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
                    <span style={{ fontWeight: 500 }}>
                      {name.replace(/_/g, ' ').toUpperCase()}
                    </span>
                  </div>
                ))
              )}
            </div>

            {readiness?.blockers && readiness.blockers.length > 0 && (
              <div style={{ marginTop: '16px', padding: '12px', backgroundColor: 'var(--danger-light)', borderRadius: 'var(--radius-md)' }}>
                <div style={{ fontWeight: 600, color: 'var(--danger)', fontSize: '0.825rem', marginBottom: '4px' }}>
                  Active Blockers:
                </div>
                <ul style={{ paddingLeft: '18px', fontSize: '0.8rem', color: 'var(--danger)' }}>
                  {readiness.blockers.map((b, idx) => (
                    <li key={idx}>{b}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Quick Confirmed Resources */}
          <div className="card">
            <div className="card-header">
              <h3>Active Sandbox Commitments</h3>
              <span className="badge badge-simulated">{confirmedOrdersCount + confirmedGuestsCount} booked</span>
            </div>

            <div style={{ fontSize: '0.85rem' }}>
              <div style={{ fontWeight: 600, marginBottom: '6px' }}>Confirmed Speakers:</div>
              {event.guest_coordination?.confirmed_guests?.length ? (
                <ul style={{ paddingLeft: '18px', marginBottom: '14px', color: 'var(--text-primary)' }}>
                  {event.guest_coordination.confirmed_guests.map((g, idx) => (
                    <li key={idx}>
                      <strong>{g.candidate.display_name}</strong> — {g.candidate.current_title || 'Expert'} (
                      {g.candidate.company_name || 'Organization'})
                    </li>
                  ))}
                </ul>
              ) : (
                <div style={{ color: 'var(--text-muted)', marginBottom: '12px' }}>None confirmed yet.</div>
              )}

              <div style={{ fontWeight: 600, marginBottom: '6px' }}>Procured Vendor Orders:</div>
              {event.orders?.length ? (
                <ul style={{ paddingLeft: '18px', color: 'var(--text-primary)' }}>
                  {event.orders
                    .filter((o) => o.status === 'CONFIRMED_SIMULATED')
                    .map((o, idx) => (
                      <li key={idx}>
                        Order <code>{o.id}</code> — ₹{o.committed_inr.toLocaleString('en-IN')} (Offer: {o.offer_id})
                      </li>
                    ))}
                </ul>
              ) : (
                <div style={{ color: 'var(--text-muted)' }}>No orders committed yet.</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
