import { useState, useEffect } from 'react';
import { getConfig, updateConfig, getPantry, addPantryItem, updatePantryItem, deletePantryItem, bulkAddPantry, getPreferences, upsertPreference } from '../api/client';

const STORE_OPTIONS = [
  { id: 'trader_joes',  label: "Trader Joe's" },
  { id: 'costco',       label: 'Costco'        },
  { id: 'indian_store', label: 'Indian Store'  },
  { id: 'target',       label: 'Target'        },
  { id: 'whole_foods',  label: 'Whole Foods'   },
  { id: 'safeway',      label: 'Safeway'       },
  { id: 'walmart',      label: 'Walmart'       },
  { id: 'kroger',       label: 'Kroger'        },
  { id: 'sprouts',      label: 'Sprouts'       },
  { id: 'hmart',        label: 'H Mart'        },
];


const PANTRY_PRESETS = [
  {
    id:    'spices',
    label: '🌶️ All spices',
    desc:  '12 common spices at high stock',
    items: [
      { ingredient_name: 'turmeric powder',   quantity: 200, unit: 'g', category: 'spice', restock_threshold: 30 },
      { ingredient_name: 'cumin seeds',       quantity: 200, unit: 'g', category: 'spice', restock_threshold: 30 },
      { ingredient_name: 'coriander powder',  quantity: 200, unit: 'g', category: 'spice', restock_threshold: 30 },
      { ingredient_name: 'garam masala',      quantity: 200, unit: 'g', category: 'spice', restock_threshold: 30 },
      { ingredient_name: 'red chili powder',  quantity: 200, unit: 'g', category: 'spice', restock_threshold: 30 },
      { ingredient_name: 'cumin powder',      quantity: 150, unit: 'g', category: 'spice', restock_threshold: 25 },
      { ingredient_name: 'salt',              quantity: 500, unit: 'g', category: 'spice', restock_threshold: 75 },
      { ingredient_name: 'black pepper',      quantity: 100, unit: 'g', category: 'spice', restock_threshold: 15 },
      { ingredient_name: 'cardamom',          quantity: 100, unit: 'g', category: 'spice', restock_threshold: 15 },
      { ingredient_name: 'cinnamon',          quantity: 100, unit: 'g', category: 'spice', restock_threshold: 15 },
      { ingredient_name: 'mustard seeds',     quantity: 150, unit: 'g', category: 'spice', restock_threshold: 25 },
      { ingredient_name: 'kasuri methi',      quantity: 100, unit: 'g', category: 'spice', restock_threshold: 15 },
    ]
  },
  {
    id:    'oils',
    label: '🫙 Oils & basics',
    desc:  'Oils, ghee, butter',
    items: [
      { ingredient_name: 'vegetable oil', quantity: 1000, unit: 'ml', category: 'oil',   restock_threshold: 200 },
      { ingredient_name: 'olive oil',     quantity: 500,  unit: 'ml', category: 'oil',   restock_threshold: 100 },
      { ingredient_name: 'ghee',          quantity: 500,  unit: 'g',  category: 'oil',   restock_threshold: 100 },
      { ingredient_name: 'butter',        quantity: 250,  unit: 'g',  category: 'dairy', restock_threshold: 50  },
    ]
  },
  {
    id:    'grains',
    label: '🌾 Grains & lentils',
    desc:  'Rice, dal, flour',
    items: [
      { ingredient_name: 'basmati rice', quantity: 3000, unit: 'g', category: 'grain',  restock_threshold: 500 },
      { ingredient_name: 'toor dal',     quantity: 1000, unit: 'g', category: 'legume', restock_threshold: 200 },
      { ingredient_name: 'chana dal',    quantity: 500,  unit: 'g', category: 'legume', restock_threshold: 100 },
      { ingredient_name: 'urad dal',     quantity: 500,  unit: 'g', category: 'legume', restock_threshold: 100 },
      { ingredient_name: 'besan',        quantity: 500,  unit: 'g', category: 'grain',  restock_threshold: 100 },
      { ingredient_name: 'atta',         quantity: 2000, unit: 'g', category: 'grain',  restock_threshold: 500 },
    ]
  },
];

