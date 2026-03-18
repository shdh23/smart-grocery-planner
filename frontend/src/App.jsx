import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import PlannerChat   from './screens/PlannerChat';
import AgentProgress from './screens/AgentProgress';
import GroceryList   from './screens/GroceryList';
import History       from './screens/History';
import Recipes       from './screens/Recipes';
import Settings      from './screens/Settings';
import Login         from './screens/Login';
import Onboarding    from './screens/Onboarding';
import './index.css';

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="page"><div className="empty-state"><div className="spinner" /></div></div>;
  if (!user)   return <Navigate to="/login" replace />;
  return children;
}

function Header() {
  const { user, signOut } = useAuth();

  const navStyle = ({ isActive }) => ({
    fontSize: '0.85rem',
    fontWeight: 500,
    color: isActive ? 'var(--sage)' : 'var(--muted)',
    padding: '4px 0',
    borderBottom: isActive ? '2px solid var(--sage)' : '2px solid transparent',
    transition: 'all 0.15s',
    textDecoration: 'none',
  });

  return (
    <header className="app-header" style={{ justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: '1.4rem' }}>🛒</span>
        <div>
          <h1>Grocery Planner</h1>
          <p className="tagline">Pantry-aware · FSA-smart</p>
        </div>
      </div>
      {user && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          <nav style={{ display: 'flex', gap: 24 }}>
            <NavLink to="/"         end style={navStyle}>Plan</NavLink>
            <NavLink to="/history"  style={navStyle}>History</NavLink>
            <NavLink to="/recipes"  style={navStyle}>Recipes</NavLink>
            <NavLink to="/settings" style={navStyle}>Settings</NavLink>
          </nav>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingLeft: 16, borderLeft: '1px solid var(--border)' }}>
            <span style={{ fontSize: '0.78rem', color: 'var(--muted)', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user.email}
            </span>
            <button
              onClick={signOut}
              style={{ fontSize: '0.78rem', color: 'var(--muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
            >
              Sign out
            </button>
          </div>
        </div>
      )}
    </header>
  );
}

function AppRoutes() {
  const { user, loading } = useAuth();
  if (loading) return <div className="page"><div className="empty-state"><div className="spinner" /></div></div>;

  return (
    <>
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
        <Route path="/" element={<ProtectedRoute><PlannerChat /></ProtectedRoute>} />
        <Route path="/progress/:planId" element={<ProtectedRoute><AgentProgress /></ProtectedRoute>} />
        <Route path="/list/:planId"     element={<ProtectedRoute><GroceryList /></ProtectedRoute>} />
        <Route path="/history"          element={<ProtectedRoute><History /></ProtectedRoute>} />
        <Route path="/recipes"          element={<ProtectedRoute><Recipes /></ProtectedRoute>} />
        <Route path="/settings"         element={<ProtectedRoute><Settings /></ProtectedRoute>} />
        <Route path="*"                 element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

function OnboardingGate() {
  const { user } = useAuth();
  const [showOnboarding,    setShowOnboarding]    = React.useState(false);
  const [onboardingChecked, setOnboardingChecked] = React.useState(false);

  React.useEffect(() => {
    if (!user) { setOnboardingChecked(true); return; }
    import('./api/client').then(({ getConfig }) => {
      getConfig().then(({ data }) => {
        if (!data.onboarding_complete) setShowOnboarding(true);
        setOnboardingChecked(true);
      }).catch(() => setOnboardingChecked(true));
    });
  }, [user]);

  if (!onboardingChecked) return null;
  if (!showOnboarding)    return null;
  return <Onboarding onComplete={() => setShowOnboarding(false)} />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app-shell" style={{ position: 'relative' }}>
          <Header />
          <AppRoutes />
          <OnboardingGate />
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}
