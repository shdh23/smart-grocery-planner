import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getPlan, confirmPlan } from '../api/client';
import api from '../api/client';

const STORE_EMOJI = {
  trader_joes:  '🌿',
  costco:       '📦',
  indian_store: '🪔',
  target:       '🎯',
};

function StoreName({ id }) {
  const labels = {
    trader_joes:  "Trader Joe's",
    costco:       'Costco',
    indian_store: 'Indian Store',
    target:       'Target'
  };
  return <>{STORE_EMOJI[id] || '🏪'} {labels[id] || id}</>;
}

// ── Remove modal ──
function RemoveModal({ item, planId, onDone, onClose }) {
  const [reason,   setReason]   = useState('');
  const [loading,  setLoading]  = useState(false);
  const [result,   setResult]   = useState(null);
  const [error,    setError]    = useState('');

  const submit = async () => {
    if (!reason.trim()) return setError('Please tell us why.');
    setLoading(true); setError('');
    try {
      const { data } = await api.post(`/api/plan/${planId}/remove-item`, {
        ingredient_name: item.name,
        meal_name:       item.notes?.replace('for ', '').replace(' (your recipe)', '') || null,
        reason:          reason.trim(),
        store:           item.store,
        quantity:        item.quantity,
        unit:            item.unit,
      });
      setResult(data);
      setTimeout(() => { onDone(item.name); }, 1800);
    } catch (e) {
      setError(e.response?.data?.detail || 'Something went wrong.');
    }
    setLoading(false);
  };

  const ACTION_ICONS = {
    ADD_TO_PANTRY:  '🥫',
    SKIP_FOR_MEAL:  '🍽️',
    SKIP_ALWAYS:    '🚫',
    CHANGE_STORE:   '🏪',
    WRONG_QUANTITY: '✏️',
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(26,24,20,0.4)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000, padding: 24
    }}>
      <div className="card" style={{ width: '100%', maxWidth: 440, position: 'relative' }}>
        <button onClick={onClose} style={{
          position: 'absolute', top: 16, right: 16,
          background: 'none', border: 'none', cursor: 'pointer',
          fontSize: '1.2rem', color: 'var(--muted)'
        }}>×</button>

        {!result ? (
          <>
            <h2 style={{ fontSize: '1.1rem', marginBottom: 6 }}>Removing "{item.name}"</h2>
            <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginBottom: 20 }}>
              Tell us why and we'll remember it for next time.
            </p>

            {/* Quick reason buttons */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
              {[
                'I already have it at home',
                "Not in my recipe",
                'I never use this',
                'Wrong store',
                'Too much quantity',
              ].map(r => (
                <button key={r} onClick={() => setReason(r)}
                  style={{
                    padding: '6px 12px', borderRadius: '20px', fontSize: '0.8rem',
                    border: reason === r ? '1.5px solid var(--sage)' : '1.5px solid var(--border)',
                    background: reason === r ? 'var(--sage-lt)' : 'var(--cream)',
                    color: reason === r ? 'var(--sage)' : 'var(--muted)',
                    cursor: 'pointer', transition: 'all 0.15s'
                  }}>
                  {r}
                </button>
              ))}
            </div>

            <textarea
              className="text-input"
              style={{ width: '100%', minHeight: 80, resize: 'vertical', padding: '10px 14px' }}
              placeholder='Or type your own reason…'
              value={reason}
              onChange={e => setReason(e.target.value)}
            />

            {error && <div className="alert alert-error" style={{ marginTop: 10 }}>{error}</div>}

            <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
              <button className="btn btn-primary" onClick={submit} disabled={loading || !reason.trim()}>
                {loading ? 'Processing…' : 'Remove & remember'}
              </button>
              <button className="btn btn-outline" onClick={onClose}>Cancel</button>
            </div>
          </>
        ) : (
          <div style={{ textAlign: 'center', padding: '16px 0' }}>
            <div style={{ fontSize: '2.5rem', marginBottom: 12 }}>
              {ACTION_ICONS[result.action] || '✓'}
            </div>
            <p style={{ fontWeight: 600, marginBottom: 6 }}>{result.user_message}</p>
            <p style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>Removing from list…</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function GroceryList() {
  const { planId }  = useParams();
  const navigate    = useNavigate();
  const pollRef     = useRef(null);

  const [plan,       setPlan]       = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [errMsg,     setErrMsg]     = useState('');
  const [confirmed,  setConfirmed]  = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [restocks,   setRestocks]   = useState([]);
  const [removing,   setRemoving]   = useState(null); // item being removed
  const [removed,    setRemoved]    = useState([]);   // names removed this session

  useEffect(() => {
    let cancelled = false;
    const fetchPlan = async () => {
      try {
        const { data } = await getPlan(planId);
        if (cancelled) return;
        setPlan(data);
        if (data.status === 'complete' || data.status === 'confirmed') {
          setLoading(false);
          if (data.confirmed) setConfirmed(true);
          clearInterval(pollRef.current);
        } else if (data.status === 'failed') {
          setErrMsg('Pipeline failed. Please try again.');
          setLoading(false);
          clearInterval(pollRef.current);
        }
      } catch (e) {
        if (!cancelled) { setErrMsg('Could not load plan.'); setLoading(false); clearInterval(pollRef.current); }
      }
    };
    fetchPlan();
    pollRef.current = setInterval(fetchPlan, 2000);
    return () => { cancelled = true; clearInterval(pollRef.current); };
  }, [planId]);

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      const { data } = await confirmPlan(planId);
      setConfirmed(true);
      setRestocks(data.restock_alerts || []);
    } catch (e) {
      setErrMsg(e.response?.data?.detail || 'Confirmation failed.');
    }
    setConfirming(false);
  };

  const handleRemoveDone = (name) => {
    setRemoved(r => [...r, name.toLowerCase()]);
    setRemoving(null);
  };

  if (loading) return (
    <div className="page">
      <div className="empty-state"><div className="spinner" /><h2>Building your list…</h2><p>This page will update automatically.</p></div>
    </div>
  );

  if (errMsg && !plan) return (
    <div className="page">
      <div className="alert alert-error">{errMsg}</div>
      <button className="btn btn-outline" style={{ marginTop: 16 }} onClick={() => navigate('/')}>← Back</button>
    </div>
  );

  const { grocery_lists = [], pantry_skipped = [], pantry_restock = [], pantry_deductions = [] } = plan;
  const visibleLists = grocery_lists.filter(s => s.store !== 'pantry_meta');
  const fsaItems     = visibleLists.flatMap(s => (s.extra_items || []).filter(i => i.fsa_eligible));

  return (
    <div className="page">
      {removing && (
        <RemoveModal
          item={removing}
          planId={planId}
          onDone={handleRemoveDone}
          onClose={() => setRemoving(null)}
        />
      )}

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 32, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: '1.8rem', marginBottom: 4 }}>Your Grocery List</h1>
          <p style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>
            {plan.meals?.join(' · ')} &nbsp;·&nbsp; {plan.num_people} people
          </p>
        </div>
        <button className="btn btn-outline" onClick={() => navigate('/')}>← New plan</button>
      </div>

      {errMsg && <div className="alert alert-error" style={{ marginBottom: 16 }}>{errMsg}</div>}

      {restocks.length > 0 && (
        <div className="alert alert-info" style={{ marginBottom: 20 }}>
          <strong>⚠️ Restock soon:</strong>
          {restocks.map(r => <div key={r.name} style={{ marginTop: 4 }}>{r.name} — {r.message}</div>)}
        </div>
      )}

      {/* Confirm banner */}
      {!confirmed ? (
        <div className="card" style={{ marginBottom: 24, borderColor: 'var(--amber)', background: 'var(--amber-lt)' }}>
          <p style={{ fontSize: '0.9rem', marginBottom: 14 }}>
            <strong>Happy with this list?</strong> Confirming will deduct used items from your pantry.
            {pantry_deductions.length > 0 && (
              <span style={{ color: 'var(--muted)', display: 'block', marginTop: 4, fontSize: '0.82rem' }}>
                Will deduct: {pantry_deductions.map(d => `${d.ingredient_name} (${d.deduct_amount}${d.unit})`).join(', ')}
              </span>
            )}
          </p>
          <button className="btn-confirm" onClick={handleConfirm} disabled={confirming}>
            {confirming ? 'Confirming…' : '✓ Looks good — confirm & update pantry'}
          </button>
        </div>
      ) : (
        <div className="alert alert-success" style={{ marginBottom: 24 }}>✓ Confirmed! Pantry has been updated.</div>
      )}

      {/* Per-store lists */}
      {visibleLists.map(store => {
        const foodItems  = (store.food_items  || []).filter(i => !removed.includes(i.name.toLowerCase()));
        const extraItems = (store.extra_items || []).filter(i => !removed.includes(i.name.toLowerCase()));
        if (!foodItems.length && !extraItems.length) return null;

        return (
          <div key={store.store} className="card store-section">
            <div className="store-header">
              <h2 className="store-name card-title" style={{ margin: 0 }}><StoreName id={store.store} /></h2>
              <span className="store-count">{foodItems.length + extraItems.length} items</span>
            </div>

            {foodItems.length > 0 && (
              <>
                <p className="section-label">Food</p>
                {foodItems.map((item, i) => (
                  <div key={i} className="item-row">
                    <span className={`item-name ${item.quantity === 0 ? 'pantry' : ''}`}>{item.name}</span>
                    {item.notes?.includes('your recipe') && (
                      <span title="From your saved recipe" style={{ fontSize: '0.75rem', color: 'var(--amber)' }}>⭐</span>
                    )}
                    {item.quantity === 0
                      ? <span className="badge badge-pantry">in pantry</span>
                      : <span className="item-qty">{item.quantity} {item.unit}</span>
                    }
                    <button
                      onClick={() => setRemoving({ ...item, store: store.store })}
                      title="Remove this item"
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', fontSize: '1rem', padding: '0 4px', marginLeft: 4, opacity: 0.5, transition: 'opacity 0.15s' }}
                      onMouseEnter={e => e.target.style.opacity = 1}
                      onMouseLeave={e => e.target.style.opacity = 0.5}
                    >✕</button>
                  </div>
                ))}
              </>
            )}

            {extraItems.length > 0 && (
              <>
                {foodItems.length > 0 && <div className="divider" style={{ margin: '16px 0' }} />}
                <p className="section-label">Extras</p>
                {extraItems.map((item, i) => (
                  <div key={i} className="item-row">
                    <span className="item-name">{item.name}</span>
                    {item.fsa_eligible && <span className="badge badge-fsa">FSA/HSA</span>}
                    <button
                      onClick={() => setRemoving({ ...item, store: store.store })}
                      title="Remove this item"
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', fontSize: '1rem', padding: '0 4px', marginLeft: 4, opacity: 0.5, transition: 'opacity 0.15s' }}
                      onMouseEnter={e => e.target.style.opacity = 1}
                      onMouseLeave={e => e.target.style.opacity = 0.5}
                    >✕</button>
                  </div>
                ))}
              </>
            )}
          </div>
        );
      })}

      {/* Pantry skipped */}
      {pantry_skipped.length > 0 && (
        <div className="summary-section">
          <h3>🥫 Already in your pantry</h3>
          {pantry_skipped.map(name => (
            <div key={name} className="summary-row"><span>✓</span> <strong>{name}</strong></div>
          ))}
        </div>
      )}

      {/* Pantry restock */}
      {pantry_restock.length > 0 && (
        <div className="summary-section" style={{ marginTop: 12 }}>
          <h3>⚠️ Running low after this week</h3>
          {pantry_restock.map((item, i) => (
            <div key={i} className="summary-row">
              <span className="badge badge-low">low</span>
              <strong>{item.name}</strong>
              <span style={{ marginLeft: 'auto', fontSize: '0.8rem' }}>
                {item.status === 'low_after_use' ? `${item.will_remain}${item.unit} left` : `bought ${item.to_buy}${item.unit} more`}
                {item.preferred_store && ` · restock at ${item.preferred_store.replace('_', ' ')}`}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* FSA summary */}
      {fsaItems.length > 0 && (
        <div className="summary-section" style={{ marginTop: 12 }}>
          <h3>💊 FSA/HSA Eligible</h3>
          {fsaItems.map((item, i) => (
            <div key={i} className="summary-row">
              <span className="badge badge-fsa">FSA/HSA</span>
              <strong>{item.name}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
