import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';

const NODE_META = {
  recipe_agent:             { icon: '🍽️',  label: 'Extracting ingredients',       detail: 'Scaling quantities for your meals' },
  extra_items_agent:        { icon: '🛍️',  label: 'Structuring extra items',       detail: 'Categorising for FSA checking'     },
  consolidation_agent:      { icon: '🔄',  label: 'Consolidating list',            detail: 'Merging duplicates across meals'   },
  pantry_checker_agent:     { icon: '🥫',  label: 'Checking your pantry',          detail: 'Removing items you already have'  },
  fsa_checker_agent:        { icon: '💊',  label: 'Checking FSA/HSA eligibility',  detail: 'Searching FSA Store + web'        },
  store_router_agent_food:  { icon: '🏪',  label: 'Routing food to stores',        detail: 'Verifying stock via web search'   },
  store_router_agent_extra: { icon: '🏪',  label: 'Routing extras to stores',      detail: 'Finding best store for each item' },
  output_formatter:         { icon: '📋',  label: 'Assembling final list',         detail: 'Grouping by store'                },
};

export default function AgentProgress() {
  const { planId } = useParams();
  const navigate   = useNavigate();

  const [events,   setEvents]   = useState([]);  // { type, data }
  const [done,     setDone]     = useState(false);
  const [errMsg,   setErrMsg]   = useState('');
  const [stats,    setStats]    = useState(null);

  useEffect(() => {
    const baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const es = new EventSource(`${baseURL}/api/stream/${planId}`);

    es.addEventListener('pipeline_start', e => {
      const d = JSON.parse(e.data);
      setEvents(prev => [...prev, { type: 'start', data: d }]);
    });

    es.addEventListener('node_complete', e => {
      const d = JSON.parse(e.data);
      if (d.node === 'merge_barrier') return; // skip internal node
      setEvents(prev => [...prev, { type: 'node', data: d }]);
    });

    es.addEventListener('pipeline_complete', e => {
      const d = JSON.parse(e.data);
      setStats(d.stats);
      setEvents(prev => [...prev, { type: 'complete', data: d }]);
      setDone(true);
    });

    es.addEventListener('pipeline_error', e => {
      const d = JSON.parse(e.data);
      setErrMsg(d.message);
      setDone(true);
      es.close();
    });

    es.addEventListener('done', () => es.close());

    es.onerror = () => {
      // SSE will retry automatically — only set error if stream never started
      if (!events.length) setErrMsg('Could not connect to pipeline stream.');
    };

    return () => es.close();
  }, [planId]);

  return (
    <div className="page" style={{ maxWidth: 600 }}>
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: '1.8rem', marginBottom: 6 }}>Building your list</h1>
        <p style={{ color: 'var(--muted)', fontSize: '0.88rem' }}>
          Each agent is working through your request in real time.
        </p>
      </div>

      {errMsg && (
        <div className="alert alert-error" style={{ marginBottom: 24 }}>
          {errMsg}
        </div>
      )}

      <div className="card">
        <ul className="progress-list">

          {/* ── Pipeline start ── */}
          {events.filter(e => e.type === 'start').map((e, i) => (
            <li key={`start-${i}`} className="progress-item" style={{ animationDelay: '0ms' }}>
              <div className="progress-icon">✦</div>
              <div className="progress-text">
                <strong>Pipeline started</strong>
                <span>{e.data.meals?.join(', ')} · {e.data.people} people</span>
              </div>
            </li>
          ))}

          {/* ── Node events ── */}
          {events.filter(e => e.type === 'node').map((e, i) => {
            const meta = NODE_META[e.data.node] || { icon: '⚙️', label: e.data.node, detail: '' };
            return (
              <li key={`node-${i}`} className="progress-item" style={{ animationDelay: `${i * 40}ms` }}>
                <div className="progress-icon">{meta.icon}</div>
                <div className="progress-text">
                  <strong>{meta.label}</strong>
                  <span>{meta.detail}</span>
                </div>
              </li>
            );
          })}

          {/* ── Pending spinner if not done ── */}
          {!done && !errMsg && (
            <li className="progress-item" style={{ animationDelay: '0ms' }}>
              <div className="progress-icon pending">◌</div>
              <div className="progress-text">
                <strong style={{ color: 'var(--muted)' }}>Working…</strong>
              </div>
            </li>
          )}

          {/* ── Complete ── */}
          {done && !errMsg && (
            <li className="progress-item" style={{ animationDelay: '0ms' }}>
              <div className="progress-icon" style={{ background: 'var(--sage-lt)', color: 'var(--sage)' }}>✓</div>
              <div className="progress-text">
                <strong>Done!</strong>
                {stats && (
                  <span>
                    {stats.total_stores} stores · {stats.food_count} food items
                    {stats.extra_count  ? ` · ${stats.extra_count} extras`  : ''}
                    {stats.fsa_count    ? ` · 💊 ${stats.fsa_count} FSA`    : ''}
                    {stats.pantry_skipped ? ` · 🥫 ${stats.pantry_skipped} from pantry` : ''}
                  </span>
                )}
              </div>
            </li>
          )}
        </ul>
      </div>

      {done && !errMsg && (
        <div style={{ marginTop: 24, display: 'flex', justifyContent: 'flex-end' }}>
          <button
            className="btn btn-primary"
            onClick={() => navigate(`/list/${planId}`)}
            style={{ padding: '12px 32px' }}
          >
            View grocery list →
          </button>
        </div>
      )}

      {errMsg && (
        <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn btn-outline" onClick={() => navigate('/')}>← Try again</button>
        </div>
      )}
    </div>
  );
}
