import { useState } from 'react';
import { ArrowLeft, LockKeyhole, Mail, UserPlus } from 'lucide-react';
import { loginUser, registerUser } from '../../services/pricingPlatformService';

export default function AuthScreen({ onBack, onAuthenticated }) {
  const [mode, setMode] = useState('register');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError('');
    if (mode === 'register' && password !== confirmPassword) {
      setError('Passwords must match.');
      return;
    }
    setBusy(true);
    try {
      const session = await (mode === 'register' ? registerUser({ email, password }) : loginUser({ email, password }));
      localStorage.setItem('dpeci_token', session.access_token);
      localStorage.setItem('dpeci_user', JSON.stringify(session.user));
      onAuthenticated(session.user);
    } catch (requestError) {
      setError(requestError.message || 'Unable to continue.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-container" style={{ paddingTop: 72, paddingBottom: 72, position: 'relative', zIndex: 1 }}>
      <button className="apple-button secondary" onClick={onBack} style={{ padding: '8px 14px', fontSize: 12 }}><ArrowLeft className="h-3.5 w-3.5" /> Back</button>
      <section className="apple-card liquid-glass" style={{ maxWidth: 480, marginTop: 28 }}>
        <div className="feature-icon-container"><LockKeyhole className="h-4 w-4 text-sky-400" /></div>
        <span className="telemetry-label" style={{ display: 'block', marginTop: 18 }}>SECURE LOCAL WORKSPACE</span>
        <h1 style={{ marginTop: 10, fontSize: 30 }}>{mode === 'register' ? 'Create your account' : 'Welcome back'}</h1>
        <p style={{ color: 'var(--text-secondary)', marginTop: 10, fontSize: 14 }}>Your retailer workspaces and uploaded evidence are accessible only after sign-in.</p>
        <form onSubmit={submit} style={{ marginTop: 24, display: 'grid', gap: 12 }}>
          <label style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Email
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}><Mail className="h-4 w-4 text-sky-400" /><input className="chat-input" style={{ width: '100%' }} type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required /></span>
          </label>
          <label style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Password
            <input className="chat-input" style={{ width: '100%', marginTop: 6 }} type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} minLength="8" required />
          </label>
          {mode === 'register' && <label style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Confirm password
            <input className="chat-input" style={{ width: '100%', marginTop: 6 }} type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" minLength="8" required />
          </label>}
          {error && <p style={{ color: 'var(--accent-orange)', fontSize: 13 }}>{error}</p>}
          <button className="apple-button" disabled={busy}>{mode === 'register' ? <><UserPlus className="h-4 w-4" /> Create account</> : 'Sign in'}</button>
        </form>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 18 }}>
          {mode === 'register' ? 'Already have an account?' : 'New to LLM-DPECI?'}{' '}
          <button onClick={() => { setMode(mode === 'register' ? 'login' : 'register'); setError(''); }} style={{ color: 'var(--accent-blue)', background: 'none', border: 0, cursor: 'pointer' }}>{mode === 'register' ? 'Sign in' : 'Create an account'}</button>
        </p>
      </section>
    </main>
  );
}