const CATEGORIES = ['produce','dairy','meat','grain','spice','oil','legume','canned','supplement','medicine','personal_care','other'];

function Tab({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '8px 20px',
        borderRadius: '20px',
        border: active ? '1.5px solid var(--sage)' : '1.5px solid var(--border)',
        background: active ? 'var(--sage-lt)' : 'transparent',
        color: active ? 'var(--sage)' : 'var(--muted)',
        fontWeight: 500,
        fontSize: '0.88rem',
        cursor: 'pointer',
        transition: 'all 0.15s',
      }}
    >{children}</button>
  );
}

// ── STORES TAB ──
function StoresTab() {
  const [activeStores, setActiveStores] = useState([]);
  const [saving, setSaving] = useState(false);
  const [saved,  setSaved]  = useState(false);

  useEffect(() => {
    getConfig().then(({ data }) => setActiveStores(data.active_stores || []));
  }, []);

  const toggle = (id) =>
    setActiveStores(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);

  const save = async () => {
    setSaving(true);
    await updateConfig({ user_id: 'default_user', active_stores: activeStores });
    setSaving(false); setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div>
      <p style={{ color: 'var(--muted)', fontSize: '0.88rem', marginBottom: 20 }}>
        Choose which stores appear in your grocery list. You can add any store — the AI will route items there using web search.
      </p>
      <div className="store-grid" style={{ marginBottom: 24 }}>
        {STORE_OPTIONS.map(s => (
          <button
            key={s.id}
            className={`store-toggle ${activeStores.includes(s.id) ? 'active' : ''}`}
            onClick={() => toggle(s.id)}
          >{s.label}</button>
        ))}
      </div>

      {/* Custom store input */}
      <CustomStoreInput activeStores={activeStores} setActiveStores={setActiveStores} />

      <div style={{ marginTop: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save stores'}
        </button>
        {saved && <span style={{ color: 'var(--sage)', fontSize: '0.88rem' }}>✓ Saved</span>}
      </div>
    </div>
  );
}

function CustomStoreInput({ activeStores, setActiveStores }) {
  const [val, setVal] = useState('');
  const add = () => {
    const id = val.trim().toLowerCase().replace(/\s+/g, '_');
    if (id && !activeStores.includes(id)) {
      setActiveStores([...activeStores, id]);
      setVal('');
    }
  };
  return (
    <div>
      <p className="section-label" style={{ marginBottom: 8 }}>Add a custom store</p>
      <div className="input-row">
        <input
          className="text-input"
          placeholder='e.g. "Mitsuwa" or "Ranch 99"'
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && add()}
        />
        <button className="add-btn" onClick={add}>Add</button>
      </div>
      {activeStores.filter(s => !STORE_OPTIONS.find(o => o.id === s)).map(s => (
        <span key={s} className="tag" style={{ marginTop: 10, marginRight: 6 }}>
          {s.replace(/_/g, ' ')}
          <button className="tag-remove" onClick={() => setActiveStores(activeStores.filter(x => x !== s))}>×</button>
        </span>
      ))}
    </div>
  );
}


function QuickSetup({ onDone }) {
  const [preview,  setPreview]  = useState(null);   // preset being previewed
  const [items,    setItems]    = useState([]);      // editable items list
  const [loading,  setLoading]  = useState(false);
  const [done,     setDone]     = useState({});      // preset id → success msg

  const openPreview = (preset) => {
    setPreview(preset);
    setItems(preset.items.map(i => ({ ...i })));     // deep copy so edits don't mutate preset
  };

  const updateItem = (idx, field, val) => {
    setItems(items.map((item, i) => i === idx ? { ...item, [field]: val } : item));
  };

  const removeItem = (idx) => setItems(items.filter((_, i) => i !== idx));

  const submitBulk = async () => {
    setLoading(true);
    try {
      const { data } = await bulkAddPantry(items, true);
      setDone(d => ({ ...d, [preview.id]: `✓ Added ${data.added.length}, updated ${data.updated.length}` }));
      setPreview(null);
      onDone();
    } catch (e) {
      alert(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : JSON.stringify(e.response?.data) || 'Failed to add items');
    }
    setLoading(false);
  };

  return (
    <div style={{ marginBottom: 24 }}>
      <p className="section-label" style={{ marginBottom: 12 }}>Quick setup — add preset bundles</p>

      {/* Preset cards */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
        {PANTRY_PRESETS.map(preset => (
          <div key={preset.id} style={{
            flex: 1, minWidth: 160,
            padding: '14px 16px',
            border: `1.5px solid ${done[preset.id] ? 'var(--sage)' : 'var(--border)'}`,
            borderRadius: 'var(--radius)',
            background: done[preset.id] ? 'var(--sage-lt)' : 'var(--cream)',
            transition: 'all 0.15s',
          }}>
            <p style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: 4 }}>{preset.label}</p>
            <p style={{ fontSize: '0.78rem', color: 'var(--muted)', marginBottom: 12 }}>{preset.desc} · {preset.items.length} items</p>
            {done[preset.id] ? (
              <p style={{ fontSize: '0.78rem', color: 'var(--sage)', fontWeight: 500 }}>{done[preset.id]}</p>
            ) : (
              <button className="add-btn" style={{ fontSize: '0.78rem', padding: '5px 12px' }}
                onClick={() => openPreview(preset)}>
                Review & add →
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Editable preview panel */}
      {preview && (
        <div className="card" style={{ borderColor: 'var(--sage)', background: 'var(--sage-lt)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div>
              <p style={{ fontWeight: 600, fontSize: '1rem' }}>{preview.label}</p>
              <p style={{ fontSize: '0.8rem', color: 'var(--muted)', marginTop: 2 }}>
                Review and edit quantities before adding. Click × to remove any item.
              </p>
            </div>
            <button onClick={() => setPreview(null)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', fontSize: '1.3rem' }}>×</button>
          </div>

          {/* Column headers */}
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr auto', gap: 8, marginBottom: 8 }}>
            {['Ingredient', 'Quantity', 'Unit', ''].map(h => (
              <p key={h} style={{ fontSize: '0.72rem', color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</p>
            ))}
          </div>

          {/* Editable rows */}
          <div style={{ maxHeight: 340, overflowY: 'auto', marginBottom: 16 }}>
            {items.map((item, idx) => (
              <div key={idx} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr auto', gap: 8, marginBottom: 8, alignItems: 'center' }}>
                <span style={{ fontSize: '0.88rem', fontWeight: 500, padding: '8px 0' }}>{item.ingredient_name}</span>
                <input
                  className="text-input"
                  style={{ background: 'white' }}
                  type="number"
                  value={item.quantity}
                  onChange={e => updateItem(idx, 'quantity', parseFloat(e.target.value) || 0)}
                />
                <select
                  className="text-input"
                  style={{ background: 'white' }}
                  value={item.unit || 'g'}
                  onChange={e => updateItem(idx, 'unit', e.target.value)}
                >
                  {['g','kg','ml','l','tsp','tbsp','pieces'].map(u => <option key={u} value={u}>{u}</option>)}
                </select>
                <button onClick={() => removeItem(idx)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--red)', fontSize: '1.1rem', padding: '0 4px' }}>×</button>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <button className="btn btn-primary" onClick={submitBulk} disabled={loading || !items.length}>
              {loading ? 'Adding…' : `Add ${items.length} items to pantry`}
            </button>
            <button className="btn btn-outline" onClick={() => setPreview(null)}>Cancel</button>
          </div>
        </div>
      )}

      <div style={{ height: 1, background: 'var(--border)', margin: '20px 0' }} />
    </div>
  );
}


// ── Per-category quick action buttons ──
function CategoryBulkAction({ category, onAction }) {
  const [open,   setOpen]   = useState(false);
  const [value,  setValue]  = useState('');
  const [unit,   setUnit]   = useState('g');
  const [action, setAction] = useState('');

  const apply = async () => {
    if (!action) return;
    if (action === 'remove') {
      await onAction(category, 'remove');
    } else {
      if (!value) return;
      await onAction(category, action, value, unit);
    }
    setOpen(false); setValue(''); setAction(''); setUnit('g');
  };

  return (
    <div style={{ position: 'relative' }}>
      <button onClick={() => setOpen(!open)}
        style={{ fontSize: '0.75rem', padding: '3px 10px', borderRadius: 6,
          border: '1px solid var(--border)', background: 'white', cursor: 'pointer', color: 'var(--muted)' }}>
        Category actions ▾
      </button>
      {open && (
        <div style={{ position: 'absolute', right: 0, top: '100%', marginTop: 4, zIndex: 100,
          background: 'white', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
          padding: 14, width: 240, boxShadow: '0 4px 16px rgba(0,0,0,0.1)' }}>
          <p style={{ fontSize: '0.78rem', color: 'var(--muted)', marginBottom: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            All {category} items
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              { id: 'threshold', label: 'Set threshold' },
              { id: 'restock',   label: 'Set quantity' },
              { id: 'remove',    label: 'Remove all', danger: true },
            ].map(a => (
              <button key={a.id} onClick={() => setAction(a.id)}
                style={{ padding: '6px 10px', borderRadius: 6, textAlign: 'left', fontSize: '0.82rem',
                  background: action === a.id ? (a.danger ? '#FDECEA' : 'var(--sage-lt)') : 'var(--cream)',
                  color: a.danger ? 'var(--red)' : 'var(--ink)',
                  border: `1px solid ${action === a.id ? (a.danger ? 'var(--red)' : 'var(--sage)') : 'var(--border)'}`,
                  cursor: 'pointer' }}>
                {a.label}
              </button>
            ))}
            {(action === 'threshold' || action === 'restock') && (
              <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                <input type="number" placeholder={action === 'threshold' ? 'Threshold' : 'Quantity'}
                  value={value} onChange={e => setValue(e.target.value)}
                  className="text-input" style={{ flex: 1 }} />
                <select value={unit} onChange={e => setUnit(e.target.value)}
                  className="text-input" style={{ width: 70 }}>
                  {['g','kg','ml','l','tsp','tbsp','pieces'].map(u => <option key={u} value={u}>{u}</option>)}
                </select>
              </div>
            )}
            {action && (
              <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                <button onClick={apply}
                  style={{ flex: 1, padding: '6px', borderRadius: 6, fontSize: '0.82rem', fontWeight: 600,
                    background: action === 'remove' ? 'var(--red)' : 'var(--sage)',
                    color: 'white', border: 'none', cursor: 'pointer' }}>
                  Apply
                </button>
                <button onClick={() => { setOpen(false); setAction(''); setValue(''); }}
                  style={{ padding: '6px 10px', borderRadius: 6, fontSize: '0.82rem',
                    background: 'var(--cream)', border: '1px solid var(--border)', cursor: 'pointer' }}>
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── PANTRY TAB ──
function PantryTab() {
  const [items,    setItems]    = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editId,   setEditId]   = useState(null);
  const [form,     setForm]     = useState({ ingredient_name: '', quantity: '', unit: 'g', category: 'spice', restock_threshold: 0, restock_threshold_unit: 'g', preferred_store: '' });
  const [saving,   setSaving]   = useState(false);
  const [filter,   setFilter]   = useState('all');

  // ── Bulk selection state ──
  const [selected,       setSelected]       = useState(new Set());
  const [bulkAction,     setBulkAction]     = useState('');
  const [bulkValue,      setBulkValue]      = useState('');
  const [bulkUnit,       setBulkUnit]       = useState('g');
  const [bulkApplying,   setBulkApplying]   = useState(false);

  const load = () => {
    setLoading(true);
    getPantry().then(({ data }) => { setItems(data); setLoading(false); setSelected(new Set()); });
  };

  useEffect(() => { load(); }, []);

  const resetForm = () => {
    setForm({ ingredient_name: '', quantity: '', unit: 'g', category: 'spice', restock_threshold: 0, preferred_store: '' });
    setEditId(null); setShowForm(false);
  };

  const startEdit = (item) => {
    setForm({ ingredient_name: item.ingredient_name, quantity: item.quantity, unit: item.unit,
              category: item.category, restock_threshold: item.restock_threshold, preferred_store: item.preferred_store || '' });
    setEditId(item.id); setShowForm(true);
  };

  const submit = async () => {
    if (!form.ingredient_name || !form.quantity) return;
    setSaving(true);
    try {
      if (editId) {
        await updatePantryItem(editId, { quantity: parseFloat(form.quantity), restock_threshold: parseFloat(form.restock_threshold) || 0, preferred_store: form.preferred_store || null });
      } else {
        await addPantryItem({ ...form, quantity: parseFloat(form.quantity), restock_threshold: parseFloat(form.restock_threshold) || 0 });
      }
      resetForm(); load();
    } catch (e) { alert(e.response?.data?.detail || 'Error saving item'); }
    setSaving(false);
  };

  const del = async (id, name) => {
    if (!window.confirm(`Remove "${name}" from pantry?`)) return;
    await deletePantryItem(id); load();
  };

  // ── Selection helpers ──
  const toggleItem = (id) => {
    const s = new Set(selected);
    s.has(id) ? s.delete(id) : s.add(id);
    setSelected(s);
  };

  const toggleCategory = (categoryItems, checked) => {
    const s = new Set(selected);
    categoryItems.forEach(i => checked ? s.add(i.id) : s.delete(i.id));
    setSelected(s);
  };

  const selectAll  = () => setSelected(new Set(filtered.map(i => i.id)));
  const clearAll   = () => setSelected(new Set());

  // ── Bulk apply ──
  const applyBulk = async () => {
    if (!selected.size || !bulkAction) return;
    setBulkApplying(true);
    try {
      if (bulkAction === 'remove') {
        if (!window.confirm(`Remove ${selected.size} items from pantry?`)) { setBulkApplying(false); return; }
        await Promise.all([...selected].map(id => deletePantryItem(id)));
      } else if (bulkAction === 'threshold') {
        if (!bulkValue) return;
        await Promise.all([...selected].map(id => updatePantryItem(id, { restock_threshold: parseFloat(bulkValue), restock_threshold_unit: bulkUnit })));
      } else if (bulkAction === 'quantity') {
        if (!bulkValue) return;
        await Promise.all([...selected].map(id => updatePantryItem(id, { quantity: parseFloat(bulkValue), unit: bulkUnit })));
      }
      setBulkAction(''); setBulkValue(''); load();
    } catch (e) { alert('Bulk action failed'); }
    setBulkApplying(false);
  };

  // ── Category bulk shortcuts ──
  const categoryAction = async (category, action, value, unit = 'g') => {
    const categoryItems = items.filter(i => i.category === category);
    if (!categoryItems.length) return;
    if (action === 'remove') {
      if (!window.confirm(`Remove all ${categoryItems.length} ${category} items?`)) return;
      await Promise.all(categoryItems.map(i => deletePantryItem(i.id)));
    } else if (action === 'threshold') {
      await Promise.all(categoryItems.map(i => updatePantryItem(i.id, { restock_threshold: parseFloat(value), restock_threshold_unit: unit })));
    } else if (action === 'restock') {
      await Promise.all(categoryItems.map(i => updatePantryItem(i.id, { quantity: parseFloat(value), unit })));
    }
    load();
  };

  const categories = ['all', ...new Set(items.map(i => i.category))];
  const filtered   = filter === 'all' ? items : items.filter(i => i.category === filter);

  // Group filtered items by category for category-level headers
  const grouped = filtered.reduce((acc, item) => {
    const cat = item.category;
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(item);
    return acc;
  }, {});

  return (
    <div>
      <QuickSetup onDone={load} />

      {/* ── Filters + Add button ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {categories.map(c => (
            <button key={c} onClick={() => setFilter(c)} style={{
              padding: '4px 12px', borderRadius: '20px', fontSize: '0.8rem',
              border: filter === c ? '1.5px solid var(--sage)' : '1.5px solid var(--border)',
              background: filter === c ? 'var(--sage-lt)' : 'transparent',
              color: filter === c ? 'var(--sage)' : 'var(--muted)', cursor: 'pointer',
            }}>{c}</button>
          ))}
        </div>
        <button className="btn btn-primary" onClick={() => { resetForm(); setShowForm(true); }} style={{ padding: '8px 16px', fontSize: '0.85rem' }}>
          + Add item
        </button>
      </div>

      {/* ── Add/Edit form ── */}
      {showForm && (
        <div className="card" style={{ marginBottom: 20, borderColor: 'var(--sage)', background: 'var(--sage-lt)' }}>
          <p className="section-label" style={{ marginBottom: 14 }}>{editId ? 'Edit item' : 'New pantry item'}</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {[
              { label: 'Name', key: 'ingredient_name', type: 'text', placeholder: 'e.g. garam masala', disabled: !!editId },
              { label: 'Category', key: 'category', type: 'select', options: CATEGORIES },
              { label: 'Quantity', key: 'quantity', type: 'number', placeholder: '500' },
              { label: 'Unit', key: 'unit', type: 'select', options: ['g','kg','ml','l','pieces','tsp','tbsp','cups'] },
              { label: 'Restock threshold (0 = no alert)', key: 'restock_threshold', type: 'number', placeholder: '0' },
              { label: 'Threshold unit', key: 'restock_threshold_unit', type: 'select', options: ['g','kg','ml','l','tsp','tbsp','pieces'] },
              { label: 'Preferred store', key: 'preferred_store', type: 'text', placeholder: 'e.g. indian_store' },
            ].map(f => (
              <div key={f.key}>
                <p style={{ fontSize: '0.78rem', color: 'var(--muted)', marginBottom: 4 }}>{f.label}</p>
                {f.type === 'select' ? (
                  <select className="text-input" style={{ width: '100%', background: 'white' }}
                    value={form[f.key]} onChange={e => setForm({ ...form, [f.key]: e.target.value })} disabled={f.disabled}>
                    {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input className="text-input" style={{ width: '100%', background: 'white' }}
                    type={f.type} placeholder={f.placeholder}
                    value={form[f.key]} onChange={e => setForm({ ...form, [f.key]: e.target.value })}
                    disabled={f.disabled} />
                )}
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
            <button className="btn btn-primary" onClick={submit} disabled={saving}>{saving ? 'Saving…' : editId ? 'Update' : 'Add to pantry'}</button>
            <button className="btn btn-outline" onClick={resetForm}>Cancel</button>
          </div>
        </div>
      )}

      {/* ── Bulk action bar (shows when items selected) ── */}
      {selected.size > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
          background: 'var(--ink)', borderRadius: 'var(--radius)', marginBottom: 16, flexWrap: 'wrap' }}>
          <span style={{ color: 'white', fontSize: '0.88rem', fontWeight: 500 }}>
            {selected.size} selected
          </span>
          <select value={bulkAction} onChange={e => { setBulkAction(e.target.value); setBulkValue(''); }}
            style={{ padding: '6px 10px', borderRadius: 6, border: 'none', fontSize: '0.85rem', background: 'white' }}>
            <option value="">Choose action…</option>
            <option value="threshold">Set restock threshold</option>
            <option value="quantity">Set quantity</option>
            <option value="remove">Remove items</option>
          </select>
          {(bulkAction === 'threshold' || bulkAction === 'quantity') && (
            <>
              <input type="number" placeholder="Value" value={bulkValue}
                onChange={e => setBulkValue(e.target.value)}
                style={{ width: 80, padding: '6px 10px', borderRadius: 6, border: 'none', fontSize: '0.85rem' }} />
              <select value={bulkUnit} onChange={e => setBulkUnit(e.target.value)}
                style={{ padding: '6px 8px', borderRadius: 6, border: 'none', fontSize: '0.85rem', background: 'white' }}>
                {['g','kg','ml','l','tsp','tbsp','pieces'].map(u => <option key={u} value={u}>{u}</option>)}
              </select>
            </>
          )}
          <button onClick={applyBulk} disabled={bulkApplying || !bulkAction || (bulkAction !== 'remove' && !bulkValue)}
            style={{ padding: '6px 16px', borderRadius: 6, background: bulkAction === 'remove' ? 'var(--red)' : 'var(--sage)',
              color: 'white', border: 'none', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 500 }}>
            {bulkApplying ? 'Applying…' : 'Apply'}
          </button>
          <button onClick={clearAll}
            style={{ padding: '6px 12px', borderRadius: 6, background: 'transparent', color: '#aaa',
              border: '1px solid #555', cursor: 'pointer', fontSize: '0.82rem' }}>
            Clear
          </button>
        </div>
      )}

      {/* ── Select all / clear ── */}
      {filtered.length > 0 && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
          <button onClick={selectAll} style={{ fontSize: '0.78rem', color: 'var(--sage)', background: 'none', border: 'none', cursor: 'pointer' }}>
            Select all ({filtered.length})
          </button>
          {selected.size > 0 && (
            <button onClick={clearAll} style={{ fontSize: '0.78rem', color: 'var(--muted)', background: 'none', border: 'none', cursor: 'pointer' }}>
              Clear selection
            </button>
          )}
        </div>
      )}

      {/* ── Pantry table grouped by category ── */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 32, color: 'var(--muted)' }}>Loading…</div>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 32, color: 'var(--muted)' }}>No items yet.</div>
      ) : (
        <div style={{ borderRadius: 'var(--radius)', overflow: 'hidden', border: '1px solid var(--border)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem' }}>
            <thead>
              <tr style={{ background: 'var(--cream)', borderBottom: '1px solid var(--border)' }}>
                <th style={{ width: 36, padding: '10px 12px' }}></th>
                {['Item','Quantity','Threshold','Store',''].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600,
                    fontSize: '0.72rem', color: 'var(--muted)', letterSpacing: '0.05em', textTransform: 'uppercase' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(grouped).map(([cat, catItems]) => {
                const allCatSelected = catItems.every(i => selected.has(i.id));
                return [
                  // ── Category header row ──
                  <tr key={`cat-${cat}`} style={{ background: '#F7F4EF', borderBottom: '1px solid var(--border)', borderTop: '1px solid var(--border)' }}>
                    <td style={{ padding: '6px 12px' }}>
                      <input type="checkbox" checked={allCatSelected}
                        onChange={e => toggleCategory(catItems, e.target.checked)}
                        style={{ cursor: 'pointer' }} />
                    </td>
                    <td colSpan={2} style={{ padding: '6px 14px', fontWeight: 600, fontSize: '0.78rem',
                      color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      {cat} ({catItems.length})
                    </td>
                    <td colSpan={3} style={{ padding: '6px 14px', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                        <CategoryBulkAction category={cat} onAction={categoryAction} />
                      </div>
                    </td>
                  </tr>,
                  // ── Items in category ──
                  ...catItems.map((item, i) => (
                    <tr key={item.id} style={{ borderBottom: '1px solid #F0EDE8', background: selected.has(item.id) ? '#EBF0E9' : i % 2 === 0 ? 'white' : 'var(--cream)' }}>
                      <td style={{ padding: '10px 12px' }}>
                        <input type="checkbox" checked={selected.has(item.id)}
                          onChange={() => toggleItem(item.id)} style={{ cursor: 'pointer' }} />
                      </td>
                      <td style={{ padding: '10px 14px', fontWeight: 500 }}>
                        {item.ingredient_name}
                        {item.needs_restock && <span className="badge badge-low" style={{ marginLeft: 8 }}>low</span>}
                      </td>
                      <td style={{ padding: '10px 14px' }}>{item.quantity} {item.unit}</td>
                      <td style={{ padding: '10px 14px', color: item.threshold_display ? 'var(--ink)' : 'var(--muted)' }}>
                        {item.threshold_display || '—'}
                      </td>
                      <td style={{ padding: '10px 14px', color: 'var(--muted)' }}>{item.preferred_store?.replace(/_/g,' ') || '—'}</td>
                      <td style={{ padding: '10px 14px' }}>
                        <div style={{ display: 'flex', gap: 8 }}>
                          <button onClick={() => startEdit(item)} style={{ fontSize: '0.78rem', color: 'var(--sage)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>Edit</button>
                          <button onClick={() => del(item.id, item.ingredient_name)} style={{ fontSize: '0.78rem', color: 'var(--red)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>Remove</button>
                        </div>
                      </td>
                    </tr>
                  ))
                ];
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── PREFERENCES TAB ──
function PreferencesTab() {
  const [prefs,   setPrefs]   = useState([]);
  const [pattern, setPattern] = useState('');
  const [store,   setStore]   = useState('');
  const [saving,  setSaving]  = useState(false);
  const [saved,   setSaved]   = useState(false);

  useEffect(() => {
    getPreferences().then(({ data }) => setPrefs(data));
  }, []);

  const save = async () => {
    if (!pattern || !store) return;
    setSaving(true);
    await upsertPreference(pattern, store);
    const { data } = await getPreferences();
    setPrefs(data); setPattern(''); setStore('');
    setSaving(false); setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div>
      <p style={{ color: 'var(--muted)', fontSize: '0.88rem', marginBottom: 20 }}>
        Override which store an ingredient routes to. Useful for specialty items.
      </p>
      <div className="card" style={{ marginBottom: 20 }}>
        <p className="section-label" style={{ marginBottom: 12 }}>Add routing rule</p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <input className="text-input" style={{ flex: 1, minWidth: 160 }}
            placeholder='Ingredient (e.g. "paneer")'
            value={pattern} onChange={e => setPattern(e.target.value)} />
          <input className="text-input" style={{ flex: 1, minWidth: 160 }}
            placeholder='Store (e.g. "indian_store")'
            value={store} onChange={e => setStore(e.target.value)} />
          <button className="btn btn-primary" onClick={save} disabled={saving}>{saving ? '…' : 'Save'}</button>
          {saved && <span style={{ color: 'var(--sage)', fontSize: '0.88rem', alignSelf: 'center' }}>✓ Saved</span>}
        </div>
      </div>

      {prefs.length === 0 ? (
        <div style={{ color: 'var(--muted)', fontSize: '0.88rem' }}>No custom rules yet.</div>
      ) : (
        <div style={{ borderRadius: 'var(--radius)', border: '1px solid var(--border)', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem' }}>
            <thead>
              <tr style={{ background: 'var(--cream)', borderBottom: '1px solid var(--border)' }}>
                <th style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, fontSize: '0.75rem', color: 'var(--muted)', textTransform: 'uppercase' }}>Ingredient</th>
                <th style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, fontSize: '0.75rem', color: 'var(--muted)', textTransform: 'uppercase' }}>→ Store</th>
              </tr>
            </thead>
            <tbody>
              {prefs.map((p, i) => (
                <tr key={p.id} style={{ borderBottom: '1px solid #F0EDE8', background: i % 2 === 0 ? 'white' : 'var(--cream)' }}>
                  <td style={{ padding: '10px 14px', fontWeight: 500 }}>{p.ingredient_pattern}</td>
                  <td style={{ padding: '10px 14px', color: 'var(--muted)' }}>{p.preferred_store.replace(/_/g,' ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── MAIN SETTINGS PAGE ──
export default function Settings() {
  const [tab, setTab] = useState('stores');

  return (
    <div className="page">
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: '1.8rem', marginBottom: 6 }}>Settings</h1>
        <p style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>Manage stores, pantry, and routing preferences.</p>
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 28, flexWrap: 'wrap' }}>
        <Tab active={tab === 'stores'}      onClick={() => setTab('stores')}>🏪 Stores</Tab>
        <Tab active={tab === 'pantry'}      onClick={() => setTab('pantry')}>🥫 Pantry</Tab>
        <Tab active={tab === 'preferences'} onClick={() => setTab('preferences')}>🔀 Routing Rules</Tab>
      </div>

      <div className="card">
        {tab === 'stores'      && <StoresTab />}
        {tab === 'pantry'      && <PantryTab />}
        {tab === 'preferences' && <PreferencesTab />}
      </div>
    </div>
  );
}
