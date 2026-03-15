import { useState, useEffect } from 'react';
import { getRecipes, createRecipe, updateRecipe, deleteRecipe } from '../api/client';

const CATEGORIES = ['produce','dairy','meat','seafood','grain','spice','oil','sauce','legume','frozen','bakery','other'];
const UNITS      = ['g','kg','ml','l','tsp','tbsp','pieces','cups'];

function IngredientRow({ ing, onChange, onRemove }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr auto', gap: 8, marginBottom: 8, alignItems: 'center' }}>
      <input className="text-input" placeholder="Ingredient name" value={ing.name}
        onChange={e => onChange({ ...ing, name: e.target.value })} />
      <input className="text-input" type="number" placeholder="Qty" value={ing.quantity}
        onChange={e => onChange({ ...ing, quantity: parseFloat(e.target.value) || 0 })} />
      <select className="text-input" value={ing.unit}
        onChange={e => onChange({ ...ing, unit: e.target.value })}>
        {UNITS.map(u => <option key={u} value={u}>{u}</option>)}
      </select>
      <select className="text-input" value={ing.category}
        onChange={e => onChange({ ...ing, category: e.target.value })}>
        {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
      <button onClick={onRemove} style={{ background: 'none', border: 'none', color: 'var(--red)', cursor: 'pointer', fontSize: '1.1rem', padding: '0 4px' }}>×</button>
    </div>
  );
}

