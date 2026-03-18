import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { parseIntent, createPlan, getConfig } from '../api/client';

const STORE_LABELS = {
  trader_joes:  "Trader Joe's",
  costco:       'Costco',
  indian_store: 'Indian Store',
  target:       'Target',
  whole_foods:  'Whole Foods',
  walmart:      'Walmart',
  safeway:      'Safeway',
  hmart:        'H Mart',
};

function storeLabel(id) {
  return STORE_LABELS[id] || id.replace(/_/g, ' ');
}

function PlanCard({ state, onRemoveMeal, onRemoveExtra, onRemoveStore, onPeopleChange, onBuild, building }) {
  const { meals = [], extra_items = [], active_stores = [], num_people } = state;
  if (!meals.length && !extra_items.length) return null;

  const Tag = ({ label, onRemove, color }) => (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '3px 10px 3px 12px',
      borderRadius: 20,
      background: color === 'teal' ? 'rgba(26,188,156,0.12)' : color === 'amber' ? 'rgba(245,158,11,0.12)' : 'rgba(100,116,139,0.12)',
      color: color === 'teal' ? '#0d9488' : color === 'amber' ? '#d97706' : 'var(--color-text-secondary)',
      fontSize: 13, fontWeight: 500,
      border: `0.5px solid ${color === 'teal' ? 'rgba(13,148,136,0.3)' : color === 'amber' ? 'rgba(217,119,6,0.3)' : 'rgba(100,116,139,0.2)'}`,
    }}>
      {label}
      <button onClick={onRemove} style={{ background: 'none', border: 'none', cursor: 'pointer', opacity: 0.5, fontSize: 14, padding: '0 0 0 2px', lineHeight: 1, color: 'inherit' }}>×</button>
    </span>
  );

  return (
    <div style={{
      marginTop: 10,
      background: 'var(--color-background-secondary)',
      border: '0.5px solid var(--color-border-tertiary)',
      borderRadius: 12,
      overflow: 'hidden',
      fontSize: 13,
    }}>
      {meals.length > 0 && (
        <div style={{ padding: '10px 14px', borderBottom: extra_items.length || active_stores.length ? '0.5px solid var(--color-border-tertiary)' : 'none' }}>
          <p style={{ fontSize: 11, fontWeight: 500, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 7 }}>Meals</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {meals.map(m => <Tag key={m} label={m} color="teal" onRemove={() => onRemoveMeal(m)} />)}
          </div>
        </div>
      )}
      {extra_items.length > 0 && (
        <div style={{ padding: '10px 14px', borderBottom: active_stores.length ? '0.5px solid var(--color-border-tertiary)' : 'none' }}>
          <p style={{ fontSize: 11, fontWeight: 500, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 7 }}>Extras</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {extra_items.map(x => <Tag key={x} label={x} color="amber" onRemove={() => onRemoveExtra(x)} />)}
          </div>
        </div>
      )}
      <div style={{ padding: '10px 14px', display: 'flex', gap: 20, flexWrap: 'wrap', borderBottom: '0.5px solid var(--color-border-tertiary)' }}>
        <div>
          <p style={{ fontSize: 11, fontWeight: 500, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 7 }}>People</p>
          <div style={{ display: 'inline-flex', alignItems: 'center', border: '0.5px solid var(--color-border-secondary)', borderRadius: 8, overflow: 'hidden' }}>
            <button onClick={() => onPeopleChange(Math.max(1, (num_people || 2) - 1))}
              style={{ width: 28, height: 28, background: 'var(--color-background-primary)', border: 'none', cursor: 'pointer', fontSize: 14, color: 'var(--color-text-secondary)' }}>−</button>
            <span style={{ width: 32, textAlign: 'center', fontSize: 13, fontWeight: 500, color: 'var(--color-text-primary)', borderLeft: '0.5px solid var(--color-border-tertiary)', borderRight: '0.5px solid var(--color-border-tertiary)', lineHeight: '28px' }}>
              {num_people || '?'}
            </span>
            <button onClick={() => onPeopleChange(Math.min(20, (num_people || 2) + 1))}
              style={{ width: 28, height: 28, background: 'var(--color-background-primary)', border: 'none', cursor: 'pointer', fontSize: 14, color: 'var(--color-text-secondary)' }}>+</button>
          </div>
        </div>
        {active_stores.length > 0 && (
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 11, fontWeight: 500, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 7 }}>Stores</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
              {active_stores.map(s => <Tag key={s} label={storeLabel(s)} color="gray" onRemove={() => onRemoveStore(s)} />)}
            </div>
          </div>
        )}
      </div>
      <div style={{ padding: '10px 14px' }}>
        <button onClick={onBuild} disabled={building || !meals.length || !num_people}
          style={{
            width: '100%', padding: '9px', borderRadius: 8,
            background: meals.length && num_people ? '#0d9488' : 'var(--color-background-secondary)',
            color: meals.length && num_people ? '#fff' : 'var(--color-text-tertiary)',
            border: meals.length && num_people ? 'none' : '0.5px solid var(--color-border-tertiary)',
            cursor: meals.length && num_people ? 'pointer' : 'not-allowed',
            fontSize: 13, fontWeight: 500,
          }}>
          {building ? 'Starting…' : '✦ Build my grocery list'}
        </button>
      </div>
    </div>
  );
}

