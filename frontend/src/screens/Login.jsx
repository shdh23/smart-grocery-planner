/**
 * src/screens/Login.jsx
 * Login + Signup screen. Redirects to / on success.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export default function Login() {
  const { signIn, signUp } = useAuth();
  const navigate = useNavigate();

  const [mode,     setMode]     = useState('login');   // 'login' | 'signup'
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');
  const [info,     setInfo]     = useState('');

  const submit = async () => {
    if (!email || !password) return setError('Please enter email and password.');
    setError(''); setInfo(''); setLoading(true);

    if (mode === 'signup') {
      const { error } = await signUp(email, password);
      if (error) { setError(error.message); }
      else        { setInfo('Check your email to confirm your account, then log in.'); setMode('login'); }
    } else {
      const { error } = await signIn(email, password);
      if (error) { setError(error.message); }
      else        { navigate('/'); }
    }
    setLoading(false);
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--cream)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
    }}>
      <div style={{ width: '100%', maxWidth: 400 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{ fontSize: '2.5rem', marginBottom: 8 }}>🛒</div>
          <h1 style={{ fontSize: '1.8rem', marginBottom: 4 }}>Grocery Planner</h1>
          <p style={{ color: 'var(--muted)', fontSize: '0.88rem' }}>AI-powered · Pantry-aware · FSA-smart</p>
        </div>

        <div className="card">
          {/* Tab switcher */}
          <div style={{ display: 'flex', gap: 0, marginBottom: 24, borderBottom: '1px solid var(--border)' }}>
            {['login', 'signup'].map(m => (
              <button key={m} onClick={() => { setMode(m); setError(''); setInfo(''); }}
                style={{
                  flex: 1, padding: '10px', background: 'none', border: 'none',
                  borderBottom: mode === m ? '2px solid var(--sage)' : '2px solid transparent',
                  color: mode === m ? 'var(--sage)' : 'var(--muted)',
                  fontWeight: mode === m ? 600 : 400,
                  fontSize: '0.9rem', cursor: 'pointer', marginBottom: -1,
                  transition: 'all 0.15s',
                }}>
                {m === 'login' ? 'Log in' : 'Sign up'}
              </button>
            ))}
          </div>

          {error && <div className="alert alert-error" style={{ marginBottom: 16 }}>{error}</div>}
          {info  && <div className="alert alert-success" style={{ marginBottom: 16 }}>{info}</div>}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <p style={{ fontSize: '0.78rem', color: 'var(--muted)', marginBottom: 6 }}>Email</p>
              <input
                className="text-input"
                style={{ width: '100%' }}
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && submit()}
              />
            </div>
            <div>
              <p style={{ fontSize: '0.78rem', color: 'var(--muted)', marginBottom: 6 }}>Password</p>
              <input
                className="text-input"
                style={{ width: '100%' }}
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && submit()}
              />
            </div>
            <button
              className="btn btn-primary"
              style={{ width: '100%', justifyContent: 'center', padding: '12px', marginTop: 4 }}
              onClick={submit}
              disabled={loading}
            >
              {loading ? '…' : mode === 'login' ? 'Log in' : 'Create account'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