function RecipeForm({ initial, onSave, onCancel }) {
  const [name,     setName]     = useState(initial?.name     || '');
  const [servings, setServings] = useState(initial?.servings || 2);
  const [ings,     setIngs]     = useState(
    initial?.ingredients?.length
      ? initial.ingredients
      : [{ name: '', quantity: 0, unit: 'g', category: 'produce' }]
  );
  const [saving, setSaving] = useState(false);
  const [error,  setError]  = useState('');

  const addIng = () => setIngs([...ings, { name: '', quantity: 0, unit: 'g', category: 'produce' }]);
  const updateIng = (i, val) => setIngs(ings.map((x, idx) => idx === i ? val : x));
  const removeIng = (i) => setIngs(ings.filter((_, idx) => idx !== i));

  const submit = async () => {
    if (!name.trim())              return setError('Recipe name is required');
    if (!ings.some(i => i.name))   return setError('Add at least one ingredient');
    setSaving(true); setError('');
    try {
      const validIngs = ings.filter(i => i.name.trim());
      await onSave({ name: name.trim(), servings, ingredients: validIngs });
    } catch (e) {
      setError(e.response?.data?.detail || 'Error saving recipe');
    }
    setSaving(false);
  };

  return (
    <div className="card" style={{ marginBottom: 20, borderColor: 'var(--sage)' }}>
      <p className="section-label" style={{ marginBottom: 16 }}>
        {initial ? `Editing: ${initial.name}` : 'New recipe'}
      </p>

      {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error}</div>}

      <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{ flex: 2 }}>
          <p style={{ fontSize: '0.78rem', color: 'var(--muted)', marginBottom: 6 }}>Recipe name</p>
          <input className="text-input" style={{ width: '100%' }}
            placeholder='e.g. "Paneer Butter Masala"'
            value={name} onChange={e => setName(e.target.value)}
            disabled={!!initial}
          />
        </div>
        <div>
          <p style={{ fontSize: '0.78rem', color: 'var(--muted)', marginBottom: 6 }}>Base servings</p>
          <div className="num-control">
            <button onClick={() => setServings(s => Math.max(1, s - 1))}>−</button>
            <span>{servings}</span>
            <button onClick={() => setServings(s => s + 1)}>+</button>
          </div>
        </div>
      </div>

      {/* Column headers */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr auto', gap: 8, marginBottom: 6 }}>
        {['Ingredient', 'Quantity', 'Unit', 'Category', ''].map(h => (
          <p key={h} style={{ fontSize: '0.72rem', color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</p>
        ))}
      </div>

      {ings.map((ing, i) => (
        <IngredientRow key={i} ing={ing}
          onChange={val => updateIng(i, val)}
          onRemove={() => removeIng(i)}
        />
      ))}

      <button className="add-btn" style={{ marginTop: 8, marginBottom: 20 }} onClick={addIng}>
        + Add ingredient
      </button>

      <div style={{ display: 'flex', gap: 10 }}>
        <button className="btn btn-primary" onClick={submit} disabled={saving}>
          {saving ? 'Saving…' : initial ? 'Update recipe' : 'Save recipe'}
        </button>
        <button className="btn btn-outline" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

export default function Recipes() {
  const [recipes,  setRecipes]  = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing,  setEditing]  = useState(null);
  const [expanded, setExpanded] = useState(null);

  const load = () => {
    setLoading(true);
    getRecipes().then(({ data }) => { setRecipes(data); setLoading(false); });
  };

  useEffect(() => { load(); }, []);

  const handleSave = async (data) => {
    if (editing) {
      await updateRecipe(editing.id, data);
      setEditing(null);
    } else {
      await createRecipe(data);
      setShowForm(false);
    }
    load();
  };

  const handleDelete = async (id, name) => {
    if (!confirm(`Delete recipe "${name}"?`)) return;
    await deleteRecipe(id);
    load();
  };

  return (
    <div className="page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <h1 style={{ fontSize: '1.8rem', marginBottom: 4 }}>My Recipes</h1>
          <p style={{ color: 'var(--muted)', fontSize: '0.88rem' }}>
            Saved recipes are used instead of AI guesses when you plan meals.
          </p>
        </div>
        {!showForm && !editing && (
          <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ Save a recipe</button>
        )}
      </div>

      {(showForm && !editing) && (
        <RecipeForm onSave={handleSave} onCancel={() => setShowForm(false)} />
      )}

      {loading ? (
        <div className="empty-state"><div className="spinner" /></div>
      ) : recipes.length === 0 ? (
        <div className="card">
          <div className="empty-state" style={{ padding: '32px 0' }}>
            <h2 style={{ fontSize: '1.2rem' }}>No saved recipes yet</h2>
            <p style={{ marginTop: 6 }}>
              Save your first recipe and the planner will use your exact ingredients instead of guessing.
            </p>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {recipes.map(recipe => (
            <div key={recipe.id}>
              {editing?.id === recipe.id ? (
                <RecipeForm initial={editing} onSave={handleSave} onCancel={() => setEditing(null)} />
              ) : (
                <div className="card">
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer', flex: 1 }}
                      onClick={() => setExpanded(expanded === recipe.id ? null : recipe.id)}>
                      <span style={{ fontSize: '1.5rem' }}>⭐</span>
                      <div>
                        <p style={{ fontWeight: 600, fontSize: '0.95rem' }}>{recipe.name}</p>
                        <p style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>
                          {recipe.servings} servings · {recipe.ingredients.length} ingredients
                        </p>
                      </div>
                      <span style={{ marginLeft: 'auto', color: 'var(--muted)', fontSize: '0.8rem' }}>
                        {expanded === recipe.id ? '▲ hide' : '▼ show'}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: 12, marginLeft: 16 }}>
                      <button onClick={() => setEditing(recipe)}
                        style={{ fontSize: '0.82rem', color: 'var(--sage)', background: 'none', border: 'none', cursor: 'pointer' }}>
                        Edit
                      </button>
                      <button onClick={() => handleDelete(recipe.id, recipe.name)}
                        style={{ fontSize: '0.82rem', color: 'var(--red)', background: 'none', border: 'none', cursor: 'pointer' }}>
                        Delete
                      </button>
                    </div>
                  </div>

                  {expanded === recipe.id && (
                    <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 8, marginBottom: 8 }}>
                        {['Ingredient','Quantity','Unit','Category'].map(h => (
                          <p key={h} style={{ fontSize: '0.72rem', color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</p>
                        ))}
                      </div>
                      {recipe.ingredients.map((ing, i) => (
                        <div key={i} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 8, padding: '6px 0', borderBottom: '1px solid #F0EDE8', fontSize: '0.88rem' }}>
                          <span style={{ fontWeight: 500 }}>{ing.name}</span>
                          <span style={{ color: 'var(--muted)' }}>{ing.quantity}</span>
                          <span style={{ color: 'var(--muted)' }}>{ing.unit}</span>
                          <span style={{ color: 'var(--muted)' }}>{ing.category}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
