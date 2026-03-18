import { useState } from 'react';
import { completeOnboarding } from '../api/client';

const STEPS = [
  {
    emoji: '🛒',
    title: 'Welcome to Grocery Planner',
    desc: 'Pantry-aware, FSA-smart. Takes about 2 minutes to set up.',
    detail: null,
  },
  {
    emoji: '🥫',
    title: 'Set up your pantry',
    desc: 'Go to Settings → Pantry and use the quick setup bundles. Pick whichever apply — spices, oils, grains — and adjust quantities to what you have.',
    detail: ['Spices bundle', 'Oils & basics', 'Grains & lentils'],
    detailColor: '#0d9488',
    detailBg: 'rgba(13,148,136,0.08)',
  },
  {
    emoji: '🏪',
    title: 'Tell us where you shop',
    desc: 'In Settings → Routing Rules, add your regulars. We\'ll route ingredients to the right store automatically.',
    detail: ['paneer → indian store', 'basmati rice → costco', 'medicine → target'],
    detailColor: '#d97706',
    detailBg: 'rgba(217,119,6,0.08)',
  },
  {
    emoji: '🍽️',
    title: 'Just chat to plan',
    desc: 'Tell the planner what you want to cook in plain English. Add notes for special instructions.',
    detail: null,
    example: '"Idli - I get batter from Idli Express"',
  },
  {
    emoji: '💊',
    title: 'Add extras too',
    desc: 'Medicine, supplements, household items — add them in chat or the extras section. We check FSA/HSA eligibility automatically.',
    detail: ['ibuprofen 200mg', 'vitamin D3', 'paper towels'],
    detailColor: '#7c3aed',
    detailBg: 'rgba(124,58,237,0.08)',
  },
  {
    emoji: '🧠',
    title: 'It learns from you',
    desc: 'Remove items and tell it why — wrong store, already have it, not in my recipe. It remembers for next time.',
    detail: null,
  },
];

export default function Onboarding({ onComplete }) {
  const [step,    setStep]    = useState(0);
  const [loading, setLoading] = useState(false);

  const isLast = step === STEPS.length - 1;
  const s      = STEPS[step];

  const next = async () => {
    if (isLast) {
      setLoading(true);
      try { await completeOnboarding(); } catch {}
      onComplete();
    } else {
      setStep(step + 1);
    }
  };

  const skip = async () => {
    try { await completeOnboarding(); } catch {}
    onComplete();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="onboarding-step-title"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(26, 24, 20, 0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: 24,
      }}
    >
      <div
        style={{
          background: 'var(--white)',
          border: '1px solid var(--border)',
          borderRadius: 20,
          width: '100%',
          maxWidth: 460,
          overflow: 'hidden',
          boxShadow: '0 24px 48px rgba(26, 24, 20, 0.2)',
        }}
      >
        {/* Progress bar */}
        <div style={{ display: 'flex', gap: 4, padding: '20px 24px 0' }}>
          {STEPS.map((_, i) => (
            <div key={i} style={{
              flex: 1, height: 3, borderRadius: 2,
              background: i <= step ? '#C96442' : 'var(--border)',
              transition: 'background 0.3s',
            }}/>
          ))}
        </div>

        {/* Content */}
        <div style={{ padding: '28px 28px 0' }}>
          <div style={{
            width: 52, height: 52, borderRadius: 14,
            background: 'var(--cream)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 26, marginBottom: 18,
            border: '0.5px solid var(--border)',
          }}>
            {s.emoji}
          </div>

          <h2 id="onboarding-step-title" style={{ fontSize: 18, fontWeight: 500, marginBottom: 10, color: 'var(--ink)' }}>
            {s.title}
          </h2>
          <p style={{ fontSize: 14, color: 'var(--muted)', lineHeight: 1.6, marginBottom: 20 }}>
            {s.desc}
          </p>

          {s.detail && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 20 }}>
              {s.detail.map(d => (
                <span key={d} style={{
                  fontSize: 12, padding: '4px 12px', borderRadius: 20,
                  background: s.detailBg, color: s.detailColor,
                  border: `0.5px solid ${s.detailColor}40`,
                  fontWeight: 500,
                }}>{d}</span>
              ))}
            </div>
          )}

          {s.example && (
            <div style={{
              background: 'var(--cream)',
              border: '0.5px solid var(--border)',
              borderRadius: 10, padding: '10px 14px',
              fontSize: 13, color: 'var(--muted)',
              fontStyle: 'italic', marginBottom: 20,
            }}>
              {s.example}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 28px 24px',
          borderTop: '0.5px solid var(--border)',
          marginTop: 8,
        }}>
          <button onClick={skip} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontSize: 13, color: 'var(--muted)', padding: 0,
          }}>
            Skip
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <span style={{ fontSize: 12, color: 'var(--muted)' }}>
              {step + 1} of {STEPS.length}
            </span>
            <button onClick={next} disabled={loading}
              style={{
                padding: '9px 22px', borderRadius: 10,
                background: '#C96442', color: '#fff',
                border: 'none', cursor: 'pointer',
                fontSize: 14, fontWeight: 500,
                transition: 'opacity 0.15s',
                opacity: loading ? 0.7 : 1,
              }}>
              {loading ? 'Starting…' : isLast ? 'Start planning' : 'Next'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
