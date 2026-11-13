import React from 'react';
import { Link } from 'react-router-dom';
import { ShoppingBag, Car, Package, Wallet, Truck, LayoutDashboard, Users, ArrowRight, ShieldCheck } from 'lucide-react';
import { api, money } from '../api';
import { useApp } from '../store';
import { Card, Stat, Badge, useAsync, Loading, Empty } from '../components/ui';

export default function Home() {
  const { user } = useApp();
  const ops = ['admin','dispatcher','fleet_manager'].includes(user.role);
  const summary = useAsync(() => ops ? api('/optimizer/summary') : Promise.all([api('/orders?kind=active'), api('/trips?kind=active'), api('/wallet')]).then(([orders, trips, wallet]) => ({ orders: orders.length, trips: trips.length, wallet: wallet.balance })), [user.role]);
  const admin = useAsync(() => user.role === 'admin' ? api('/admin/overview') : Promise.resolve(null), [user.role]);
  const quick = user.role === 'driver' ? [{ to: '/driver', icon: Truck, title: 'Driver workspace', text: 'Go online, accept requests and complete handovers.' }]
    : ops ? [{ to: '/operations', icon: LayoutDashboard, title: 'Operations', text: 'Plan routes, monitor alerts and review performance.' }, { to: '/fleet', icon: Truck, title: 'Fleet', text: 'Manage vehicles, drivers and maintenance.' }, ...(user.role === 'admin' ? [{ to: '/admin', icon: Users, title: 'Administration', text: 'See who is signed in, audit activity and manage the catalogue.' }] : [])]
    : [{ to: '/shop', icon: ShoppingBag, title: 'Shop essentials', text: 'Stationery, groceries, electronics and hostel needs.' }, { to: '/trips', icon: Car, title: 'Book a ride or parcel', text: 'Search pickup and drop-off, compare fares and track the trip.' }, { to: '/orders', icon: Package, title: 'Track orders', text: 'Follow status, delivery windows and handover codes.' }, { to: '/wallet', icon: Wallet, title: 'Wallet & offers', text: 'Top up securely and review available offers.' }];
  return <div className="stack">
    <div className="page-head"><div><h1>{user.role === 'customer' ? `Hello, ${user.name.split(' ')[0]}` : 'Operations overview'}</h1><p>{user.role === 'customer' ? 'What would you like to do today?' : 'A clear view of work, people and vehicles right now.'}</p></div>{user.role === 'customer' && <Link className="btn primary" to="/shop">Start shopping<ArrowRight size={16} /></Link>}</div>
    {summary.loading ? <Loading /> : <div className="stat-grid">
      {ops ? <><Stat label="Awaiting dispatch" value={summary.data?.pending_orders ?? '—'} icon={Package} /><Stat label="Assigned orders" value={summary.data?.assigned_orders ?? '—'} icon={Truck} /><Stat label="Available vehicles" value={summary.data?.available_vehicles ?? '—'} icon={Truck} /><Stat label="Open alerts" value={summary.data?.open_alerts ?? '—'} icon={ShieldCheck} /></>
        : <><Stat label="Active orders" value={summary.data?.orders ?? 0} icon={Package} /><Stat label="Active trips" value={summary.data?.trips ?? 0} icon={Car} /><Stat label="Wallet balance" value={money(summary.data?.wallet)} icon={Wallet} /></>}
    </div>}
    {admin.data && <div className="stat-grid"><Stat label="Registered users" value={admin.data.users} icon={Users} /><Stat label="Active users" value={admin.data.active_users} note={`${admin.data.active_sessions} signed-in sessions`} icon={ShieldCheck} /><Stat label="Products" value={admin.data.products} icon={ShoppingBag} /><Stat label="Orders today" value={admin.data.orders_today} icon={Package} /></div>}
    <div className="quick-grid">{quick.map(({ to, icon: Icon, title, text }) => <Link key={to} to={to} className="quick-card"><Icon size={24} /><h3>{title}</h3><p>{text}</p><span>Open <ArrowRight size={15} /></span></Link>)}</div>
    {user.role === 'customer' && <Card title="Good to know"><div className="info-list"><p><strong>Delivery:</strong> free above ₹499; otherwise ₹39. Choose a delivery window at checkout.</p><p><strong>Payments:</strong> cash on delivery, wallet, or secure online payment. Online payments are confirmed only after server verification.</p><p><strong>Handover codes:</strong> share your delivery code only with the driver. Staff cannot see your real code.</p></div></Card>}
  </div>;
}
