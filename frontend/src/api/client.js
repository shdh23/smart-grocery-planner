/**
 * api/client.js
 * Axios instance with Supabase JWT auth on every request.
 */

import axios from 'axios';
import { supabase } from '../auth/AuthContext';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
});

// Attach the current Supabase JWT to every request automatically
api.interceptors.request.use(async (config) => {
  const { data: { session } } = await supabase.auth.getSession();
  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`;
  }
  return config;
});

export const createPlan  = (data)     => api.post('/api/plan', data);
export const getPlan     = (id)       => api.get(`/api/plan/${id}`);
export const confirmPlan = (id)       => api.post(`/api/plan/${id}/confirm`);
export const getHistory  = (limit=10) => api.get('/api/history', { params: { limit } });

export const parseIntent = (message, context) =>
  api.post('/api/parse-intent', {
    message:       message.trim(),
    meals:         context?.meals ?? [],
    extra_items:   context?.extra_items ?? [],
    active_stores: context?.active_stores ?? [],
    num_people:    context?.num_people ?? 2,
  });

export const getPantry        = (category)      => api.get('/api/pantry', { params: category ? { category } : {} });
export const addPantryItem    = (data)           => api.post('/api/pantry', data);
export const bulkAddPantry    = (items, overwrite=false) => api.post('/api/pantry/bulk', { items }, { params: { overwrite } });
export const updatePantryItem = (id, data)       => api.put(`/api/pantry/${id}`, data);
export const deletePantryItem = (id)             => api.delete(`/api/pantry/${id}`);

export const getConfig    = ()     => api.get('/api/config');
export const updateConfig = (data) => api.put('/api/config', data);

export const getPreferences   = ()               => api.get('/api/preferences');
export const upsertPreference = (pattern, store) =>
  api.put('/api/preferences', null, { params: { ingredient_pattern: pattern, preferred_store: store } });

export default api;

export const getRecipes    = ()           => api.get('/api/recipes');
export const createRecipe  = (data)       => api.post('/api/recipes', data);
export const updateRecipe  = (id, data)   => api.put(`/api/recipes/${id}`, data);
export const deleteRecipe  = (id)         => api.delete(`/api/recipes/${id}`);