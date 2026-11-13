import React, { useState } from 'react';
import { Wallet, Plus, Tag, ArrowUpRight, ArrowDownLeft } from 'lucide-react';
import { api, money, dateTime, uuid } from '../api';
import { useApp } from '../store';
import { Button, Card, Empty, ErrorBox, Field, Loading, Stat, Table, useAsync } from '../components/ui';
import PaymentModal from '../components/PaymentModal';

export default function WalletPage() {
  const { toast, config } = useApp();
  const wallet = useAsync(() => api('/wallet'), []);
  const coupons = useAsync(() => api('/coupons'), []);
  const [amount, setAmount] = useState(500), [busy, setBusy] = useState(false), [error, setError] = useState(null), [checkout, setCheckout] = useState(null);
  const topup = async e => { e.preventDefault(); setBusy(true); setError(null); try { const c = await api('/wallet/topup', { method: 'POST', body: { purpose: 'wallet_topup', amount: Number(amount), idempotency_key: uuid() } }); setCheckout(c); } catch (e) { setError(e); } finally { setBusy(false); } };
  return <div className="stack"><div className="page-head"><div><h1>Wallet & offers</h1><p>Top up through a verified payment and keep a clear transaction history.</p></div></div>
    <div className="two-col"><Card title="Balance"><div className="wallet-balance"><Wallet size={30} /><strong>{money(wallet.data?.balance)}</strong><span>Available balance</span></div><form onSubmit={topup} className="stack-sm"><Field label="Top-up amount (₹)"><input type="number" min="10" max="100000" step="1" required value={amount} onChange={e => setAmount(e.target.value)} /></Field><div className="chips">{[100,500,1000,2000].map(v => <button type="button" key={v} onClick={() => setAmount(v)}>{money(v)}</button>)}</div><ErrorBox error={error} /><Button loading={busy}><Plus size={16} />Add money{config?.payment_provider === 'demo' ? ' (test)' : ''}</Button></form></Card>
    <Card title="Available offers">{coupons.loading ? <Loading /> : <div className="offer-list">{coupons.data?.map(c => <div key={c.code} className="offer"><Tag size={19} /><div><strong>{c.title}</strong><small>{c.scope === 'all' ? 'All services' : c.scope} · minimum {money(c.min_amount)}{c.one_time ? ' · one use per customer' : ''}</small></div><code>{c.code}</code></div>)}</div>}</Card></div>
    <Card title="Recent transactions" action={<Button variant="secondary" onClick={wallet.reload}>Refresh</Button>}><Table columns={['Date','Description','Type','Amount','Balance']} rows={wallet.data?.transactions || []} render={t => <><td>{dateTime(t.created_at)}</td><td>{t.note}</td><td>{t.kind}</td><td className={t.amount >= 0 ? 'positive' : ''}>{t.amount >= 0 ? '+' : ''}{money(t.amount)}</td><td>{money(t.balance_after)}</td></>} empty="No wallet transactions yet" /></Card>
    {checkout && <PaymentModal checkout={checkout} onClose={() => setCheckout(null)} onSuccess={() => { wallet.reload(); toast('Wallet updated after verified payment'); }} />}
  </div>;
}
