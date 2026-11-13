import React, { useState } from 'react';
import { Bot, Send, X } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../store';
import { Button } from './ui';

export default function Assistant({ onClose }) {
  const { user } = useApp();
  const [messages, setMessages] = useState([{ role: 'assistant', text: `Hello ${user.name.split(' ')[0]}. Ask for a summary${['admin','dispatcher','fleet_manager'].includes(user.role) ? ', say “plan routes”,' : ''} or “cancel order 12”. Actions always ask for confirmation.` }]);
  const [input, setInput] = useState(''), [busy, setBusy] = useState(false), [action, setAction] = useState(null);
  const send = async text => {
    if (!text.trim()) return;
    setMessages(m => [...m, { role: 'user', text }]); setInput(''); setBusy(true);
    try { const r = await api('/assistant/message', { method: 'POST', body: { message: text } }); setMessages(m => [...m, { role: 'assistant', text: r.reply }]); setAction(r.action); }
    catch (e) { setMessages(m => [...m, { role: 'assistant', text: e.message }]); }
    finally { setBusy(false); }
  };
  const confirm = async yes => {
    setBusy(true);
    try { const r = await api(yes ? '/assistant/confirm' : '/assistant/dismiss', { method: 'POST', body: { action_id: action.id } }); setMessages(m => [...m, { role: 'assistant', text: r.reply || 'Action dismissed.' }]); setAction(null); }
    catch (e) { setMessages(m => [...m, { role: 'assistant', text: e.message }]); }
    finally { setBusy(false); }
  };
  return <div className="assistant-panel" role="dialog" aria-label="RouteNex assistant">
    <header><Bot size={20} /><strong>RouteNex assistant</strong><button className="icon-btn" onClick={onClose}><X size={18} /></button></header>
    <div className="assistant-messages">{messages.map((m, i) => <div key={i} className={`msg ${m.role}`}>{m.text}</div>)}
      {action && <div className="confirm-box"><p>{action.summary}</p><div><Button variant="secondary" onClick={() => confirm(false)} disabled={busy}>Dismiss</Button><Button onClick={() => confirm(true)} loading={busy}>Confirm</Button></div></div>}
    </div>
    <form onSubmit={e => { e.preventDefault(); send(input); }}><input value={input} onChange={e => setInput(e.target.value)} placeholder="Ask about your account or operations…" aria-label="Assistant message" /><button className="icon-btn" disabled={busy}><Send size={18} /></button></form>
  </div>;
}
