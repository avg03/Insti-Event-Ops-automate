import React, { useEffect, useState, useRef, useCallback } from 'react';
import type { EventState, EventSummary, TimelineItem, EventBrief } from './types';
import {
  fetchEvents,
  fetchEvent,
  fetchTimeline,
  createEvent,
  simulateDisruption,
} from './api';
import { Sidebar, type TabKey } from './components/Sidebar';
import { Header } from './components/Header';
import { OverviewTab } from './components/OverviewTab';
import { IntakeForm } from './components/IntakeForm';
import { GuestDeskTab } from './components/GuestDeskTab';
import { ProcurementTab } from './components/ProcurementTab';
import { RecoveryLabTab } from './components/RecoveryLabTab';
import { CampaignsTab } from './components/CampaignsTab';
import { AuditTrailTab } from './components/AuditTrailTab';
import './styles.css';

export const App: React.FC = () => {
  const [eventsList, setEventsList] = useState<EventSummary[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string>('');
  const [currentEvent, setCurrentEvent] = useState<EventState | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [activeTab, setActiveTab] = useState<TabKey>('overview');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [notification, setNotification] = useState<string | null>(null);

  const pollingRef = useRef<number | null>(null);

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 4000);
  };

  // Load events list on startup
  const refreshEventsList = useCallback(async () => {
    try {
      const list = await fetchEvents();
      setEventsList(list);
      if (list.length > 0 && !selectedEventId) {
        setSelectedEventId(list[0].event_id);
      } else if (list.length === 0) {
        setActiveTab('intake');
      }
    } catch (err) {
      console.error('Failed to load events:', err);
    }
  }, [selectedEventId]);

  useEffect(() => {
    refreshEventsList();
  }, [refreshEventsList]);

  // Load selected event details and timeline
  const loadEventData = useCallback(async (eventId: string) => {
    if (!eventId) return;
    try {
      const [evData, tlData] = await Promise.all([
        fetchEvent(eventId),
        fetchTimeline(eventId),
      ]);
      setCurrentEvent(evData);
      setTimeline(tlData);
    } catch (err) {
      console.error('Failed to load event data:', err);
    }
  }, []);

  useEffect(() => {
    if (selectedEventId) {
      setIsLoading(true);
      loadEventData(selectedEventId).finally(() => setIsLoading(false));
    }
  }, [selectedEventId, loadEventData]);

  // Adaptive polling loop
  useEffect(() => {
    if (!selectedEventId) return;

    const poll = async () => {
      try {
        const evData = await fetchEvent(selectedEventId);
        setCurrentEvent(evData);
        const tlData = await fetchTimeline(selectedEventId);
        setTimeline(tlData);
      } catch (err) {
        // ignore polling error
      }
    };

    const isRunning =
      currentEvent?.status === 'PLANNING' ||
      currentEvent?.status === 'RUNNING' ||
      currentEvent?.status === 'IN_PROGRESS';

    const intervalMs = isRunning ? 1500 : 5000;

    pollingRef.current = window.setInterval(poll, intervalMs);
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [selectedEventId, currentEvent?.status]);

  const handleCreateEvent = async (brief: EventBrief) => {
    setIsSubmitting(true);
    try {
      const res = await createEvent(brief);
      showNotification(`Event ${res.event_id} created! Agent is now coordinating resources.`);
      await refreshEventsList();
      setSelectedEventId(res.event_id);
      setActiveTab('overview');
    } catch (err: any) {
      throw err;
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSimulateDisruption = async (
    type: 'VENDOR_CANCELLED' | 'GUEST_CANCELLED' | 'ATTENDANCE_CHANGED',
    payload: { target_id?: string; new_count?: number }
  ) => {
    if (!selectedEventId) return;
    setIsSimulating(true);
    try {
      const res = await simulateDisruption(selectedEventId, type, payload);
      showNotification(`Disruption simulated: ${type}. Restored state: ${res.status}`);
      await loadEventData(selectedEventId);
      return res;
    } catch (err: any) {
      throw err;
    } finally {
      setIsSimulating(false);
    }
  };

  const handleRefresh = async () => {
    if (selectedEventId) {
      setIsLoading(true);
      await loadEventData(selectedEventId);
      await refreshEventsList();
      setIsLoading(false);
      showNotification('State synchronized with database.');
    }
  };

  const openIssuesCount =
    currentEvent?.issues?.filter((i) => i.status === 'OPEN' || i.status === 'RECOVERING').length || 0;

  return (
    <div className="app-container">
      <Sidebar
        activeTab={activeTab}
        onTabChange={(tab) => setActiveTab(tab)}
        openIssuesCount={openIssuesCount}
      />

      <div className="main-wrapper">
        <Header
          currentEvent={currentEvent}
          eventsList={eventsList}
          selectedEventId={selectedEventId}
          onSelectEvent={(id) => setSelectedEventId(id)}
          onNewEventClick={() => setActiveTab('intake')}
          onRefresh={handleRefresh}
          isLoading={isLoading}
        />

        {notification && (
          <div
            style={{
              backgroundColor: 'var(--primary)',
              color: 'white',
              padding: '10px 24px',
              fontSize: '0.85rem',
              fontWeight: 500,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span>{notification}</span>
            <button
              onClick={() => setNotification(null)}
              style={{ background: 'none', border: 'none', color: 'white', cursor: 'pointer', fontSize: '0.9rem' }}
            >
              ✕
            </button>
          </div>
        )}

        <main className="content-pane">
          {activeTab === 'intake' && (
            <IntakeForm onSubmit={handleCreateEvent} isSubmitting={isSubmitting} />
          )}

          {activeTab !== 'intake' && !currentEvent && (
            <div className="card" style={{ textAlign: 'center', padding: '60px 20px' }}>
              <h2 style={{ marginBottom: '12px' }}>Welcome to EventOps Autopilot</h2>
              <p style={{ color: 'var(--text-muted)', marginBottom: '24px', maxWidth: '500px', margin: '0 auto 24px' }}>
                There are no active events in the SQLite store yet. Submit your first event brief to run real Crustdata speaker discovery and sandbox procurement.
              </p>
              <button className="btn btn-primary" onClick={() => setActiveTab('intake')}>
                Create Your First Event
              </button>
            </div>
          )}

          {currentEvent && activeTab === 'overview' && (
            <OverviewTab
              event={currentEvent}
              timeline={timeline}
              onTriggerDisruptionTab={() => setActiveTab('recovery')}
            />
          )}

          {currentEvent && activeTab === 'guests' && (
            <GuestDeskTab event={currentEvent} />
          )}

          {currentEvent && activeTab === 'procurement' && (
            <ProcurementTab event={currentEvent} />
          )}

          {currentEvent && activeTab === 'recovery' && (
            <RecoveryLabTab
              event={currentEvent}
              onSimulateDisruption={handleSimulateDisruption}
              isSimulating={isSimulating}
            />
          )}

          {currentEvent && activeTab === 'campaigns' && (
            <CampaignsTab event={currentEvent} />
          )}

          {currentEvent && activeTab === 'audit' && (
            <AuditTrailTab event={currentEvent} timeline={timeline} />
          )}
        </main>
      </div>
    </div>
  );
};

export default App;
