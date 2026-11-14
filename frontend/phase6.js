/* RouteNex Phase 6 UI: the student-friendly shop (search, categories, sorting, quantity limits and a live cart bar). */
(() => {
// Illustrative demo images are keyed by catalogue name, not database IDs, so existing
// installations need no migration. A valid merchant-supplied image always wins.
const DEMO_IMAGES = Object.freeze({
  'Ruled Notebook, A4 (200 pages)': 'ruled-notebook.jpg',
  'Notebook Pack, Single Line (set of 6)': 'notebook-pack.jpg',
  'Spiral Notebook, 5 Subject (300 pages)': 'spiral-notebook.jpg',
  'Ball Pens, Blue (pack of 10)': 'blue-ball-pens.jpg',
  'Gel Pens, Assorted (pack of 12)': 'gel-pens.jpg',
  'Pencils HB with Eraser & Sharpener (set of 10)': 'pencils-set.jpg',
  'Geometry Box (full set)': 'geometry-box.jpg',
  'Highlighters (pack of 5)': 'highlighters.jpg',
  'Class 10 CBSE Sample Papers': 'cbse-papers.jpg',
  'Class 12 Physics Practice Workbook': 'physics-workbook.jpg'
});
const MAX_PER_ITEM = 50;
const localImage = url => typeof url === 'string' && /^\/static\/product-images\/[a-zA-Z0-9._-]+$/.test(url);
function imageFor(x) {
  if (localImage(x.image_url)) return { url: x.image_url, illustrative: false };
  const filename = Object.prototype.hasOwnProperty.call(DEMO_IMAGES, x.name) ? DEMO_IMAGES[x.name] : null;
  return filename ? { url: '/static/product-images/' + filename, illustrative: true } : null;
}
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
  const image = imageFor(x), q = cart[x.id] || 0, out = x.stock <= 0;
  return `<div class="card item shopcard"><div class="shop-banner">
  <div class="shop-fallback" ${image ? 'aria-hidden="true"' : ''}><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="8.5" cy="9" r="1.5"/><path d="m4 18 5-5 3 3 3-3 5 5"/></svg><span>Photo coming soon</span></div>
  ${image ? `<img class="shop-photo" src="${esc(image.url)}" alt="" loading="lazy" decoding="async">${image.illustrative ? '<span class="shop-illustrative">AI illustration</span>' : ''}` : ''}<small>${esc(x.category)}</small></div>
  <h3>${esc(x.name)}</h3><p class="muted">${esc(x.description)}</p>
  <div class="price">${money(x.price)}</div>
  <div class="quantity"><button data-act="changeCart" data-id="${x.id}" data-d="-1" aria-label="Remove one ${esc(x.name)}">−</button><b id="q${x.id}">${q}</b><button data-act="changeCart" data-id="${x.id}" data-d="1" aria-label="Add one ${esc(x.name)}" ${out ? 'disabled' : ''}>+</button>
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
  // Image errors do not bubble. Capture them so an unavailable merchant photo
  // reveals the accessible, styled fallback rather than a broken-image icon.
  $('#shopGrid').addEventListener('error', e => {
    if (!e.target.classList.contains('shop-photo')) return;
    const banner = e.target.closest('.shop-banner');
    e.target.remove(); banner.querySelector('.shop-illustrative')?.remove();
    banner.querySelector('.shop-fallback').removeAttribute('aria-hidden');
  }, true);
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
window.__rnShop = { filterItems, imageFor };
})();
