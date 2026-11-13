import React, { useEffect, useState } from 'react';
import { LoaderCircle, X, AlertCircle, Inbox } from 'lucide-react';
import { titleCase } from '../api';

export function Button({ children, variant = 'primary', loading, className = '', ...props }) {
  return <button className={`btn ${variant} ${className}`} disabled={loading || props.disabled} {...props}>{loading && <LoaderCircle size={16} className="spin" />}{children}</button>;
}
export function Card({ title, action, children, className = '' }) {
  return <section className={`card ${className}`}>{(title || action) && <header className="card-head"><h3>{title}</h3>{action}</header>}{children}</section>;
}
export function Badge({ value }) {
  const v = String(value || '');
  const tone = ['completed','delivered','paid','captured','available','online','processed','active'].includes(v) ? 'good'
    : ['cancelled','failed','breakdown','expired','refunded'].includes(v) ? 'bad'
    : ['pending','awaiting_payment','searching','planned','maintenance','created','queued'].includes(v) ? 'warn' : 'neutral';
  return <span className={`badge ${tone}`}>{titleCase(v)}</span>;
}
export function Field({ label, hint, children }) {
  return <label className="field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>;
}
export function Modal({ title, children, onClose, wide = false }) {
  useEffect(() => { const h = e => e.key === 'Escape' && onClose(); window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, [onClose]);
  return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}><div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}><header><h2>{title}</h2><button className="icon-btn" onClick={onClose} aria-label="Close"><X size={20} /></button></header><div className="modal-body">{children}</div></div></div>;
}
export function Empty({ title = 'Nothing here yet', text = 'New activity will appear here.', icon: Icon = Inbox }) {
  return <div className="empty"><Icon size={34} /><h3>{title}</h3><p>{text}</p></div>;
}
export function ErrorBox({ error }) { return error ? <div className="error-box"><AlertCircle size={17} />{error.message || String(error)}</div> : null; }
export function Loading() { return <div className="loading"><LoaderCircle className="spin" /> Loading…</div>; }
export function Stat({ label, value, note, icon: Icon }) {
  return <div className="stat">{Icon && <div className="stat-icon"><Icon size={20} /></div>}<div><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</div></div>;
}
export function Table({ columns, rows, render, empty = 'No records found' }) {
  if (!rows?.length) return <Empty title={empty} text="Try a different filter or check back later." />;
  return <div className="table-wrap"><table><thead><tr>{columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={r.id || r.session_id || i}>{render(r)}</tr>)}</tbody></table></div>;
}
export function useAsync(fn, deps = []) {
  const [data, setData] = useState(null), [error, setError] = useState(null), [loading, setLoading] = useState(true);
  const reload = React.useCallback(async () => { setLoading(true); setError(null); try { setData(await fn()); } catch (e) { setError(e); } finally { setLoading(false); } }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload, setData };
}
export function Tabs({ tabs, active, onChange }) {
  return <div className="tabs" role="tablist">{tabs.map(t => <button key={t.id} role="tab" aria-selected={active === t.id} className={active === t.id ? 'active' : ''} onClick={() => onChange(t.id)}>{t.label}{t.count !== undefined && <span className="tab-count">{t.count}</span>}</button>)}</div>;
}
