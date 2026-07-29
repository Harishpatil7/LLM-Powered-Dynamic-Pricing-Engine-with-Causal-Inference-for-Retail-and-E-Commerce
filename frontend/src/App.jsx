import { useEffect, useState } from 'react';
import { Activity, ArrowRight, Cpu, LogOut, Shield } from 'lucide-react';
import { healthCheck, getCurrentUser } from './services/pricingPlatformService';
import AuthScreen from './components/auth/AuthScreen';
import RealDataWorkspace from './components/workspace/RealDataWorkspace';

export default function App() {
  const [page, setPage] = useState('home');
  const [user, setUser] = useState(null);
  const [apiStatus, setApiStatus] = useState('checking');

  useEffect(() => {
    healthCheck().then(() => setApiStatus('connected')).catch(() => setApiStatus('offline'));
    if (!localStorage.getItem('dpeci_token')) return;
    getCurrentUser().then((account) => setUser(account)).catch(() => localStorage.removeItem('dpeci_token'));
  }, []);

  function openConsole() { setPage(user ? 'workspace' : 'auth'); }
  function signOut() {
    localStorage.removeItem('dpeci_token');
    localStorage.removeItem('dpeci_user');
    localStorage.removeItem('dpeci_retailer_id');
    localStorage.removeItem('dpeci_retailer_name');
    setUser(null);
    setPage('home');
  }

  return <div className="flex flex-col min-h-screen bg-[#09090b] relative overflow-x-hidden">
    <div className="aurora-bg"><div className="aurora-blob aurora-blob-1" /><div className="aurora-blob aurora-blob-2" /><div className="aurora-blob aurora-blob-3" /></div>
    <nav className="nav-bar app-container">
      <div className="nav-logo" onClick={() => setPage('home')}><div className="h-7 w-7 rounded-md bg-white flex items-center justify-center"><Cpu className="h-4 w-4 text-black" /></div><span className="logo-text">LLM-DPECI</span></div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <span className="telemetry-label"><span className={`status-dot ${apiStatus === 'connected' ? 'emerald' : ''}`} /> API {apiStatus}</span>
        {user ? <><span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{user.email}</span><button className="apple-button secondary" onClick={signOut} style={{ padding: '7px 12px', fontSize: 12 }}><LogOut className="h-3.5 w-3.5" /> Sign out</button></> : <button className="apple-button secondary" onClick={() => setPage('auth')} style={{ padding: '7px 12px', fontSize: 12 }}>Sign in</button>}
      </div>
    </nav>
    {page === 'home' && <main className="flex flex-col flex-1" style={{ position: 'relative', zIndex: 1 }}>
      <header className="app-container landing-hero">
        <span className="telemetry-label">EVIDENCE-BASED PRICING</span><h1 className="landing-title">The Causal Edge.</h1>
        <p className="landing-subtitle">Upload authorised retail data, verify causal price effects, and generate grounded recommendations with clear safety checks.</p>
        <div className="landing-cta-group"><button onClick={openConsole} className="apple-button" style={{ padding: '14px 28px', fontSize: 14 }}>Open workspace <ArrowRight className="h-4 w-4" /></button></div>
      </header>
      <section className="app-container"><div className="featured-specs-grid">
        <article className="spec-feature-card liquid-glass gradient-border-animated"><Activity className="h-5 w-5 text-sky-400" /><h2 className="feature-title">Your authorised data</h2><p className="feature-desc">CSV records are validated before they enter an isolated retailer workspace.</p></article>
        <article className="spec-feature-card liquid-glass gradient-border-animated"><Shield className="h-5 w-5 text-emerald-400" /><h2 className="feature-title">Verified decisions</h2><p className="feature-desc">Recommendations are blocked whenever causal diagnostics do not pass.</p></article>
      </div></section>
    </main>}
    {page === 'auth' && <AuthScreen onBack={() => setPage('home')} onAuthenticated={(account) => { setUser(account); setPage('workspace'); }} />}
    {page === 'workspace' && user && <RealDataWorkspace user={user} onBack={() => setPage('home')} />}
  </div>;
}
