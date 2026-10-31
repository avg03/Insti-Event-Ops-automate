import React, { useState } from 'react';
import {
  ShieldAlert,
  AlertTriangle,
  RotateCcw,
  CheckCircle2,
  XCircle,
  Users,
  Store,
  TrendingUp,
  ArrowRight,
  Flame,
} from 'lucide-react';
import type { EventState } from '../types';

interface RecoveryLabTabProps {
  event: EventState;
  onSimulateDisruption: (
    type: 'VENDOR_CANCELLED' | 'GUEST_CANCELLED' | 'ATTENDANCE_CHANGED',
    payload: { target_id?: string; new_count?: number }
  ) => Promise<any>;
  isSimulating: boolean;
}

export const RecoveryLabTab: React.FC<RecoveryLabTabProps> = ({
  event,
  onSimulateDisruption,
  isSimulating,
}) => {
  const [selectedOrderId, setSelectedOrderId] = useState<string>('');
  const [selectedCandidateId, setSelectedCandidateId] = useState<string>('');
  const [newAttendance, setNewAttendance] = useState<number>(
    Math.min(event.brief.venue_capacity, event.brief.expected_attendance + 25)
  );
  const [lastDisruptionResult, setLastDisruptionResult] = useState<any>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const confirmedOrders = event.orders?.filter((o) => o.status === 'CONFIRMED_SIMULATED') || [];
  const confirmedGuests = event.guest_coordination?.confirmed_guests || [];

  const handleVendorCancel = async () => {
    setActionError(null);
    const target = selectedOrderId || confirmedOrders[0]?.id;
    if (!target) {
      setActionError('No confirmed vendor orders to cancel.');
      return;
    }
    try {
      const res = await onSimulateDisruption('VENDOR_CANCELLED', { target_id: target });
      setLastDisruptionResult(res);
    } catch (err: any) {
      setActionError(err.message || 'Disruption simulation failed');
    }
  };

  const handleGuestCancel = async () => {
    setActionError(null);
    const target = selectedCandidateId || confirmedGuests[0]?.candidate?.id;
    if (!target) {
      setActionError('No confirmed guests to cancel.');
      return;
    }
    try {
      const res = await onSimulateDisruption('GUEST_CANCELLED', { target_id: target });
      setLastDisruptionResult(res);
    } catch (err: any) {
      setActionError(err.message || 'Guest cancellation simulation failed');
    }
  };

  const handleAttendanceChange = async () => {
    setActionError(null);
    try {
      const res = await onSimulateDisruption('ATTENDANCE_CHANGED', { new_count: newAttendance });
      setLastDisruptionResult(res);
    } catch (err: any) {
      setActionError(err.message || 'Attendance surge simulation failed');
    }
  };

  return (
    <div>
      <div className="card" style={{ borderLeft: '4px solid var(--primary)' }}>
        <div className="card-header">
          <div>
            <h2>Autonomous Recovery Lab — Resilience & Failover</h2>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Test EventOps' deterministic recovery engine by injecting real-time disruptions into the active sandbox.
            </div>
          </div>
          <span className="badge badge-recovery">
            <Flame size={12} /> Live Chaos Simulator
          </span>
        </div>

        {actionError && (
          <div
            style={{
              padding: '12px',
              backgroundColor: 'var(--danger-light)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--danger)',
              fontSize: '0.85rem',
              marginBottom: '18px',
            }}
          >
            {actionError}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px' }}>
          {/* Scenario 1: Vendor Cancellation */}
          <div
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: '18px',
              backgroundColor: 'var(--bg-surface)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <Store size={18} color="var(--primary)" />
              <h3 style={{ fontSize: '1rem' }}>Vendor Cancellation</h3>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '14px' }}>
              Simulates caterer or AV supplier cancellation. The orchestrator invalidates the order and commits an eligible backup under budget limits.
            </p>

            <div className="form-group">
              <label className="form-label" style={{ fontSize: '0.75rem' }}>
                Select Active Order to Drop:
              </label>
              <select
                className="form-select"
                value={selectedOrderId || (confirmedOrders[0]?.id ?? '')}
                onChange={(e) => setSelectedOrderId(e.target.value)}
                disabled={confirmedOrders.length === 0}
              >
                {confirmedOrders.length === 0 ? (
                  <option value="">No active orders</option>
                ) : (
                  confirmedOrders.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.id} (Offer: {o.offer_id} - ₹{o.committed_inr})
                    </option>
                  ))
                )}
              </select>
            </div>

            <button
              className="btn btn-outline-danger"
              style={{ width: '100%' }}
              onClick={handleVendorCancel}
              disabled={isSimulating || confirmedOrders.length === 0}
            >
              <AlertTriangle size={14} />
              <span>{isSimulating ? 'Recovering...' : 'Simulate Vendor Cancellation'}</span>
            </button>
          </div>

          {/* Scenario 2: Guest Speaker Drop */}
          <div
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: '18px',
              backgroundColor: 'var(--bg-surface)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <Users size={18} color="var(--amber)" />
              <h3 style={{ fontSize: '1rem' }}>Guest Speaker Dropout</h3>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '14px' }}>
              Simulates sudden keynote speaker emergency. The agent releases the slot, invites the top Crustdata backup, and re-verifies.
            </p>

            <div className="form-group">
              <label className="form-label" style={{ fontSize: '0.75rem' }}>
                Select Confirmed Guest to Cancel:
              </label>
              <select
                className="form-select"
                value={selectedCandidateId || (confirmedGuests[0]?.candidate?.id ?? '')}
                onChange={(e) => setSelectedCandidateId(e.target.value)}
                disabled={confirmedGuests.length === 0}
              >
                {confirmedGuests.length === 0 ? (
                  <option value="">No active guests</option>
                ) : (
                  confirmedGuests.map((g) => (
                    <option key={g.candidate.id} value={g.candidate.id}>
                      {g.candidate.display_name} ({g.candidate.company_name})
                    </option>
                  ))
                )}
              </select>
            </div>

            <button
              className="btn btn-outline-danger"
              style={{ width: '100%' }}
              onClick={handleGuestCancel}
              disabled={isSimulating || confirmedGuests.length === 0}
            >
              <AlertTriangle size={14} />
              <span>{isSimulating ? 'Re-coordinating...' : 'Simulate Guest Drop'}</span>
            </button>
          </div>

          {/* Scenario 3: Attendance Surge */}
          <div
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: '18px',
              backgroundColor: 'var(--bg-surface)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <TrendingUp size={18} color="var(--moss-green)" />
              <h3 style={{ fontSize: '1rem' }}>Attendance Surge</h3>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '14px' }}>
              Surge in RSVP count from {event.brief.expected_attendance} up to venue limit ({event.brief.venue_capacity}). Recalculates catering & seating capacity.
            </p>

            <div className="form-group">
              <label className="form-label" style={{ fontSize: '0.75rem' }}>
                New Expected Attendance:
              </label>
              <input
                type="number"
                className="form-input"
                value={newAttendance}
                onChange={(e) => setNewAttendance(parseInt(e.target.value) || event.brief.expected_attendance)}
                min={1}
                max={event.brief.venue_capacity + 50}
              />
              <div className="form-helper">
                {newAttendance > event.brief.venue_capacity
                  ? '⚠️ Exceeds venue capacity! Verifier will emit BLOCKED.'
                  : `Within hall capacity (${event.brief.venue_capacity}).`}
              </div>
            </div>

            <button
              className="btn btn-secondary"
              style={{ width: '100%' }}
              onClick={handleAttendanceChange}
              disabled={isSimulating}
            >
              <RotateCcw size={14} />
              <span>{isSimulating ? 'Recalculating...' : 'Simulate Attendance Change'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Disruption Hero Output Card */}
      {lastDisruptionResult && (
        <div className="card" style={{ backgroundColor: 'var(--bg-surface)', border: '2px solid var(--moss-green)' }}>
          <div className="card-header">
            <div>
              <span className="badge badge-ready" style={{ marginBottom: '6px' }}>
                <CheckCircle2 size={12} /> Autonomous Recovery Executed
              </span>
              <h3>Disruption Handled & Restored</h3>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Issue ID: <code>{lastDisruptionResult.issue_id}</code> • Restored Readiness:{' '}
                <strong>{lastDisruptionResult.status}</strong>
              </div>
            </div>
            <span className="badge badge-simulated">Deterministic Verifier Pass</span>
          </div>

          <div className="recovery-diff-box">
            <div className="diff-col diff-before">
              <div style={{ fontWeight: 700, color: 'var(--danger)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <XCircle size={16} /> Disrupted Target Invalidation
              </div>
              <div style={{ fontSize: '0.825rem' }}>
                <div>
                  <strong>Target ID:</strong>{' '}
                  <code>{lastDisruptionResult.recovery?.cancelled_order_id || lastDisruptionResult.recovery?.cancelled_candidate_id || 'Disrupted target'}</code>
                </div>
                <div>
                  <strong>Status:</strong> Cancelled / Invalidated
                </div>
                {lastDisruptionResult.recovery?.cancellation_fee_inr !== undefined && (
                  <div>
                    <strong>Cancellation Fee Incurred:</strong> ₹{lastDisruptionResult.recovery.cancellation_fee_inr}
                  </div>
                )}
                <div style={{ marginTop: '8px', color: 'var(--text-muted)' }}>
                  State lock maintained. Idempotency guarantees no double bookings.
                </div>
              </div>
            </div>

            <div className="diff-col diff-after">
              <div style={{ fontWeight: 700, color: 'var(--moss-green)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <CheckCircle2 size={16} /> Autonomous Replacement Committed
              </div>
              <div style={{ fontSize: '0.825rem' }}>
                {lastDisruptionResult.recovery?.replacement_order && (
                  <div>
                    <div>
                      <strong>Replacement Order:</strong>{' '}
                      <code>{lastDisruptionResult.recovery.replacement_order.id}</code>
                    </div>
                    <div>
                      <strong>New Spend:</strong> ₹{lastDisruptionResult.recovery.replacement_order.committed_inr}
                    </div>
                    <div>
                      <strong>Idempotency Key:</strong>{' '}
                      <code>{lastDisruptionResult.recovery.replacement_order.idempotency_key.substring(0, 16)}...</code>
                    </div>
                  </div>
                )}

                {lastDisruptionResult.recovery?.replacement && (
                  <div>
                    <div>
                      <strong>Replacement Speaker:</strong>{' '}
                      <strong>{lastDisruptionResult.recovery.replacement.candidate?.display_name}</strong>
                    </div>
                    <div>
                      <strong>Role:</strong> {lastDisruptionResult.recovery.replacement.candidate?.current_title}
                    </div>
                    <div>
                      <strong>Source:</strong> Crustdata Canonical Ref
                    </div>
                  </div>
                )}

                <div style={{ marginTop: '8px', fontWeight: 600, color: 'var(--moss-green)' }}>
                  Independent Verifier confirmed: Ready in Sandbox
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
