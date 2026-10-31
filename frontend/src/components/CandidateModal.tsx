import React from 'react';
import { X, ShieldCheck, Calendar, Briefcase, Award } from 'lucide-react';
import type { GuestCandidate } from '../types';

interface CandidateModalProps {
  candidate: GuestCandidate | null;
  onClose: () => void;
}

export const CandidateModal: React.FC<CandidateModalProps> = ({ candidate, onClose }) => {
  if (!candidate) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
          <div>
            <span className="badge badge-live-data" style={{ marginBottom: '8px' }}>
              <ShieldCheck size={12} /> Verified Source: Crustdata
            </span>
            <h2 style={{ fontSize: '1.4rem' }}>{candidate.display_name}</h2>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              {candidate.current_title} • {candidate.company_name}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
          >
            <X size={20} />
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '20px' }}>
          <div style={{ padding: '12px', backgroundColor: 'var(--bg-muted)', borderRadius: 'var(--radius-md)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Canonical Person ID
            </div>
            <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>
              <code>{candidate.canonical_person_id || candidate.id}</code>
            </div>
          </div>
          <div style={{ padding: '12px', backgroundColor: 'var(--bg-muted)', borderRadius: 'var(--radius-md)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Relevance Match Score
            </div>
            <div style={{ fontWeight: 700, fontSize: '1.1rem', color: 'var(--moss-green)' }}>
              {(candidate.relevance_score * 100).toFixed(0)}%
            </div>
          </div>
        </div>

        <div style={{ marginBottom: '20px' }}>
          <h4 style={{ fontSize: '0.95rem', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Award size={16} /> Crustdata Provenance & Evidence Records
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {candidate.evidence?.map((ev, idx) => (
              <div
                key={idx}
                style={{
                  padding: '10px 14px',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: 'var(--bg-surface)',
                  fontSize: '0.825rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ fontWeight: 600 }}>{ev.claim}</span>
                  <span className="badge badge-live-data" style={{ fontSize: '0.65rem' }}>
                    {ev.mode}
                  </span>
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                  Support: <code>{ev.support}</code> • Ref ID: <code>{ev.source_id}</code>
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', marginTop: '2px' }}>
                  Fetched: {new Date(ev.collected_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ padding: '12px', backgroundColor: 'var(--amber-light)', borderRadius: 'var(--radius-md)', fontSize: '0.775rem', color: 'var(--amber)' }}>
          <strong>Sandbox Notice:</strong> In compliance with competition guidelines, outreach & calendar agreements for this candidate are executed through local synthetic simulation. No real email or DM was dispatched.
        </div>
      </div>
    </div>
  );
};
