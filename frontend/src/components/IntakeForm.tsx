import React, { useState } from 'react';
import { Send, Sparkles, AlertCircle } from 'lucide-react';
import type { EventBrief } from '../types';

interface IntakeFormProps {
  onSubmit: (brief: EventBrief) => Promise<void>;
  isSubmitting: boolean;
}

export const IntakeForm: React.FC<IntakeFormProps> = ({ onSubmit, isSubmitting }) => {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 5);
  const dateStr = tomorrow.toISOString().split('T')[0];

  const defaultBrief: EventBrief = {
    title: 'AI Systems & LLM Architecture Summit',
    topic: 'Machine Learning and AI systems',
    city: 'Mumbai',
    timezone: 'Asia/Kolkata',
    starts_at: `${dateStr}T16:00:00+05:30`,
    ends_at: `${dateStr}T19:00:00+05:30`,
    budget_inr: 25000,
    expected_attendance: 120,
    venue_capacity: 150,
    guest_count: 2,
    mandatory_resources: ['catering', 'av'],
    dietary_requirements: ['vegetarian_option'],
    promotion_requested: true,
  };

  const [brief, setBrief] = useState<EventBrief>(defaultBrief);
  const [error, setError] = useState<string | null>(null);

  const applyPreset = (presetType: 'ml' | 'robotics' | 'cloud') => {
    if (presetType === 'ml') {
      setBrief({
        ...defaultBrief,
        title: 'AI Systems & LLM Architecture Summit',
        topic: 'Machine Learning and AI systems',
        budget_inr: 25000,
        expected_attendance: 120,
        venue_capacity: 150,
        guest_count: 2,
      });
    } else if (presetType === 'robotics') {
      setBrief({
        ...defaultBrief,
        title: 'Robotics & Autonomous Hardware Colloquium',
        topic: 'Robotics and Embedded Systems',
        budget_inr: 20000,
        expected_attendance: 80,
        venue_capacity: 100,
        guest_count: 1,
      });
    } else {
      setBrief({
        ...defaultBrief,
        title: 'Cloud Infrastructure & High-Scale Systems',
        topic: 'Cloud Computing and DevOps',
        budget_inr: 30000,
        expected_attendance: 140,
        venue_capacity: 160,
        guest_count: 2,
      });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validation
    if (brief.expected_attendance > brief.venue_capacity) {
      setError(
        `Expected attendance (${brief.expected_attendance}) cannot exceed venue capacity (${brief.venue_capacity}).`
      );
      return;
    }
    if (new Date(brief.ends_at) <= new Date(brief.starts_at)) {
      setError('Event end time must be after the start time.');
      return;
    }
    if (brief.budget_inr <= 0) {
      setError('Budget must be greater than zero.');
      return;
    }

    try {
      await onSubmit(brief);
    } catch (err: any) {
      setError(err?.message || 'Failed to submit event');
    }
  };

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
      <div className="card">
        <div className="card-header">
          <div>
            <h2>Event Intake & Sandbox Provisioning</h2>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Specify event constraints. Crustdata will search real speaker candidates; vendor simulator will reserve resources.
            </div>
          </div>
          <span className="badge badge-live-data">
            <Sparkles size={12} /> Autonomous Planner
          </span>
        </div>

        {/* Quick Presets */}
        <div style={{ marginBottom: '20px', display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>Quick Presets:</span>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            onClick={() => applyPreset('ml')}
          >
            AI Systems (2 Guests)
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            onClick={() => applyPreset('robotics')}
          >
            Robotics Colloquium (1 Guest)
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            onClick={() => applyPreset('cloud')}
          >
            Cloud Systems (2 Guests)
          </button>
        </div>

        {error && (
          <div
            style={{
              padding: '12px 16px',
              backgroundColor: 'var(--danger-light)',
              borderRadius: 'var(--radius-md)',
              marginBottom: '20px',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              color: 'var(--danger)',
              fontSize: '0.85rem',
            }}
          >
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Event Title</label>
            <input
              type="text"
              className="form-input"
              value={brief.title}
              onChange={(e) => setBrief({ ...brief, title: e.target.value })}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Topic / Subject Domain (used for real Crustdata speaker discovery)</label>
            <input
              type="text"
              className="form-input"
              value={brief.topic}
              onChange={(e) => setBrief({ ...brief, topic: e.target.value })}
              required
            />
            <div className="form-helper">
              Crustdata queries people matching this topic and checks current titles, experience, and organization.
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div className="form-group">
              <label className="form-label">City</label>
              <input
                type="text"
                className="form-input"
                value={brief.city}
                onChange={(e) => setBrief({ ...brief, city: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Timezone</label>
              <input
                type="text"
                className="form-input"
                value={brief.timezone}
                onChange={(e) => setBrief({ ...brief, timezone: e.target.value })}
                required
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div className="form-group">
              <label className="form-label">Starts At</label>
              <input
                type="text"
                className="form-input"
                value={brief.starts_at}
                onChange={(e) => setBrief({ ...brief, starts_at: e.target.value })}
                placeholder="YYYY-MM-DDTHH:MM:SS+05:30"
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Ends At</label>
              <input
                type="text"
                className="form-input"
                value={brief.ends_at}
                onChange={(e) => setBrief({ ...brief, ends_at: e.target.value })}
                placeholder="YYYY-MM-DDTHH:MM:SS+05:30"
                required
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
            <div className="form-group">
              <label className="form-label">Total Budget (₹ INR)</label>
              <input
                type="number"
                className="form-input"
                value={brief.budget_inr}
                onChange={(e) => setBrief({ ...brief, budget_inr: parseInt(e.target.value) || 0 })}
                min={1000}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Expected Attendance</label>
              <input
                type="number"
                className="form-input"
                value={brief.expected_attendance}
                onChange={(e) => setBrief({ ...brief, expected_attendance: parseInt(e.target.value) || 0 })}
                min={1}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Venue Capacity</label>
              <input
                type="number"
                className="form-input"
                value={brief.venue_capacity}
                onChange={(e) => setBrief({ ...brief, venue_capacity: parseInt(e.target.value) || 0 })}
                min={1}
                required
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div className="form-group">
              <label className="form-label">Required Speaker Count</label>
              <input
                type="number"
                className="form-input"
                value={brief.guest_count}
                onChange={(e) => setBrief({ ...brief, guest_count: parseInt(e.target.value) || 0 })}
                min={0}
                max={5}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Dietary Requirements</label>
              <input
                type="text"
                className="form-input"
                value={brief.dietary_requirements.join(', ')}
                onChange={(e) =>
                  setBrief({
                    ...brief,
                    dietary_requirements: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                  })
                }
                placeholder="e.g. vegetarian_option"
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Mandatory Resources</label>
            <div style={{ display: 'flex', gap: '16px', marginTop: '6px' }}>
              {['catering', 'av', 'seating'].map((res) => (
                <label key={res} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem' }}>
                  <input
                    type="checkbox"
                    checked={brief.mandatory_resources.includes(res)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setBrief({ ...brief, mandatory_resources: [...brief.mandatory_resources, res] });
                      } else {
                        setBrief({ ...brief, mandatory_resources: brief.mandatory_resources.filter((r) => r !== res) });
                      }
                    }}
                  />
                  <span style={{ textTransform: 'capitalize' }}>{res}</span>
                </label>
              ))}
            </div>
          </div>

          <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting}
              style={{ padding: '10px 24px', fontSize: '0.95rem' }}
            >
              <Send size={16} />
              <span>{isSubmitting ? 'Provisioning Sandbox...' : 'Organize Event (Run Agent)'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
