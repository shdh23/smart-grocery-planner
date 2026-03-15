import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createPlan, parseIntent } from '../api/client';
import api from '../api/client';

const ALL_STORES = [
  { id: 'trader_joes', label: "Trader Joe's" },
  { id: 'costco',      label: 'Costco'       },
  { id: 'indian_store',label: 'Indian Store' },
  { id: 'target',      label: 'Target'       },
];

export default function MealPlanner() {
  const navigate = useNavigate();

  const [meals,        setMeals]        = useState([]);
  const [mealInput,    setMealInput]    = useState('');
  const [extras,       setExtras]       = useState([]);
  const [extraInput,   setExtraInput]   = useState('');
  const [numPeople,    setNumPeople]    = useState(2);
  const [stores,       setStores]       = useState(['trader_joes','costco','indian_store','target']);
  const [loading,      setLoading]      = useState(false);
  const [storeHints,   setStoreHints]   = useState({});
  const [error,        setError]        = useState('');
  const [intentText,   setIntentText]   = useState('');
  const [intentLoading,setIntentLoading]= useState(false);
  const [intentResult, setIntentResult] = useState('');
  const [itemStoreOverrides, setItemStoreOverrides] = useState({});

  const parseMealInput = async (raw) => {
    const storeKeywords = /(from|at|always get from|buy at|get from|order from)/i;
    if (!storeKeywords.test(raw)) {
      const name = raw.trim();
      if (name && !meals.includes(name)) {
        setMeals(m => [...m, name]);
        setMealInput('');
      }
      return;
    }

    try {
      const { data } = await api.post('/api/parse-meal-input', { raw_input: raw });
      const mealName  = data.meal_name;
      const storeName = data.store_name;
      const storeItem = data.store_item;

      if (mealName && !meals.includes(mealName)) {
        setMeals(m => [...m, mealName]);
      }
      if (storeName && !stores.includes(storeName)) {
        setStores(s => [...s, storeName]);
        setStoreHints(h => ({ ...h, [mealName]: { store: storeName, item: storeItem } }));
      }
      setMealInput('');
    } catch {
      const name = raw.split(/[-–]/)[0].trim();
      if (name && !meals.includes(name)) setMeals(m => [...m, name]);
      setMealInput('');
    }
  };

  const addMeal = () => {
    const v = mealInput.trim();
    if (v) parseMealInput(v);
  };
  const addExtra = () => {
    const v = extraInput.trim();
    if (v && !extras.includes(v)) { setExtras([...extras, v]); setExtraInput(''); }
  };
  const onKey = (fn) => (e) => { if (e.key === 'Enter') { e.preventDefault(); fn(); } };

  const toggleStore = (id) =>
    setStores(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);


  const applyIntent = async () => {
    if (!intentText.trim()) return;
    setIntentLoading(true); setIntentResult('');
    try {
      const { data } = await parseIntent(intentText, {
        meals, extra_items: extras, active_stores: stores, num_people: numPeople
      });

      const changes = [];

      if (data.add_meals?.length) {
        setMeals(m => [...new Set([...m, ...data.add_meals])]);
        changes.push(`Added meals: ${data.add_meals.join(', ')}`);
      }
      if (data.remove_meals?.length) {
        setMeals(m => m.filter(x => !data.remove_meals.includes(x)));
        changes.push(`Removed: ${data.remove_meals.join(', ')}`);
      }
      if (data.add_extras?.length) {
        setExtras(e => [...new Set([...e, ...data.add_extras])]);
        changes.push(`Added extras: ${data.add_extras.join(', ')}`);
      }
      if (data.remove_extras?.length) {
        setExtras(e => e.filter(x => !data.remove_extras.includes(x)));
        changes.push(`Removed extras: ${data.remove_extras.join(', ')}`);
      }
      if (data.add_stores?.length) {
        setStores(s => [...new Set([...s, ...data.add_stores])]);
        changes.push(`Added stores: ${data.add_stores.join(', ')}`);
      }
      if (data.remove_stores?.length) {
        setStores(s => s.filter(x => !data.remove_stores.includes(x)));
        changes.push(`Removed stores: ${data.remove_stores.join(', ')}`);
      }
      if (data.set_num_people) {
        setNumPeople(data.set_num_people);
        changes.push(`Set people to ${data.set_num_people}`);
      }
      if (data.item_store_overrides && Object.keys(data.item_store_overrides).length) {
        setItemStoreOverrides(prev => ({ ...prev, ...data.item_store_overrides }));
        changes.push(`Item→store: ${Object.entries(data.item_store_overrides).map(([k, v]) => `${k} → ${v}`).join(', ')}`);
      }

      setIntentResult(data.summary || changes.join(' · ') || 'No changes detected');
      setIntentText('');
    } catch (e) {
      setIntentResult('Could not parse — try rephrasing');
    }
    setIntentLoading(false);
  };

  // ── Submit ──
  const submit = async () => {
    if (!meals.length)   return setError('Add at least one meal.');
    if (!stores.length)  return setError('Select at least one store.');
    setError(''); setLoading(true);
    try {
      const { data } = await createPlan({
        meals,
        extra_items:   extras,
        num_people:    numPeople,
        active_stores: stores,
        user_id:       'default_user',
        store_hints:   storeHints,
        item_store_overrides: Object.keys(itemStoreOverrides).length ? itemStoreOverrides : undefined,
      });
      navigate(`/progress/${data.plan_id}`);
    } catch (e) {
      setError(e.response?.data?.detail || 'Something went wrong. Is the backend running?');
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: '2rem', marginBottom: 6 }}>Plan This Week</h1>
        <p style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>
          Add your meals and any extra items — we'll handle the rest.
        </p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {/* ── Meals ── */}
      <div className="card">
        <p className="section-label">Meals this week</p>
        <div className="input-row">
          <input
            className="text-input"
            placeholder='e.g. "Idli - I get batter from Idli Express"'
            value={mealInput}
            onChange={e => setMealInput(e.target.value)}
            onKeyDown={onKey(addMeal)}
          />
          <button className="add-btn" onClick={addMeal}>Add</button>
        </div>
        {meals.length > 0 && (
          <div className="tag-list">
            {meals.map(m => (
              <span key={m} className="tag">
                {m}
                {storeHints[m] && (
                  <span style={{ fontSize: '0.72rem', opacity: 0.7, marginLeft: 4 }}>
                    → {storeHints[m].store.replace(/_/g,' ')}
                  </span>
                )}
                <button className="tag-remove" onClick={() => setMeals(meals.filter(x => x !== m))}>×</button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Extra items ── */}
      <div className="card">
        <p className="section-label">Extra items <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>— medicine, supplements, household (optional)</span></p>
        <div className="input-row">
          <input
            className="text-input"
            placeholder='e.g. "ibuprofen 200mg" or "SPF 50 sunscreen"'
            value={extraInput}
            onChange={e => setExtraInput(e.target.value)}
            onKeyDown={onKey(addExtra)}
          />
          <button className="add-btn" onClick={addExtra}>Add</button>
        </div>
        {extras.length > 0 && (
          <div className="tag-list">
            {extras.map(x => (
              <span key={x} className="tag amber">
                {x}
                <button className="tag-remove" onClick={() => setExtras(extras.filter(e => e !== x))}>×</button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── People + Stores ── */}
      <div className="card">
        <div style={{ display: 'flex', gap: 40, flexWrap: 'wrap' }}>
          <div>
            <p className="section-label">People</p>
            <div className="num-control">
              <button onClick={() => setNumPeople(p => Math.max(1, p - 1))}>−</button>
              <span>{numPeople}</span>
              <button onClick={() => setNumPeople(p => Math.min(20, p + 1))}>+</button>
            </div>
          </div>
          <div style={{ flex: 1 }}>
            <p className="section-label">Active stores</p>
            <div className="store-grid">
              {ALL_STORES.map(s => (
                <button
                  key={s.id}
                  className={`store-toggle ${stores.includes(s.id) ? 'active' : ''}`}
                  onClick={() => toggleStore(s.id)}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>


      {/* ── Natural language input ── */}
      <div className="card">
        <p className="section-label" style={{ marginBottom: 10 }}>💬 Anything to add or change?</p>
        <div className="input-row">
          <input
            className="text-input"
            placeholder='e.g. "add idly express store and idly batter" or "remove target, 4 people"'
            value={intentText}
            onChange={e => setIntentText(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && applyIntent()}
          />
          <button className="add-btn" onClick={applyIntent} disabled={intentLoading || !intentText.trim()}>
            {intentLoading ? '…' : 'Apply'}
          </button>
        </div>
        {intentResult && (
          <p style={{ marginTop: 10, fontSize: '0.82rem', color: 'var(--sage)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>✓</span> {intentResult}
          </p>
        )}
      </div>

      {/* ── Submit ── */}
      <div style={{ marginTop: 24, display: 'flex', justifyContent: 'flex-end' }}>
        <button
          className="btn btn-primary"
          onClick={submit}
          disabled={loading || !meals.length}
          style={{ padding: '12px 32px', fontSize: '0.95rem' }}
        >
          {loading ? 'Starting…' : '✦ Build my grocery list'}
        </button>
      </div>
    </div>
  );
}
