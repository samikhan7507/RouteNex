import React, { useState } from 'react';
import { Monitor, KeyRound, User } from 'lucide-react';
import { api, dateTime } from '../api';
import { useApp } from '../store';
import { Button, Card, ErrorBox, Field, Table, useAsync } from '../components/ui';

export default function Settings() {
  const { user, setUser, refresh, toast } = useApp();
  const [name, setName] = useState(user.name);
  const [passwords, setPasswords] = useState({ current_password: '', new_password: '' });
  const [error, setError] = useState(null), [busy, setBusy] = useState(false);
  const sessions = useAsync(() => api('/auth/sessions'), []);
  const saveProfile = async e => { e.preventDefault(); setBusy(true); try { const u = await api('/auth/me', { method: 'PATCH', body: { name } }); setUser({ ...user, ...u }); toast('Profile updated'); } catch (e) { setError(e); } finally { setBusy(false); } };
  const changePassword = async e => { e.preventDefault(); setBusy(true); try { await api('/auth/change-password', { method: 'POST', body: passwords }); setPasswords({ current_password: '', new_password: '' }); toast('Password changed; other devices signed out'); sessions.reload(); } catch (e) { setError(e); } finally { setBusy(false); } };
  return <div className="stack"><div className="page-head"><div><h1>Account settings</h1><p>Manage your profile, password and signed-in devices.</p></div></div><ErrorBox error={error} />
    <div className="two-col"><Card title="Profile"><form onSubmit={saveProfile} className="stack-sm"><Field label="Full name"><input value={name} minLength={2} required onChange={e => setName(e.target.value)} /></Field><Field label="Email"><input value={user.email || user.phone || ''} disabled /></Field><Button loading={busy}>Save profile</Button></form></Card>
    <Card title="Change password"><form onSubmit={changePassword} className="stack-sm"><Field label="Current password"><input type="password" required value={passwords.current_password} onChange={e => setPasswords({ ...passwords, current_password: e.target.value })} /></Field><Field label="New password" hint="At least 12 characters"><input type="password" required minLength={12} value={passwords.new_password} onChange={e => setPasswords({ ...passwords, new_password: e.target.value })} /></Field><Button loading={busy}><KeyRound size={16} />Change password</Button></form></Card></div>
    <Card title="Signed-in devices" action={<Button variant="secondary" onClick={sessions.reload}>Refresh</Button>}><Table columns={['Device','IP address','Signed in','Last active','']} rows={sessions.data || []} render={s => <><td>{s.current && <strong>Current · </strong>}{s.user_agent?.slice(0, 70) || 'Unknown device'}</td><td>{s.ip_address}</td><td>{dateTime(s.created_at)}</td><td>{dateTime(s.last_seen_at)}</td><td>{!s.current && <Button variant="secondary" onClick={async () => { await api(`/auth/sessions/${s.id}`, { method: 'DELETE' }); sessions.reload(); toast('Device signed out'); }}>Sign out</Button>}</td></>} /></Card>
  </div>;
}
