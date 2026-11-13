import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, ShieldCheck, Truck, ShoppingBag, MapPin } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../store';
import { Button, ErrorBox, Field, Tabs } from '../components/ui';

export default function Login() {
  const { login, config, toast } = useApp();
  const navigate = useNavigate();
  const [tab, setTab] = useState('password');
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({ name: '', email: '', password: '', phone: '', code: '' });
  const [busy, setBusy] = useState(false), [error, setError] = useState(null), [otpSent, setOtpSent] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const done = () => { toast('Welcome to RouteNex'); navigate('/'); };
  const submit = async e => {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      if (tab === 'password') {
        if (mode === 'register') { await login('/auth/register', { name: form.name, email: form.email, password: form.password }); }
        else await login('/auth/login', { email: form.email, password: form.password });
        done();
      } else if (!otpSent) {
        const r = await api('/auth/otp/request', { method: 'POST', body: { phone: form.phone } });
        setOtpSent(true); if (r.demo_code) set('code', r.demo_code);
        toast(r.demo ? 'Demo code filled in for the test account' : 'Verification code sent');
      } else { await login('/auth/otp/verify', { phone: form.phone, code: form.code }); done(); }
    } catch (err) { setError(err); } finally { setBusy(false); }
  };
  return <div className="login-page">
    <section className="login-brand">
      <div className="brand large"><div className="brand-mark">R</div><div><strong>RouteNex</strong><span>Jaipur local logistics</span></div></div>
      <h1>One account for the things you need every day.</h1>
      <p>Shop local essentials, book a ride, send a parcel and follow every delivery from pickup to handover.</p>
      <div className="login-features"><div><ShoppingBag />190+ everyday essentials</div><div><Truck />Live dispatch and fleet operations</div><div><MapPin />Search places by name, then pick the right one</div><div><ShieldCheck />Secure sessions and verified payments</div></div>
      <small>Serving Jaipur, Rajasthan · Light, accessible interface</small>
    </section>
    <section className="login-form-wrap">
      <form className="login-form" onSubmit={submit}>
        <h2>{mode === 'register' ? 'Create your account' : 'Sign in'}</h2>
        <p className="muted">{mode === 'register' ? 'Use a strong password of at least 12 characters.' : 'Welcome back. Choose how you want to continue.'}</p>
        <Tabs tabs={[{ id: 'password', label: 'Email' }, { id: 'otp', label: 'Phone OTP' }]} active={tab} onChange={t => { setTab(t); setError(null); }} />
        {tab === 'password' ? <>
          {mode === 'register' && <Field label="Full name"><input required minLength={2} value={form.name} onChange={e => set('name', e.target.value)} autoComplete="name" /></Field>}
          <Field label="Email address"><input type="email" required value={form.email} onChange={e => set('email', e.target.value)} autoComplete="email" placeholder="you@example.com" /></Field>
          <Field label="Password"><input type="password" required value={form.password} onChange={e => set('password', e.target.value)} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} minLength={mode === 'register' ? 12 : 1} /></Field>
        </> : <>
          <Field label="Phone number" hint="Include country code, e.g. +919876543210"><input required value={form.phone} onChange={e => set('phone', e.target.value)} placeholder="+91…" disabled={otpSent} /></Field>
          {otpSent && <Field label="6-digit verification code"><input required inputMode="numeric" pattern="\d{6}" maxLength={6} value={form.code} onChange={e => set('code', e.target.value)} /></Field>}
        </>}
        <ErrorBox error={error} />
        <Button type="submit" loading={busy} className="full">{tab === 'otp' ? (otpSent ? 'Verify and sign in' : 'Send verification code') : mode === 'register' ? 'Create account' : 'Sign in'}<ArrowRight size={17} /></Button>
        {tab === 'password' && <p className="switch-mode">{mode === 'register' ? 'Already have an account?' : 'New to RouteNex?'} <button type="button" className="text-btn" onClick={() => setMode(mode === 'register' ? 'login' : 'register')}>{mode === 'register' ? 'Sign in' : 'Create an account'}</button></p>}
        {config?.demo_mode && <div className="demo-credentials"><strong>Demo accounts</strong><div><span>Admin</span><code>samikhan@gmail.com / sami@123</code></div><div><span>Customer</span><code>customer@routenex.in / Demo@123</code></div><div><span>Driver / Dispatcher / Fleet</span><code>driver@… / dispatcher@… / fleet@routenex.in · Demo@123</code></div><small>These credentials are for the local demo only and are disabled in production.</small></div>}
      </form>
    </section>
  </div>;
}
