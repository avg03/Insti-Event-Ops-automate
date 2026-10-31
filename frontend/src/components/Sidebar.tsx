import React from 'react';
import {
  LayoutDashboard,
  PlusCircle,
  Users,
  Store,
  ShieldAlert,
  Megaphone,
  History,
  Building2,
} from 'lucide-react';

export type TabKey =
  | 'overview'
  | 'intake'
  | 'guests'
  | 'procurement'
  | 'recovery'
  | 'campaigns'
  | 'audit';

interface SidebarProps {
  activeTab: TabKey;
  onTabChange: (tab: TabKey) => void;
  openIssuesCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  openIssuesCount,
}) => {
  const navItems = [
    { key: 'overview' as TabKey, label: 'Overview', icon: LayoutDashboard },
    { key: 'intake' as TabKey, label: 'Event Intake', icon: PlusCircle },
    { key: 'guests' as TabKey, label: 'Guest Desk', icon: Users },
    { key: 'procurement' as TabKey, label: 'Procurement', icon: Store },
    {
      key: 'recovery' as TabKey,
      label: 'Recovery Lab',
      icon: ShieldAlert,
      badge: openIssuesCount > 0 ? openIssuesCount : undefined,
    },
    { key: 'campaigns' as TabKey, label: 'Campaigns', icon: Megaphone },
    { key: 'audit' as TabKey, label: 'Audit Trail', icon: History },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-title">
          <Building2 size={22} />
          <span>EventOps</span>
          <span className="brand-badge">IIT Bombay</span>
        </div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
          Autonomous Ops Console
        </div>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.key;
          return (
            <button
              key={item.key}
              className={`nav-item ${isActive ? 'active' : ''}`}
              onClick={() => onTabChange(item.key)}
            >
              <Icon size={18} />
              <span style={{ flex: 1 }}>{item.label}</span>
              {item.badge !== undefined && (
                <span
                  style={{
                    backgroundColor: 'var(--danger)',
                    color: 'white',
                    fontSize: '0.7rem',
                    padding: '1px 6px',
                    borderRadius: '9999px',
                    fontWeight: 600,
                  }}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
          Mode: Sandbox Active
        </div>
        <div>Crustdata Live Graph</div>
        <div>Deterministic Simulators</div>
      </div>
    </aside>
  );
};