function Bubble({ role, content, planState, onRemoveMeal, onRemoveExtra, onRemoveStore, onPeopleChange, onBuild, building }) {
  const isUser = role === 'user';
  return (
    <div style={{ display: 'flex', gap: 10, marginBottom: 20, alignItems: 'flex-start', flexDirection: isUser ? 'row-reverse' : 'row' }}>
      {/* Avatar */}
      <div style={{
        width: 28, height: 28, borderRadius: '50%', flexShrink: 0, marginTop: 2,
        background: isUser ? 'var(--color-background-secondary)' : '#0d9488',
        border: isUser ? '0.5px solid var(--color-border-secondary)' : 'none',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 12, fontWeight: 600,
        color: isUser ? 'var(--color-text-secondary)' : '#fff',
      }}>
        {isUser ? 'S' : (
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path d="M8 1.5L9.5 5.5L13.5 6.5L10.5 9.5L11.5 13.5L8 11.5L4.5 13.5L5.5 9.5L2.5 6.5L6.5 5.5L8 1.5Z" fill="white" stroke="white" strokeWidth="0.5" strokeLinejoin="round"/>
          </svg>
        )}
      </div>

      <div style={{ maxWidth: '80%' }}>
        {/* Bubble */}
        <div style={{
          padding: '10px 14px',
          borderRadius: isUser ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
          background: isUser ? '#0d9488' : 'var(--color-background-primary)',
          color: isUser ? '#fff' : 'var(--color-text-primary)',
          fontSize: 14, lineHeight: 1.6,
          border: isUser ? 'none' : '0.5px solid var(--color-border-secondary)',
        }}>
          {content}
        </div>

        {!isUser && planState && (
          <PlanCard
            state={planState}
            onRemoveMeal={onRemoveMeal}
            onRemoveExtra={onRemoveExtra}
            onRemoveStore={onRemoveStore}
            onPeopleChange={onPeopleChange}
            onBuild={onBuild}
            building={building}
          />
        )}
      </div>
    </div>
  );
}

const SUGGESTIONS = [
  'Palak paneer and dal tadka for 4 people',
  'Butter chicken and naan for 2 people',
  'I want to cook idli — I get batter from Idli Express',
];

