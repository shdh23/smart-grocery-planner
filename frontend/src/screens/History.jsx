import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getHistory } from '../api/client';

const STATUS_STYLE = {
  complete:  { color: 'var(--sage)',  bg: 'var(--sage-lt)',  label: 'Complete'  },
  running:   { color: 'var(--amber)', bg: 'var(--amber-lt)', label: 'Running'   },
  failed:    { color: 'var(--red)',   bg: '#FDECEA',         label: 'Failed'    },
  confirmed: { color: 'var(--sage)',  bg: 'var(--sage-lt)',  label: 'Confirmed' },
};

export default function History() {
  const navigate = useNavigate();
  const [plans,   setPlans]   = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getHistory(20).then(({ data }) => { setPlans(data); setLoading(false); });
  }, []);

  if (loading) return (
    <div className="page"><div className="empty-state"><div className="spinner" /><p>Loading history…</p></div></div>
  );

  if (!plans.length) return (
    <div className="page">
      <h1 style={{ fontSize: '1.8rem', marginBottom: 8 }}>History</h1>
      <div className="empty-state" style={{ marginTop: 48 }}>
        <h2>No plans yet</h2>
        <p>Your completed grocery plans will appear here.</p>
        <button className="btn btn-primary" style={{ marginTop: 20 }} onClick={() => navigate('/')}>Plan this week →</button>
      </div>
    </div>
  );

  return (
    <div className="page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <h1 style={{ fontSize: '1.8rem', marginBottom: 4 }}>History</h1>
          <p style={{ color: 'var(--muted)', fontSize: '0.88rem' }}>{plans.length} past plans</p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/')}>+ New plan</button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {plans.map(plan => {
          const s   = STATUS_STYLE[plan.status] || STATUS_STYLE.complete;
          const dt  = new Date(plan.created_at);
          const ago = formatAgo(dt);

          return (
            <div
              key={plan.plan_id}
              className="card"
              style={{ cursor: plan.status === 'complete' || plan.status === 'confirmed' ? 'pointer' : 'default', transition: 'box-shadow 0.15s' }}
              onClick={() => {
                if (plan.status === 'complete' || plan.status === 'confirmed') {
                  navigate(`/list/${plan.plan_id}`);
                }
              }}
              onMouseEnter={e => { if (plan.status !== 'running') e.currentTarget.style.boxShadow = '0 4px 20px rgba(26,24,20,0.1)'; }}
              onMouseLeave={e => { e.currentTarget.style.boxShadow = ''; }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6, flexWrap: 'wrap' }}>
                    <span
                      style={{
                        fontSize: '0.72rem', fontWeight: 600, padding: '2px 10px',
                        borderRadius: '20px', background: s.bg, color: s.color,
                        textTransform: 'uppercase', letterSpacing: '0.05em'
                      }}
                    >{s.label}</span>
                    <span style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>{ago}</span>
                    <span style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>·</span>
                    <span style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>{plan.num_people} people</span>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {plan.meals.map(m => (
                      <span key={m} className="tag" style={{ fontSize: '0.82rem' }}>{m}</span>
                    ))}
                  </div>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontSize: '0.78rem', color: 'var(--muted)' }}>
                    Week of {new Date(plan.week_start_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  </div>
                  {(plan.status === 'complete' || plan.status === 'confirmed') && (
                    <div style={{ fontSize: '0.82rem', color: 'var(--sage)', marginTop: 4 }}>View list →</div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatAgo(date) {
  const diff = Math.floor((Date.now() - date.getTime()) / 1000);
  if (diff < 60)   return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400)return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}
