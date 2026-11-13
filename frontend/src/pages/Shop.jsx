import React, { useEffect, useState } from 'react';
import { Search, ShoppingCart, Plus, Minus, Trash2, MapPin, Tag, PackageCheck } from 'lucide-react';
import { api, money, uuid } from '../api';
import { useApp } from '../store';
import { Button, Card, Empty, ErrorBox, Field, Loading, Modal, Tabs, useAsync } from '../components/ui';
import PlaceSearch from '../components/PlaceSearch';
import PaymentModal, { createCheckout } from '../components/PaymentModal';

function AddressForm({ onSaved, onCancel }) {
  const [place, setPlace] = useState(null), [form, setForm] = useState({ label: 'Home', line1: '', pincode: '', city: 'Jaipur', state: 'Rajasthan' });
  const [busy, setBusy] = useState(false), [error, setError] = useState(null);
  const submit = async e => { e.preventDefault(); if (!place) return setError(new Error('Search and select a location first')); setBusy(true); setError(null); try { const a = await api('/addresses', { method: 'POST', body: { ...form, lat: place.lat, lng: place.lng } }); onSaved(a); } catch (e) { setError(e); } finally { setBusy(false); } };
  return <form onSubmit={submit} className="stack-sm"><PlaceSearch label="Delivery location" value={place} onChange={p => { setPlace(p); if (p) setForm(f => ({ ...f, line1: f.line1 || p.name })); }} /><Field label="Flat / house / street"><input required minLength={5} value={form.line1} onChange={e => setForm({ ...form, line1: e.target.value })} /></Field><div className="form-row"><Field label="Label"><input required value={form.label} onChange={e => setForm({ ...form, label: e.target.value })} /></Field><Field label="PIN code"><input required pattern="\d{6}" value={form.pincode} onChange={e => setForm({ ...form, pincode: e.target.value })} /></Field></div><ErrorBox error={error} /><div className="modal-actions"><Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button><Button loading={busy}>Save address</Button></div></form>;
}

