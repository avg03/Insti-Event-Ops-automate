import React, { useState } from 'react';
import { Users, ShieldCheck, CheckCircle2, Clock, UserCheck, Eye, Award } from 'lucide-react';
import type { EventState, GuestCandidate } from '../types';
import { CandidateModal } from './CandidateModal';

interface GuestDeskTabProps {
  event: EventState;
}

export const GuestDeskTab: React.FC<GuestDeskTabProps> = ({ event }) => {
  const [selectedCandidate, setSelectedCandidate] = useState<GuestCandidate | null>(null);

  const coordination = event.guest_coordination;
  const confirmed = coordination?.confirmed_guests || [];
  const backups = coordination?.backup_candidates || [];

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <div>
            <h2>Guest Desk & Identity Provenance</h2>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Real people discovered from Crustdata Canonical Identity Graph • Simulated negotiation & calendar confirmations
            </div>
          </div>
          <span className="badge badge-live-data">
            <ShieldCheck size={12} /> Crustdata Identity Graph
          </span>
        </div>

        {/* Confirmed Speaker Sessions */}
        <div style={{ marginBottom: '28px' }}>
          <h3 style={{ fontSize: '1.05rem', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <UserCheck size={18} color="var(--moss-green)" /> Confirmed Guest Lineup ({confirmed.length} / {event.brief.guest_count})
          </h3>

          {confirmed.length === 0 ? (
            <div style={{ padding: '20px', backgroundColor: 'var(--bg-muted)', borderRadius: 'var(--radius-md)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              No guest confirmed yet. The agent coordinates candidates sequentially.
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
              {confirmed.map((item, idx) => {
                const cand = item.candidate;
                const terms = item.terms || {};
                const slot = item.slot || {};
                return (
                  <div
                    key={idx}
                    style={{
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-md)',
                      backgroundColor: 'var(--bg-surface)',
                      padding: '18px',
                      boxShadow: 'var(--shadow-sm)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '1.05rem' }}>{cand.display_name}</div>
                        <div style={{ fontSize: '0.825rem', color: 'var(--text-muted)' }}>
                          {cand.current_title}
                        </div>
                        <div style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--primary)' }}>
                          {cand.company_name}
                        </div>
                      </div>
                      <span className="badge badge-ready">
                        <CheckCircle2 size={12} /> Confirmed (Simulated)
                      </span>
                    </div>

                    <div style={{ backgroundColor: 'var(--bg-muted)', padding: '10px 12px', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', marginBottom: '12px' }}>
                      <div>
                        <strong>Agreed Honorarium:</strong> ₹{terms.honorarium_inr || slot.honorarium_inr || 1500}
                      </div>
                      {slot.starts_at && (
                        <div>
                          <strong>Calendar Slot:</strong>{' '}
                          {new Date(slot.starts_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} -{' '}
                          {new Date(slot.ends_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      )}
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span className="badge badge-live-data" style={{ fontSize: '0.7rem' }}>
                        ID: {cand.canonical_person_id || cand.id}
                      </span>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                        onClick={() => setSelectedCandidate(cand)}
                      >
                        <Eye size={12} /> Provenance
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Shortlisted / Backup Roster */}
        <div>
          <h3 style={{ fontSize: '1.05rem', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Users size={18} /> Shortlisted & Backup Candidates ({backups.length})
          </h3>

          {backups.length === 0 ? (
            <div style={{ padding: '16px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              No additional backup candidates shortlisted.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th>Current Role & Company</th>
                    <th>Relevance Score</th>
                    <th>Source ID</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {backups.map((item, idx) => {
                    const cand = item.candidate || item;
                    return (
                      <tr key={idx}>
                        <td>
                          <strong>{cand.display_name}</strong>
                        </td>
                        <td>
                          <div>{cand.current_title || 'Expert'}</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            {cand.company_name}
                          </div>
                        </td>
                        <td>
                          <div style={{ fontWeight: 600, color: 'var(--moss-green)' }}>
                            {((cand.relevance_score || 0) * 100).toFixed(0)}%
                          </div>
                        </td>
                        <td>
                          <code>{cand.canonical_person_id || cand.id}</code>
                        </td>
                        <td>
                          <span className="badge badge-planning" style={{ fontSize: '0.7rem' }}>
                            Backup Standby
                          </span>
                        </td>
                        <td>
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                            onClick={() => setSelectedCandidate(cand)}
                          >
                            <Eye size={12} /> Inspect
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <CandidateModal candidate={selectedCandidate} onClose={() => setSelectedCandidate(null)} />
    </div>
  );
};
