import React, { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Home, ShoppingBag, Car, Package, Wallet, UserCog, LayoutDashboard, Truck, Users, Bell, LogOut, Menu, X, Bot, Settings, ShieldCheck } from 'lucide-react';
import { api, dateTime } from '../api';
import { useApp } from '../store';
import Assistant from './Assistant';

const NAV = [
  { to: '/', label: 'Overview', icon: Home, roles: ['customer','admin','dispatcher','fleet_manager','driver'] },
  { to: '/shop', label: 'Shop', icon: ShoppingBag, roles: ['customer','admin'] },
  { to: '/trips', label: 'Rides & parcels', icon: Car, roles: ['customer','admin'] },
  { to: '/orders', label: 'My orders', icon: Package, roles: ['customer','admin'] },
  { to: '/wallet', label: 'Wallet & offers', icon: Wallet, roles: ['customer','admin'] },
  { to: '/driver', label: 'Driver workspace', icon: UserCog, roles: ['driver'] },
  { to: '/operations', label: 'Operations', icon: LayoutDashboard, roles: ['dispatcher','fleet_manager','admin'] },
  { to: '/fleet', label: 'Fleet', icon: Truck, roles: ['fleet_manager','admin','dispatcher'] },
  { to: '/admin', label: 'Administration', icon: ShieldCheck, roles: ['admin'] },
  { to: '/settings', label: 'Account settings', icon: Settings, roles: ['customer','admin','dispatcher','fleet_manager','driver'] },
];

export default function Layout() {
  const { user, logout, config } = useApp();
  const navigate = useNavigate();
  const [mobile, setMobile] = useState(false);
  const [notes, setNotes] = useState([]);
  const [showNotes, setShowNotes] = useState(false);
  const [assistant, setAssistant] = useState(false);
  useEffect(() => {
    const load = () => api('/notifications').then(setNotes).catch(() => {});
    load(); const t = setInterval(load, 30000); return () => clearInterval(t);
  }, []);
  const unread = notes.filter(n => !n.read).length;
  const links = NAV.filter(n => n.roles.includes(user.role));
  return <div className="app-shell">
    <aside className={`sidebar ${mobile ? 'open' : ''}`}>
      <div className="brand"><div className="brand-mark">R</div><div><strong>RouteNex</strong><span>Jaipur local logistics</span></div><button className="icon-btn mobile-close" onClick={() => setMobile(false)}><X size={20} /></button></div>
      {config?.demo_mode && <div className="demo-pill">Demo environment · test payments</div>}
      <nav>{links.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} end={to === '/'} onClick={() => setMobile(false)} className={({ isActive }) => isActive ? 'active' : ''}><Icon size={18} />{label}</NavLink>)}</nav>
      <div className="sidebar-user"><div className="avatar">{user.name?.[0] || 'U'}</div><div><strong>{user.name}</strong><span>{user.role.replaceAll('_', ' ')}</span></div><button className="icon-btn" title="Sign out" onClick={async () => { await logout(); navigate('/login'); }}><LogOut size={17} /></button></div>
    </aside>
    {mobile && <div className="sidebar-scrim" onClick={() => setMobile(false)} />}
    <div className="main-area">
      <header className="topbar">
        <button className="icon-btn menu-btn" onClick={() => setMobile(true)} aria-label="Open menu"><Menu size={21} /></button>
        <div className="topbar-title"><strong>RouteNex</strong><span>{new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })}</span></div>
        <div className="topbar-actions">
          <button className="icon-btn assistant-toggle" onClick={() => setAssistant(true)} title="Assistant"><Bot size={20} /></button>
          <div className="notes-wrap"><button className="icon-btn" onClick={() => setShowNotes(v => !v)} aria-label="Notifications"><Bell size={20} />{unread > 0 && <span className="dot">{unread}</span>}</button>
            {showNotes && <div className="notes-panel"><header><strong>Notifications</strong><button className="text-btn" onClick={() => setShowNotes(false)}>Close</button></header>{notes.length === 0 ? <p className="muted">No notifications yet.</p> : notes.slice(0, 12).map(n => <button key={n.id} className={`note ${n.read ? '' : 'unread'}`} onClick={async () => { await api(`/notifications/${n.id}/read`, { method: 'POST' }); setNotes(ns => ns.map(x => x.id === n.id ? { ...x, read: true } : x)); }}><strong>{n.title}</strong><p>{n.body}</p><small>{dateTime(n.created_at)}</small></button>)}</div>}
          </div>
          <div className="avatar small">{user.name?.[0] || 'U'}</div>
        </div>
      </header>
      <main className="page"><Outlet /></main>
    </div>
    {assistant && <Assistant onClose={() => setAssistant(false)} />}
  </div>;
}
