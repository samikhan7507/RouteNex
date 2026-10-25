/* RouteNex Phase 5 UI: floating assistant (chat, suggestion chips, confirm cards, voice input). */
(() => {
const S = { open: false, history: [], busy: false, provider: '', mounted: false }, A = {};
let rec = null;
const fmt = t => esc(t).replace(/\n/g, '<br>');
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
window.addEventListener('rn:logout', () => {            // never show or send the previous user's chat to the next person
  S.open = false; S.history = []; S.started = false; S.busy = false; S.provider = '';
  const p = document.getElementById('aiPanel'); if (!p) return;
  p.classList.add('hidden'); document.getElementById('aiMsgs').innerHTML = ''; document.getElementById('aiChips').innerHTML = ''; document.getElementById('aiProv').textContent = 'starting…';
});

function mount() {
  if (S.mounted) return; S.mounted = true;
  document.body.insertAdjacentHTML('beforeend', `<button id="aiFab" class="ai-fab hidden" aria-label="Open assistant" data-p5="toggle">💬</button>
  <section id="aiPanel" class="ai-panel hidden" aria-label="RouteNex assistant"><header class="ai-head"><div><b>RouteNex Assistant</b><small id="aiProv">starting…</small></div><button class="ai-x" data-p5="toggle" aria-label="Close">✕</button></header>
  <div id="aiMsgs" class="ai-msgs"></div><div id="aiChips" class="ai-chips"></div>
  <div class="ai-input">${SR ? '<button id="aiMic" class="ai-mic" data-p5="mic" aria-label="Speak">🎤</button>' : ''}<input id="aiText" maxlength="500" placeholder="Ask or tell me what you need…" autocomplete="off"><button id="aiSend" data-p5="send">Send</button></div></section>`);
  $('#aiText').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); A.send(); } });
  setInterval(() => { const on = typeof session !== 'undefined' && session; $('#aiFab').classList.toggle('hidden', !on || S.open); if (!on && S.open) toggle(false); }, 1200);
}
async function toggle(force) {
  S.open = force !== undefined ? force : !S.open; $('#aiPanel').classList.toggle('hidden', !S.open); $('#aiFab').classList.toggle('hidden', S.open);
  if (S.open && !S.history.length && !S.started) { S.started = true;
    try { const st = await api('/assistant/status'); S.provider = st.provider; $('#aiProv').textContent = st.provider === 'offline' ? 'built-in engine' : st.provider; $('#aiProv').title = st.note;
      bot(`Hi ${session.user.name.split(' ')[0]}! I can look things up, give prices and, with your OK, book or cancel. ${st.note}`); chips(st.suggestions); } catch (e) { bot('Assistant is unavailable right now.'); } }
  if (S.open) setTimeout(() => $('#aiText').focus(), 80);
}
function chips(list) { $('#aiChips').innerHTML = (list || []).slice(0, 4).map(t => `<button class="ai-chip" data-p5="chip" data-t="${esc(t)}">${esc(t)}</button>`).join(''); }
function add(html, cls) { const m = $('#aiMsgs'); m.insertAdjacentHTML('beforeend', `<div class="ai-msg ${cls}">${html}</div>`); m.scrollTop = m.scrollHeight; }
const bot = (t, extra = '') => add(fmt(t) + extra, 'bot');
function cardsHtml(cards) {
  return (cards || []).map(c => `<div class="ai-card">${c.title ? `<b>${esc(c.title)}</b>` : ''}${(c.rows || []).map(r => `<div class="ai-row"><span>${esc(r[0])}</span><b>${esc(r[1])}</b></div>`).join('')}${(c.buttons || []).map(b => `<button class="btn-sm" data-p2="track" data-id="${+b.id}">${esc(b.label)}</button>`).join('')}</div>`).join('');
}
function actionsHtml(acts) {
  return (acts || []).map(a => `<div class="ai-action" id="act${a.id}"><p>${esc(a.summary)}</p><div class="ai-btns"><button class="btn-sm" data-p5="confirm" data-id="${a.id}">Confirm</button><button class="btn-sm outline" data-p5="dismiss" data-id="${a.id}">Not now</button></div></div>`).join('');
}
async function ask(text) {
  if (S.busy || !text.trim()) return; S.busy = true; $('#aiChips').innerHTML = '';
  add(esc(text), 'me'); S.history.push({ role: 'user', text }); $('#aiText').value = '';
  add('<span class="dots"><i></i><i></i><i></i></span>', 'bot typing');
  try { const r = await api('/assistant/chat', { method: 'POST', body: JSON.stringify({ message: text, history: S.history.slice(-8, -1) }) });
    document.querySelector('.typing')?.remove(); S.history.push({ role: 'assistant', text: r.reply }); if (r.provider) { $('#aiProv').textContent = r.provider === 'offline' ? 'built-in engine' : r.provider; }
    bot(r.reply, cardsHtml(r.cards) + actionsHtml(r.actions) + (r.note ? `<div class="ai-note">${esc(r.note)}</div>` : '')); }
  catch (e) { document.querySelector('.typing')?.remove(); bot(e.message || 'Something went wrong.'); }
  S.busy = false;
}
A.toggle = () => toggle();
A.send = () => ask($('#aiText').value);
A.chip = b => ask(b.dataset.t);
A.confirm = async b => {
  const box = document.getElementById('act' + b.dataset.id); box.querySelectorAll('button').forEach(x => x.disabled = true);
  try { const r = await api('/assistant/confirm', { method: 'POST', body: JSON.stringify({ id: +b.dataset.id }) }); box.remove(); bot(r.reply, cardsHtml(r.cards)); S.history.push({ role: 'assistant', text: r.reply });
    if (r.ok && typeof page !== 'undefined' && ['trips', 'overview', 'wallet', 'optimizer', 'route'].includes(page)) navigate(page); }
  catch (e) { box.remove(); bot(e.message); }
};
A.dismiss = async b => { try { const r = await api('/assistant/dismiss', { method: 'POST', body: JSON.stringify({ id: +b.dataset.id }) }); document.getElementById('act' + b.dataset.id)?.remove(); bot(r.reply); } catch (e) { toast(e.message, true); } };
A.mic = b => {
  if (!SR) return; if (rec) { rec.stop(); return; }
  rec = new SR(); rec.lang = 'en-IN'; rec.interimResults = false; b.classList.add('on');
  rec.onresult = e => { $('#aiText').value = e.results[0][0].transcript; ask($('#aiText').value); };
  rec.onerror = () => toast('Could not hear that. Check microphone permission.', true); rec.onend = () => { rec = null; b.classList.remove('on'); }; rec.start();
};
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-p5]'); if (b) { const fn = A[b.dataset.p5]; if (fn) { try { await fn(b); } catch (err) { toast(err.message, true); } } return; }
  if (e.target.closest('#aiPanel [data-p2]') && window.innerWidth < 900) toggle(false);          // "Track trip" etc: get out of the way on phones
});
const _r = render;
render = async function () { mount(); return _r(); };
if (typeof session !== 'undefined' && session) mount();
})();