function Checkout({ cart, addresses, onClose, onDone }) {
  const { config, toast } = useApp();
  const [addressId, setAddressId] = useState(addresses[0]?.id || '');
  const [addAddress, setAddAddress] = useState(false), [localAddresses, setLocalAddresses] = useState(addresses);
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
  const [date, setDate] = useState(today), [start, setStart] = useState('08:00'), [end, setEnd] = useState('23:59');
  const [method, setMethod] = useState('cod'), [coupon, setCoupon] = useState(''), [discount, setDiscount] = useState(0);
  const [busy, setBusy] = useState(false), [error, setError] = useState(null), [checkout, setCheckout] = useState(null);
  const applyCoupon = async () => { try { const r = await api('/coupons/validate', { method: 'POST', body: { code: coupon, amount_paise: Math.round(cart.subtotal * 100), scope: 'shop' } }); setDiscount(r.discount); toast(`${r.code} applied`); } catch (e) { setDiscount(0); setError(e); } };
  const submit = async e => {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      const body = { address_id: Number(addressId), payment_method: method, coupon: coupon || null, priority: 1,
        delivery_window_start: `${date}T${start}:00+05:30`, delivery_window_end: `${date}T${end}:00+05:30`, idempotency_key: uuid() };
      const order = await api('/orders', { method: 'POST', body });
      if (order.status === 'awaiting_payment') { const c = await createCheckout('order', order.id); setCheckout(c); }
      else { toast(`Order #${order.id} placed`); onDone(); }
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  if (checkout) return <PaymentModal checkout={checkout} onClose={onClose} onSuccess={onDone} />;
  const total = Math.max(0, cart.subtotal - discount) + cart.delivery_fee;
  return <Modal title="Checkout" onClose={onClose} wide>
    {addAddress ? <AddressForm onCancel={() => setAddAddress(false)} onSaved={a => { setLocalAddresses(x => [...x, a]); setAddressId(a.id); setAddAddress(false); }} /> :
    <form onSubmit={submit} className="stack-sm">
      <div className="checkout-grid"><div className="stack-sm">
        <div className="section-label"><MapPin size={16} />Delivery address</div>
        {localAddresses.length === 0 ? <p className="muted">Add a delivery address to continue.</p> : <select required value={addressId} onChange={e => setAddressId(e.target.value)}>{localAddresses.map(a => <option key={a.id} value={a.id}>{a.label} — {a.line1}, {a.pincode}</option>)}</select>}
        <Button type="button" variant="secondary" onClick={() => setAddAddress(true)}><Plus size={15} />Add address</Button>
        <div className="section-label">Delivery window</div>
        <div className="form-row three"><Field label="Date"><input type="date" required min={today} value={date} onChange={e => setDate(e.target.value)} /></Field><Field label="From"><input type="time" required value={start} onChange={e => setStart(e.target.value)} /></Field><Field label="To"><input type="time" required value={end} onChange={e => setEnd(e.target.value)} /></Field></div>
        <div className="section-label">Payment method</div>
        <div className="radio-cards">
          {[['cod','Cash on delivery','Pay the driver at handover'],['wallet','Wallet','Use your verified wallet balance'],['razorpay', config?.payment_provider === 'demo' ? 'UPI / card (test)' : 'UPI / card', config?.payment_provider === 'demo' ? 'Simulated payment, no real charge' : 'Secure Razorpay checkout']].map(([id, title, text]) => <label key={id} className={`radio-card ${method === id ? 'selected' : ''}`}><input type="radio" name="payment" value={id} checked={method === id} onChange={() => setMethod(id)} /><div><strong>{title}</strong><small>{text}</small></div></label>)}
        </div>
      </div><div className="order-summary"><h3>Order summary</h3><div><span>Subtotal</span><strong>{money(cart.subtotal)}</strong></div><div><span>Delivery</span><strong>{cart.delivery_fee ? money(cart.delivery_fee) : 'Free'}</strong></div>{discount > 0 && <div className="discount"><span>Offer discount</span><strong>−{money(discount)}</strong></div>}<div className="coupon-row"><input placeholder="Offer code" value={coupon} onChange={e => setCoupon(e.target.value.toUpperCase())} /><Button type="button" variant="secondary" onClick={applyCoupon}><Tag size={15} />Apply</Button></div><div className="total"><span>Total</span><strong>{money(total)}</strong></div><ErrorBox error={error} /><Button className="full" loading={busy} disabled={!addressId}>Place order · {money(total)}</Button><small className="muted">Stock is reserved atomically. Online orders are confirmed only after payment verification.</small></div></div>
    </form>}
  </Modal>;
}

export default function Shop() {
  const { toast } = useApp();
  const [tab, setTab] = useState('browse'), [q, setQ] = useState(''), [category, setCategory] = useState(''), [sort, setSort] = useState('popular');
  const [selected, setSelected] = useState(null), [checkout, setCheckout] = useState(false);
  const products = useAsync(() => api(`/products?q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}&sort=${sort}&page_size=100`), [q, category, sort]);
  const categories = useAsync(() => api('/categories'), []);
  const cart = useAsync(() => api('/cart'), []);
  const addresses = useAsync(() => api('/addresses'), []);
  const [debounced, setDebounced] = useState('');
  useEffect(() => { const t = setTimeout(() => setQ(debounced), 300); return () => clearTimeout(t); }, [debounced]);
  const add = async (p, quantity = 1) => { try { const current = cart.data?.items.find(i => i.product.id === p.id)?.quantity || 0; const c = await api('/cart', { method: 'PUT', body: { product_id: p.id, quantity: Math.min(50, current + quantity) } }); cart.setData(c); toast(`${p.name} added to basket`); } catch (e) { toast(e.message, 'error'); } };
  const setQty = async (id, quantity) => { try { const c = await api('/cart', { method: 'PUT', body: { product_id: id, quantity } }); cart.setData(c); } catch (e) { toast(e.message, 'error'); } };
  const count = cart.data?.items.reduce((n, i) => n + i.quantity, 0) || 0;
  return <div className="stack">
    <div className="page-head"><div><h1>Shop everyday essentials</h1><p>Real product photos, clear prices and reliable local delivery.</p></div><Button variant={tab === 'cart' ? 'primary' : 'secondary'} onClick={() => setTab('cart')}><ShoppingCart size={17} />Basket{count > 0 && <span className="tab-count">{count}</span>}</Button></div>
    <Tabs tabs={[{ id: 'browse', label: 'Browse products' }, { id: 'cart', label: 'Basket', count }]} active={tab} onChange={setTab} />
    {tab === 'browse' ? <>
      <div className="toolbar"><div className="search-box"><Search size={17} /><input placeholder="Search notebooks, rice, chargers…" value={debounced} onChange={e => setDebounced(e.target.value)} aria-label="Search products" /></div><select value={sort} onChange={e => setSort(e.target.value)} aria-label="Sort products"><option value="popular">Catalogue order</option><option value="price_asc">Price: low to high</option><option value="price_desc">Price: high to low</option><option value="name">Name A–Z</option></select></div>
      <div className="chips"><button className={!category ? 'active' : ''} onClick={() => setCategory('')}>All</button>{categories.data?.map(c => <button key={c.name} className={category === c.name ? 'active' : ''} onClick={() => setCategory(c.name)}>{c.name}<span>{c.count}</span></button>)}</div>
      {products.loading ? <Loading /> : products.error ? <ErrorBox error={products.error} /> : products.data?.items.length === 0 ? <Empty title="No products match" text="Try another search or category." /> : <div className="product-grid">{products.data.items.map(p => <article key={p.id} className="product-card"><button className="product-image" onClick={() => setSelected(p)}><img src={p.image} alt={p.name} loading="lazy" />{p.available === 0 && <span className="sold-out">Out of stock</span>}</button><div className="product-body"><small>{p.category}</small><h3><button onClick={() => setSelected(p)}>{p.name}</button></h3><p>{p.unit} · {p.brand}</p><div className="product-bottom"><div><strong>{money(p.price)}</strong>{p.compare_at > p.price && <del>{money(p.compare_at)}</del>}</div><Button variant="secondary" disabled={p.available === 0} onClick={() => add(p)} aria-label={`Add ${p.name}`}><Plus size={16} />Add</Button></div></div></article>)}</div>}
    </> : <Card title={`Basket (${count} items)`}>{cart.loading ? <Loading /> : !cart.data?.items.length ? <Empty title="Your basket is empty" text="Browse the catalogue and add what you need." icon={ShoppingCart} /> : <><div className="cart-list">{cart.data.items.map(i => <div key={i.product.id} className="cart-row"><img src={i.product.image} alt="" /><div><strong>{i.product.name}</strong><small>{money(i.product.price)} · {i.product.unit}</small></div><div className="qty"><button className="icon-btn" onClick={() => setQty(i.product.id, i.quantity - 1)} aria-label="Decrease"><Minus size={15} /></button><span>{i.quantity}</span><button className="icon-btn" onClick={() => setQty(i.product.id, i.quantity + 1)} aria-label="Increase"><Plus size={15} /></button></div><strong>{money(i.line_total)}</strong><button className="icon-btn" onClick={() => setQty(i.product.id, 0)} aria-label="Remove"><Trash2 size={16} /></button></div>)}</div><div className="cart-footer"><div><span>Subtotal <strong>{money(cart.data.subtotal)}</strong></span><span>Delivery <strong>{cart.data.delivery_fee ? money(cart.data.delivery_fee) : 'Free'}</strong></span><span className="total">Estimated total <strong>{money(cart.data.estimated_total)}</strong></span></div><Button onClick={() => setCheckout(true)}>Checkout<PackageCheck size={17} /></Button></div></>}</Card>}
    {selected && <Modal title={selected.name} onClose={() => setSelected(null)}><img className="detail-photo" src={selected.image} alt={selected.name} /><p>{selected.description}</p><div className="detail-meta"><span>{selected.category}</span><span>{selected.unit}</span><span>{selected.available} available</span></div><small className="muted">{selected.image_credit}. Photograph is illustrative of the product category.</small><div className="modal-actions"><strong className="price">{money(selected.price)}</strong><Button disabled={selected.available === 0} onClick={() => { add(selected); setSelected(null); }}><Plus size={16} />Add to basket</Button></div></Modal>}
    {checkout && cart.data && <Checkout cart={cart.data} addresses={addresses.data || []} onClose={() => setCheckout(false)} onDone={() => { setCheckout(false); cart.reload(); addresses.reload(); setTab('browse'); }} />}
  </div>;
}
