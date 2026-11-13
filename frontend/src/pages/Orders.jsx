import React, { useState } from 'react';
import { Package, MapPin, Clock, ShieldCheck } from 'lucide-react';
import { api, money, dateTime, titleCase } from '../api';
import { useApp } from '../store';
import { Badge, Button, Card, Empty, ErrorBox, Loading, Modal, Tabs, useAsync } from '../components/ui';
import PaymentModal, { createCheckout } from '../components/PaymentModal';

const STEPS = ['placed','assigned','picked_up','out_for_delivery','delivered'];
function OrderDetail({ order: o, onClose, onChanged }) {
  const { toast } = useApp();
  const [busy, setBusy] = useState(false), [error, setError] = useState(null), [checkout, setCheckout] = useState(null);
  const cancel = async () => { if (!confirm('Cancel this order? Stock is released and eligible prepaid amounts are refunded.')) return; setBusy(true); try { await api(`/orders/${o.id}/cancel`, { method: 'POST', body: { reason: 'Customer cancelled from order details' } }); toast('Order cancelled'); onChanged(); onClose(); } catch (e) { setError(e); } finally { setBusy(false); } };
  const pay = async () => { setBusy(true); try { setCheckout(await createCheckout('order', o.id)); } catch (e) { setError(e); } finally { setBusy(false); } };
  if (checkout) return <PaymentModal checkout={checkout} onClose={() => setCheckout(null)} onSuccess={onChanged} />;
  const step = STEPS.indexOf(o.status);
  return <Modal title={`Order #${o.id}`} onClose={onClose} wide><div className="stack-sm"><div className="trip-status"><Badge value={o.status} /><Badge value={o.payment_status} /><span className="muted">{dateTime(o.created_at)}</span></div>
    {step >= 0 && <ol className="timeline">{STEPS.map((s, i) => <li key={s} className={i <= step ? 'done' : ''}><span>{i + 1}</span>{titleCase(s)}</li>)}</ol>}
    <div className="detail-grid"><div><span>Total</span><strong>{money(o.total)}</strong></div><div><span>Payment</span><strong>{titleCase(o.payment_method)}</strong></div><div><span>Delivery window</span><strong>{dateTime(o.delivery_window_start)} – {new Date(o.delivery_window_end).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</strong></div><div><span>Address</span><strong>{o.address.label}, {o.address.line1}</strong></div></div>
    <div className="order-items">{o.items.map((i, n) => <div key={n}><span>{i.name} × {i.quantity}</span><strong>{money(i.total)}</strong></div>)}</div>
    {o.delivery_otp && !['cancelled','failed','delivered'].includes(o.status) && <div className="otp-box"><span><ShieldCheck size={16} />Delivery code — share only with the driver at handover</span><strong>{o.delivery_otp}</strong></div>}
    <ErrorBox error={error} /><div className="modal-actions">{o.status === 'awaiting_payment' && <Button loading={busy} onClick={pay}>Complete payment</Button>}{['awaiting_payment','placed','assigned'].includes(o.status) && <Button variant="danger" loading={busy} onClick={cancel}>Cancel order</Button>}<Button variant="secondary" onClick={onClose}>Close</Button></div>
  </div></Modal>;
}
export default function Orders() {
  const [tab, setTab] = useState('active'), [detail, setDetail] = useState(null);
  const orders = useAsync(() => api(`/orders?kind=${tab}`), [tab]);
  return <div className="stack"><div className="page-head"><div><h1>My orders</h1><p>Track every delivery and keep your handover code ready.</p></div></div><Tabs tabs={[{ id: 'active', label: 'Active' }, { id: 'history', label: 'History' }, { id: '', label: 'All' }]} active={tab} onChange={setTab} />
    <Card>{orders.loading ? <Loading /> : !orders.data?.length ? <Empty title="No orders here" text="Your shop orders will appear here after checkout." icon={Package} /> : <div className="order-list">{orders.data.map(o => <button key={o.id} className="order-row" onClick={() => setDetail(o)}><div className="trip-icon"><Package size={20} /></div><div><strong>Order #{o.id} · {o.items.map(i => i.name).join(', ').slice(0, 70)}</strong><small><MapPin size={13} />{o.address.label} · <Clock size={13} />{dateTime(o.created_at)}</small></div><Badge value={o.status} /><strong>{money(o.total)}</strong></button>)}</div>}</Card>
    {detail && <OrderDetail order={detail} onClose={() => setDetail(null)} onChanged={orders.reload} />}
  </div>;
}
