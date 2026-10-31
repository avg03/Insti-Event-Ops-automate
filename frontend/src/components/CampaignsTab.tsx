import React, { useEffect, useState } from 'react';
import { Megaphone, Clapperboard, Calendar, Sparkles, Hash, Copy, Check } from 'lucide-react';
import type { CampaignPromotion, EventState } from '../types';
import { fetchPromotion } from '../api';

interface CampaignsTabProps {
  event: EventState;
}

export const CampaignsTab: React.FC<CampaignsTabProps> = ({ event }) => {
  const [promotion, setPromotion] = useState<CampaignPromotion | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    let isMounted = true;
    const load = async () => {
      try {
        setIsLoading(true);
        const data = await fetchPromotion(event.event_id);
        if (isMounted) setPromotion(data);
      } catch (err) {
        console.error('Failed to fetch promotion campaign:', err);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };
    load();
    return () => {
      isMounted = false;
    };
  }, [event.event_id]);

  const copyPosterCopy = () => {
    if (!promotion) return;
    const p = promotion.poster_copy;
    const text = `${p.headline}\n${p.subheadline}\n\n📍 ${p.date_and_venue}\n\nKeynotes:\n${p.featured_speakers.map((s) => `• ${s}`).join('\n')}\n\nTakeaways:\n${p.key_takeaways.map((t) => `• ${t}`).join('\n')}\n\nRSVP: ${p.registration_cta}\n\n${p.hashtags.join(' ')}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isLoading) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
        Generating campaign assets and reel storyboard...
      </div>
    );
  }

  if (!promotion) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
        No campaign assets available for this event.
      </div>
    );
  }

  const poster = promotion.poster_copy;

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <div>
            <h2>Campus Campaign & Social Storyboard (P1)</h2>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Autonomous promotional copy and video reel storyboard for student delegates
            </div>
          </div>
          <span className="badge badge-simulated">
            <Sparkles size={12} /> Draft Simulated
          </span>
        </div>

        <div style={{ padding: '10px 14px', backgroundColor: 'var(--amber-light)', borderRadius: 'var(--radius-md)', fontSize: '0.8rem', color: 'var(--amber)', marginBottom: '24px' }}>
          <strong>Notice:</strong> {promotion.disclaimer}
        </div>

        {/* Poster Copy Card */}
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '24px', marginBottom: '28px' }}>
          <div
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: '24px',
              backgroundColor: 'var(--bg-surface)',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
              <div>
                <span className="badge badge-planning" style={{ marginBottom: '8px' }}>
                  Official Announcement Copy
                </span>
                <h3 style={{ fontSize: '1.35rem', color: 'var(--primary)' }}>{poster.headline}</h3>
                <div style={{ fontStyle: 'italic', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                  {poster.subheadline}
                </div>
              </div>

              <button
                className="btn btn-secondary"
                style={{ padding: '6px 12px', fontSize: '0.75rem' }}
                onClick={copyPosterCopy}
              >
                {copied ? <Check size={14} color="var(--moss-green)" /> : <Copy size={14} />}
                <span>{copied ? 'Copied!' : 'Copy Text'}</span>
              </button>
            </div>

            <div style={{ fontSize: '0.85rem', marginBottom: '16px', color: 'var(--text-primary)' }}>
              <strong>Date & Location:</strong> {poster.date_and_venue}
            </div>

            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '6px' }}>Featured Keynote Speakers:</div>
              <ul style={{ paddingLeft: '18px', fontSize: '0.825rem', color: 'var(--text-primary)' }}>
                {poster.featured_speakers.map((s, idx) => (
                  <li key={idx}>{s}</li>
                ))}
              </ul>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '6px' }}>Core Highlights:</div>
              <ul style={{ paddingLeft: '18px', fontSize: '0.825rem', color: 'var(--text-muted)' }}>
                {poster.key_takeaways.map((t, idx) => (
                  <li key={idx}>{t}</li>
                ))}
              </ul>
            </div>

            <div style={{ padding: '12px', backgroundColor: 'var(--bg-muted)', borderRadius: 'var(--radius-sm)', fontSize: '0.825rem', marginBottom: '16px' }}>
              <strong>Call to Action:</strong> {poster.registration_cta}
            </div>

            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {poster.hashtags.map((h, idx) => (
                <span key={idx} style={{ fontSize: '0.75rem', color: 'var(--primary)', fontWeight: 500 }}>
                  {h}
                </span>
              ))}
            </div>
          </div>

          {/* Schedule Blueprint */}
          <div
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: '24px',
              backgroundColor: 'var(--bg-muted)',
            }}
          >
            <h3 style={{ fontSize: '1.05rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Calendar size={18} /> Schedule Blueprint
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {promotion.schedule_summary.map((slot, idx) => (
                <div
                  key={idx}
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border)',
                  }}
                >
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--primary)' }}>{slot.time}</div>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{slot.session}</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{slot.speaker}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Short-Form Video Reel Storyboard */}
        <div>
          <h3 style={{ fontSize: '1.15rem', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Clapperboard size={20} color="var(--primary)" /> 4-Scene Reel Storyboard (Short-Form Video)
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
            {promotion.reel_storyboard.map((scene) => (
              <div key={scene.scene} className="storyboard-scene">
                <div className="scene-header">
                  <span>Scene {scene.scene}</span>
                  <span className="badge badge-planning" style={{ fontSize: '0.7rem' }}>
                    {scene.duration_seconds}s
                  </span>
                </div>

                <div style={{ fontSize: '0.825rem', marginBottom: '10px' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem' }}>VISUAL:</div>
                  <div style={{ color: 'var(--text-primary)' }}>{scene.visual}</div>
                </div>

                <div style={{ fontSize: '0.825rem', marginBottom: '10px' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem' }}>VOICEOVER:</div>
                  <div style={{ fontStyle: 'italic', color: 'var(--primary-dark)' }}>"{scene.audio_voiceover}"</div>
                </div>

                <div style={{ fontSize: '0.8rem', backgroundColor: 'var(--bg-muted)', padding: '6px 10px', borderRadius: 'var(--radius-sm)' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.7rem', color: 'var(--text-muted)' }}>ON-SCREEN TEXT:</span>
                  <div>{scene.onscreen_text}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
