/* RouteNex Phase 6 UI: the student-friendly shop (search, categories, sorting, quantity limits and a live cart bar). */
(() => {
const LOOK = { 'Stationery': ['#6366f1', '#8b5cf6'], 'Books & Exam Prep': ['#0ea5e9', '#2563eb'], 'Electronics & Accessories': ['#0f766e', '#14b8a6'], 'Engineering & Lab': ['#9333ea', '#c026d3'],
  'Hostel & Room': ['#f97316', '#f59e0b'], 'Kitchen & Mess': ['#dc2626', '#f97316'], 'Groceries': ['#16a34a', '#65a30d'], 'Snacks & Drinks': ['#e11d48', '#fb7185'],
  'Personal Care & Health': ['#0891b2', '#06b6d4'], 'Cleaning & Laundry': ['#2563eb', '#38bdf8'], 'Bags & Travel': ['#7c3aed', '#a78bfa'], 'Art & Craft': ['#db2777', '#f472b6'],
  'Sports & Fitness': ['#ea580c', '#facc15'], 'Print & Copy': ['#475569', '#64748b'] };
const FALLBACK = ['#5548e7', '#786cff'], MAX_PER_ITEM = 50;
const SORTS = { featured: 'Featured', low: 'Price: low to high', high: 'Price: high to low', az: 'Name: A to Z' };
let all = [], view = { q: '', cat: 'All', sort: 'featured' };

/* pure helper (also used by the tests): every typed word must appear in the name, description or category */
function filterItems(items, { q = '', cat = 'All', sort = 'featured' } = {}) {
  const words = String(q).toLowerCase().split(/\s+/).filter(Boolean);
  let out = items.map((x, i) => ({ x, i })).filter(({ x }) => (cat === 'All' || x.category === cat) &&
    words.every(w => (x.name + ' ' + x.description + ' ' + x.category).toLowerCase().includes(w)));
  if (sort === 'low') out.sort((a, b) => a.x.price - b.x.price || a.i - b.i);
  else if (sort === 'high') out.sort((a, b) => b.x.price - a.x.price || a.i - b.i);
  else if (sort === 'az') out.sort((a, b) => a.x.name.localeCompare(b.x.name) || a.i - b.i);
  return out.map(o => o.x);
}
const maxFor = id => { const x = all.find(i => i.id === +id); return Math.min(MAX_PER_ITEM, x ? x.stock : MAX_PER_ITEM); };
function saveCart() { localStorage.setItem('rn_cart', JSON.stringify(cart)); }
/* forget cart lines whose item no longer exists (for example items from the old catalogue) so checkout never fails with "Item not available" */
async function pruneCart() {
  const items = await api('/items'), ok = new Set(items.map(i => i.id)); let changed = false;
  Object.keys(cart).forEach(k => { if (!ok.has(+k)) { delete cart[k]; changed = true; } });
  if (changed) saveCart(); return items;
}
function cartTotals() { let n = 0, sum = 0; all.forEach(x => { const q = cart[x.id] || 0; n += q; sum += q * x.price; }); return { n, sum }; }
function updateBar() {
  const b = document.getElementById('cartBar'); if (!b) return; const t = cartTotals();
  b.classList.toggle('hidden', !t.n);
  b.innerHTML = t.n ? `<span><b>${t.n}</b> item${t.n > 1 ? 's' : ''} in cart · <b>${money(t.sum)}</b></span><button data-p6="cart">View cart →</button>` : '';
}
window.changeCart = (id, d) => {                       // replaces the old handler: respects stock and the 50-per-item limit
  const cur = cart[id] || 0, cap = maxFor(id), next = Math.max(0, Math.min(cap, cur + d));
  if (d > 0 && next === cur) { toast(cap ? `Only ${cap} available` : 'Out of stock', true); return; }
  if (next) cart[id] = next; else delete cart[id];
  saveCart(); const q = document.getElementById('q' + id); if (q) q.textContent = cart[id] || 0; updateBar();
};

function card(x) {
  const [a, b] = LOOK[x.category] || FALLBACK, q = cart[x.id] || 0, out = x.stock <= 0;
  return `<div class="card item shopcard"><div class="shop-banner" style="background:linear-gradient(135deg,${a},${b})"><span class="shop-emoji">${esc(x.icon)}</span><small>${esc(x.category)}</small></div>
  <h3>${esc(x.name)}</h3><p class="muted">${esc(x.description)}</p>
  <div class="price">${money(x.price)}</div>
  <div class="quantity"><button data-act="changeCart" data-id="${x.id}" data-d="-1" aria-label="Remove one">−</button><b id="q${x.id}">${q}</b><button data-act="changeCart" data-id="${x.id}" data-d="1" aria-label="Add one" ${out ? 'disabled' : ''}>+</button>
  ${out ? '<small class="stock-out">Out of stock</small>' : x.stock <= 5 ? `<small class="stock-low">Only ${x.stock} left</small>` : `<small class="muted">${x.stock} available</small>`}</div></div>`;
}
function paintGrid() {
  const list = filterItems(all, view), g = document.getElementById('shopGrid'); if (!g) return;
  g.innerHTML = list.length ? list.map(card).join('') : '<div class="empty" style="grid-column:1/-1">No items match. <button class="btn-sm outline" data-p6="reset">Clear filters</button></div>';
  const n = document.getElementById('shopCount'); if (n) n.textContent = `${list.length} item${list.length === 1 ? '' : 's'}`;
  document.querySelectorAll('#shopChips button').forEach(b => b.classList.toggle('on', b.dataset.cat === view.cat));
}
async function shopPage(c) {
  all = await pruneCart(); const cats = [...new Set(all.map(i => i.category))]; view = { q: '', cat: 'All', sort: 'featured' };
  $('#pageTitle').textContent = 'Shop'; $('#subtitle').textContent = 'Student essentials, groceries and more, delivered by our fleet';
  c.innerHTML = `<div class="card shop-tools"><div class="toolbar"><input id="shopQ" class="search" type="search" placeholder="Search notebooks, calculator, rice, charger…" maxlength="60" autocomplete="off">
    <select id="shopSort" aria-label="Sort items">${Object.entries(SORTS).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select><span id="shopCount" class="pill"></span></div>
    <div id="shopChips" class="filters"><button data-cat="All" class="on">All</button>${cats.map(k => `<button data-cat="${esc(k)}">${esc(k)}</button>`).join('')}</div></div>
    <div id="shopGrid" class="grid items" style="margin-top:18px"></div><div id="cartBar" class="cartbar hidden"></div>`;
  $('#shopQ').oninput = e => { view.q = e.target.value; paintGrid(); };
  $('#shopSort').onchange = e => { view.sort = e.target.value; paintGrid(); };
  $('#shopChips').onclick = e => { const b = e.target.closest('button[data-cat]'); if (!b) return; view.cat = b.dataset.cat; paintGrid(); };
  paintGrid(); updateBar();
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-p6]'); if (!b) return;
  if (b.dataset.p6 === 'cart') navigate('cart');
  if (b.dataset.p6 === 'reset') { view = { q: '', cat: 'All', sort: 'featured' }; const q = $('#shopQ'); if (q) q.value = ''; const s = $('#shopSort'); if (s) s.value = 'featured'; paintGrid(); }
});

const _r = render;
render = async function () {
  const role = session.user.role;
  if (role === 'customer' && page === 'shop') { window.rnStopTimers && window.rnStopTimers(); return shopPage($('#content')); }
  if (role === 'customer' && page === 'cart') { try { await pruneCart(); } catch (e) {} }
  return _r();
};
window.__rnShop = { filterItems };
})();
