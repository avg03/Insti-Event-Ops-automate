import React from 'react';
import { Store, CheckCircle2, XCircle, Clock, ShieldCheck, Utensils, Mic, Armchair } from 'lucide-react';
import type { EventState } from '../types';

interface ProcurementTabProps {
  event: EventState;
}

export const ProcurementTab: React.FC<ProcurementTabProps> = ({ event }) => {
  const orders = event.orders || [];
  const confirmedOrders = orders.filter((o) => o.status === 'CONFIRMED_SIMULATED');
  const cancelledOrders = orders.filter((o) => o.status === 'CANCELLED');
  const heldOffers = event.vendor_procurement?.held_offers || [];

  const getServiceIcon = (service: string) => {
    switch (service.toLowerCase()) {
      case 'catering':
        return <Utensils size={15} />;
      case 'av':
        return <Mic size={15} />;
      case 'seating':
        return <Armchair size={15} />;
      default:
        return <Store size={15} />;
    }
  };

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <div>
            <h2>Vendor Procurement & Sandbox Ledger</h2>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Deterministic quotes, knapsack resource allocation, and idempotent sandbox commitments
            </div>
          </div>
          <span className="badge badge-simulated">Simulated Procurement</span>
        </div>

        {/* Confirmed Orders */}
        <div style={{ marginBottom: '28px' }}>
          <h3 style={{ fontSize: '1.05rem', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle2 size={18} color="var(--moss-green)" /> Confirmed Sandbox Orders ({confirmedOrders.length})
          </h3>

          {confirmedOrders.length === 0 ? (
            <div style={{ padding: '20px', backgroundColor: 'var(--bg-muted)', borderRadius: 'var(--radius-md)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              No vendor orders currently confirmed.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Order ID</th>
                    <th>Offer Ref</th>
                    <th>Committed Spend</th>
                    <th>Idempotency Key</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {confirmedOrders.map((ord) => (
                    <tr key={ord.id}>
                      <td>
                        <strong style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <Store size={14} color="var(--primary)" /> {ord.id}
                        </strong>
                      </td>
                      <td>
                        <code>{ord.offer_id}</code>
                      </td>
                      <td>
                        <strong style={{ color: 'var(--primary)' }}>
                          ₹{ord.committed_inr.toLocaleString('en-IN')}
                        </strong>
                      </td>
                      <td>
                        <code style={{ fontSize: '0.75rem' }}>{ord.idempotency_key.substring(0, 16)}...</code>
                      </td>
                      <td>
                        <span className="badge badge-ready">
                          <CheckCircle2 size={12} /> Confirmed (Simulated)
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Cancelled / Invalidated Orders (Disruption Audit) */}
        {cancelledOrders.length > 0 && (
          <div style={{ marginBottom: '28px' }}>
            <h3 style={{ fontSize: '1.05rem', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--danger)' }}>
              <XCircle size={18} /> Cancelled / Invalidated Orders ({cancelledOrders.length})
            </h3>
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Order ID</th>
                    <th>Offer Ref</th>
                    <th>Original Amount</th>
                    <th>Cancellation Fee</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {cancelledOrders.map((ord) => (
                    <tr key={ord.id} style={{ opacity: 0.75 }}>
                      <td>
                        <code style={{ textDecoration: 'line-through' }}>{ord.id}</code>
                      </td>
                      <td>
                        <code>{ord.offer_id}</code>
                      </td>
                      <td>₹{ord.committed_inr.toLocaleString('en-IN')}</td>
                      <td style={{ color: 'var(--danger)', fontWeight: 600 }}>
                        ₹{(ord.cancellation_fee_inr || 0).toLocaleString('en-IN')}
                      </td>
                      <td>
                        <span className="badge badge-blocked">
                          <XCircle size={12} /> Cancelled
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Active Holds */}
        <div>
          <h3 style={{ fontSize: '1.05rem', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Clock size={18} color="var(--amber)" /> Active Vendor Holds ({heldOffers.length})
          </h3>

          {heldOffers.length === 0 ? (
            <div style={{ padding: '16px', backgroundColor: 'var(--bg-muted)', borderRadius: 'var(--radius-md)', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              No backup offers currently held. Backup options are reserved automatically when recovery is needed.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Offer ID</th>
                    <th>Service</th>
                    <th>Price</th>
                    <th>Hold Expiration</th>
                    <th>Dietary Tags</th>
                  </tr>
                </thead>
                <tbody>
                  {heldOffers.map((h) => (
                    <tr key={h.id}>
                      <td>
                        <code>{h.id}</code>
                      </td>
                      <td style={{ textTransform: 'capitalize' }}>{h.service}</td>
                      <td>₹{h.total_price_inr.toLocaleString('en-IN')}</td>
                      <td>{h.hold_expires_at ? new Date(h.hold_expires_at).toLocaleTimeString() : 'N/A'}</td>
                      <td>{h.dietary_tags.join(', ') || 'Standard'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
