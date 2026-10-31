import React, { useState } from 'react';
import { History, ShieldCheck, Download, Filter, CheckCircle2, XCircle } from 'lucide-react';
import type { EventState, TimelineItem } from '../types';

interface AuditTrailTabProps {
  event: EventState;
  timeline: TimelineItem[];
}

export const AuditTrailTab: React.FC<AuditTrailTabProps> = ({ event, timeline }) => {
  const [filterMode, setFilterMode] = useState<'ALL' | 'LIVE_DATA' | 'SIMULATED'>('ALL');
  const [filterStatus, setFilterStatus] = useState<'ALL' | 'SUCCESS' | 'FAILED'>('ALL');

  const filtered = timeline.filter((item) => {
    if (filterMode !== 'ALL' && item.source_mode !== filterMode) return false;
    if (filterStatus !== 'ALL' && item.status !== filterStatus) return false;
    return true;
  });

  const exportJson = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(timeline, null, 2));
    const dlAnchorElem = document.createElement('a');
    dlAnchorElem.setAttribute('href', dataStr);
    dlAnchorElem.setAttribute('download', `audit_trail_${event.event_id}.json`);
    dlAnchorElem.click();
  };

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <div>
            <h2>Verifiable Audit Trail & State Transitions</h2>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Chronological immutable ledger of all agent actions, Crustdata queries, and simulator bookings
            </div>
          </div>

          <button
            className="btn btn-secondary"
            style={{ padding: '6px 12px', fontSize: '0.75rem' }}
            onClick={exportJson}
          >
            <Download size={14} />
            <span>Export JSON</span>
          </button>
        </div>

        {/* Filter Bar */}
        <div style={{ display: 'flex', gap: '14px', marginBottom: '20px', alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.825rem', color: 'var(--text-muted)' }}>
            <Filter size={14} />
            <span>Filters:</span>
          </div>

          <select
            className="form-select"
            style={{ width: 'auto', padding: '6px 10px', fontSize: '0.8rem' }}
            value={filterMode}
            onChange={(e) => setFilterMode(e.target.value as any)}
          >
            <option value="ALL">All Source Modes</option>
            <option value="LIVE_DATA">Crustdata Live Data Only</option>
            <option value="SIMULATED">Simulated Only</option>
          </select>

          <select
            className="form-select"
            style={{ width: 'auto', padding: '6px 10px', fontSize: '0.8rem' }}
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as any)}
          >
            <option value="ALL">All Statuses</option>
            <option value="SUCCESS">Success Only</option>
            <option value="FAILED">Failed Only</option>
          </select>

          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
            Showing {filtered.length} of {timeline.length} audit records
          </span>
        </div>

        {/* Audit Log Table */}
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Action</th>
                <th>Tool / Component</th>
                <th>Source Mode</th>
                <th>Status</th>
                <th>Reason & Notes</th>
                <th>References</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                    No audit records match the selected filters.
                  </td>
                </tr>
              ) : (
                filtered.map((item) => (
                  <tr key={item.id}>
                    <td style={{ whiteSpace: 'nowrap', fontSize: '0.775rem', color: 'var(--text-muted)' }}>
                      {item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : 'N/A'}
                    </td>
                    <td>
                      <strong>{item.action}</strong>
                    </td>
                    <td>
                      <code>{item.tool}</code>
                    </td>
                    <td>
                      <span
                        className={`badge ${item.source_mode === 'LIVE_DATA' ? 'badge-live-data' : 'badge-simulated'}`}
                        style={{ fontSize: '0.7rem' }}
                      >
                        {item.source_mode === 'LIVE_DATA' ? 'LIVE: Crustdata' : 'SIMULATED'}
                      </span>
                    </td>
                    <td>
                      {item.status === 'SUCCESS' ? (
                        <span style={{ color: 'var(--moss-green)', display: 'flex', alignItems: 'center', gap: '4px', fontWeight: 600 }}>
                          <CheckCircle2 size={13} /> OK
                        </span>
                      ) : (
                        <span style={{ color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: '4px', fontWeight: 600 }}>
                          <XCircle size={13} /> {item.status}
                        </span>
                      )}
                    </td>
                    <td style={{ fontSize: '0.8rem', maxWidth: '320px' }}>
                      {item.reason}
                    </td>
                    <td>
                      {item.references && item.references.length > 0 ? (
                        <code style={{ fontSize: '0.725rem' }}>{item.references.join(', ')}</code>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