export default function PlannerChat() {
  const navigate  = useNavigate();
  const bottomRef = useRef(null);

  const [messages,  setMessages]  = useState([
    { role: 'assistant', content: "What are you cooking this week? Tell me your meals, how many people, and any extras like medicine or household items.", planState: null }
  ]);
  const [input,     setInput]     = useState('');
  const [loading,   setLoading]   = useState(false);
  const [building,  setBuilding]  = useState(false);
  const [error,     setError]     = useState('');
  const [planState, setPlanState] = useState({
    meals: [], extra_items: [], active_stores: [], num_people: null,
    meal_hints: [], preferences: []
  });

  useEffect(() => {
    getConfig().then(({ data }) => {
      const stores = data.active_stores || ['trader_joes','costco','indian_store','target'];
      setPlanState(prev => ({ ...prev, active_stores: stores }));
      setMessages([{
        role: 'assistant',
        content: `What are you cooking this week? Tell me your meals, how many people, and any extras like medicine or household items.\n\nYour current stores: ${stores.map(s => storeLabel(s)).join(', ')}. You can change them anytime — just tell me.`,
        planState: null
      }]);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const history = messages
    .filter(m => m.content)
    .map(m => ({ role: m.role, content: m.content }));

  const send = async (text) => {
    if (!text.trim() || loading) return;
    setError('');
    const userMsg = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const { data } = await parseIntent(text, planState, history);
      const newState = data.state || planState;
      setPlanState(newState);

      const showCard = data.status === 'confirming' || data.status === 'ready';

      if (data.status === 'ready') {
        setMessages(prev => [...prev, { role: 'assistant', content: data.message, planState: null }]);
        await buildPlan(newState);
      } else if (data.status === 'out_of_scope') {
        setMessages(prev => [...prev, { role: 'assistant', content: data.message, planState: null }]);
      } else {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: data.message,
          planState: showCard ? newState : null
        }]);
      }
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: "Sorry, something went wrong. Could you try again?", planState: null }]);
    }
    setLoading(false);
  };

  const buildPlan = async (state) => {
    setBuilding(true);
    try {
      const { data } = await createPlan({
        meals:         state.meals,
        extra_items:   state.extra_items,
        num_people:    state.num_people || 2,
        active_stores: state.active_stores,
        meal_hints:    state.meal_hints || [],
        preferences:   state.preferences || [],
        user_id:       'default_user',
      });
      navigate(`/progress/${data.plan_id}`);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to start pipeline');
      setBuilding(false);
    }
  };

  const updateState = (patch) => {
    setPlanState(prev => {
      const next = { ...prev, ...patch };
      setMessages(msgs => msgs.map((m, i) =>
        i === msgs.length - 1 && m.planState ? { ...m, planState: next } : m
      ));
      return next;
    });
  };

  const removeMeal  = (m) => updateState({ meals:         planState.meals.filter(x => x !== m) });
  const removeExtra = (x) => updateState({ extra_items:   planState.extra_items.filter(e => e !== x) });
  const removeStore = (s) => updateState({ active_stores: planState.active_stores.filter(x => x !== s) });
  const setPeople   = (n) => updateState({ num_people: n });

  return (
    <div style={{
      maxWidth: 700, margin: '0 auto', padding: '0 20px',
      display: 'flex', flexDirection: 'column',
      height: 'calc(100vh - 64px)',
    }}>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', paddingTop: 24, paddingBottom: 8, background: 'var(--cream)' }}>
        {messages.map((m, i) => (
          <Bubble
            key={i}
            role={m.role}
            content={m.content}
            planState={m.planState}
            onRemoveMeal={removeMeal}
            onRemoveExtra={removeExtra}
            onRemoveStore={removeStore}
            onPeopleChange={setPeople}
            onBuild={() => buildPlan(planState)}
            building={building}
          />
        ))}

        {/* Typing indicator */}
        {loading && (
          <div style={{ display: 'flex', gap: 10, marginBottom: 20, alignItems: 'flex-start' }}>
            <div style={{ width: 28, height: 28, borderRadius: '50%', background: '#0d9488', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 1.5L9.5 5.5L13.5 6.5L10.5 9.5L11.5 13.5L8 11.5L4.5 13.5L5.5 9.5L2.5 6.5L6.5 5.5L8 1.5Z" fill="white" strokeWidth="0.5" strokeLinejoin="round"/></svg>
            </div>
            <div style={{ padding: '10px 16px', borderRadius: '4px 16px 16px 16px', background: 'var(--color-background-primary)', border: '0.5px solid var(--color-border-secondary)', display: 'flex', gap: 4, alignItems: 'center' }}>
              {[0,1,2].map(i => (
                <span key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--color-text-tertiary)', display: 'inline-block', animation: `bounce 1s ease-in-out ${i*0.15}s infinite` }}/>
              ))}
            </div>
          </div>
        )}

        {/* Suggestions */}
        {messages.length === 1 && (
          <div style={{ marginTop: 8, marginBottom: 16 }}>
            <p style={{ fontSize: 11, fontWeight: 500, color: 'var(--color-text-tertiary)', letterSpacing: '0.07em', textTransform: 'uppercase', marginBottom: 10, paddingLeft: 38 }}>Try saying</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingLeft: 38 }}>
              {SUGGESTIONS.map(s => (
                <button key={s} onClick={() => send(s)}
                  style={{
                    textAlign: 'left', padding: '9px 14px',
                    background: 'var(--color-background-primary)',
                    border: '0.5px solid var(--color-border-secondary)',
                    borderRadius: 10, fontSize: 13,
                    color: 'var(--color-text-secondary)', cursor: 'pointer',
                    transition: 'all 0.15s', display: 'flex', alignItems: 'center', gap: 8,
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = '#0d9488'; e.currentTarget.style.color = '#0d9488'; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--color-border-secondary)'; e.currentTarget.style.color = 'var(--color-text-secondary)'; }}
                >
                  <span style={{ fontSize: 12, opacity: 0.5 }}>↗</span> {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {error && <p style={{ fontSize: 12, color: 'var(--color-text-danger)', marginBottom: 6 }}>{error}</p>}

      {/* Input area — distinct from chat background */}
      <div style={{ padding: '8px 0 20px', background: 'var(--cream)' }}>
        <div style={{
          border: '1px solid var(--border)',
          borderRadius: 16,
          background: 'var(--white)',
          overflow: 'hidden',
          boxShadow: '0 2px 8px rgba(26,24,20,0.08)',
        }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); } }}
            placeholder="Message Grocery Planner..."
            rows={2}
            style={{
              width: '100%', resize: 'none', padding: '14px 16px 4px',
              border: 'none', outline: 'none',
              fontSize: 15, fontFamily: 'var(--font-sans)',
              background: 'transparent',
              color: 'var(--color-text-primary)',
              lineHeight: 1.5, boxSizing: 'border-box',
            }}
          />
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', padding: '6px 10px 10px' }}>
            <button onClick={() => send(input)} disabled={loading || !input.trim()}
                style={{
                  width: 34, height: 34, borderRadius: '50%', flexShrink: 0,
                  background: input.trim() ? '#C96442' : 'var(--color-background-secondary)',
                  border: 'none',
                  cursor: input.trim() ? 'pointer' : 'not-allowed',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'background 0.15s',
                }}>
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                  <path d="M8 13V3M8 3L3 8M8 3L13 8" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
          </div>
        </div>
      </div>

      <style>{`@keyframes bounce { 0%,100%{transform:translateY(0);opacity:.4} 50%{transform:translateY(-3px);opacity:1} }`}</style>
    </div>
  );
}
