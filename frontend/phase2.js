/* RouteNex Phase 2 UI: home, ride + parcel booking, live tracking, driver console, wallet, checkout.
   Loaded after app.js (shares its globals: api, esc, money, pill, toast, navigate, session, menu, render ...). */
(() => {
const TITLES = { overview: 'Home', rides: 'Book a Ride', parcel: 'Send a Parcel', cart: 'Cart & Checkout', trips: 'My Trips & Orders', wallet: 'Wallet & Offers', track: 'Live Trip', users: 'Users & Audit' };
const ICON = { bike: '🏍️', auto: '🛺', cab: '🚕', pbike: '🏍️', pmini: '🚐', pvan: '🚚' };
const TILE = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const ACTIVE = ['searching', 'matched', 'arriving', 'started'];
const when = t => t ? new Date(t * 1000).toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
const lt = s => s ? new Date(String(s).replace(' ', 'T') + 'Z').toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
const stext = (s, kind) => ({ searching: 'Finding you a driver…', matched: 'Driver is on the way', arriving: 'Driver has arrived', started: kind === 'parcel' ? 'Parcel is on the way' : 'Trip in progress', completed: kind === 'parcel' ? 'Delivered' : 'Trip completed', cancelled: 'Cancelled' })[s] || s;
let trackId = +sessionStorage.getItem('rn_track') || null, timers = [], rating = 0, jobId = null, applied = null;
const every = (fn, ms) => timers.push(setInterval(fn, ms)), stopAll = () => { timers.forEach(clearInterval); timers = []; };
const H = {}, A = {};
const byName = v => JAIPUR.find(x => x[0].toLowerCase() === String(v).trim().toLowerCase());

menu.customer = [['overview', 'Home', '⌂'], ['rides', 'Ride', '⌖'], ['parcel', 'Parcel', '▣'], ['shop', 'Shop', '◇'], ['cart', 'Cart', '▤'], ['trips', 'My Trips', '↺'], ['wallet', 'Wallet', '₹']];
menu.driver = [['overview', 'Driver Console', '◫'], ['trips', 'Earnings', '₹'], ['fleet', 'My Vehicle', '◆']];

/* ---------- map helpers ---------- */
function baseMap(id) {
  const n = document.getElementById(id); if (!n) return null;
  if (typeof L === 'undefined') { n.innerHTML = '<div class="empty">The map needs an internet connection.</div>'; return null; }
  n.innerHTML = ''; const m = L.map(id).setView([26.9124, 75.7873], 12);
  L.tileLayer(TILE, { maxZoom: 19, attribution: '© OpenStreetMap contributors' }).addTo(m); setTimeout(() => m.invalidateSize(), 150); return m;
}
const vIcon = ch => L.divIcon({ html: `<div class="veh">${ch}</div>`, className: 'veh-wrap', iconSize: [36, 36], iconAnchor: [18, 18] });
async function osrm(a, b) {
  try { const r = await fetch(`https://router.project-osrm.org/route/v1/driving/${a[1]},${a[0]};${b[1]},${b[0]}?overview=full&geometries=geojson`); const d = await r.json(); const rt = d.routes && d.routes[0];
    if (rt) return { km: rt.distance / 1000, min: Math.round(rt.duration / 60), pts: rt.geometry.coordinates.map(x => [x[1], x[0]]) }; } catch (e) {}
  return null;
}
function pointAt(pts, f) {
  if (!pts || pts.length < 2) return null; const seg = []; let tot = 0;
  for (let i = 1; i < pts.length; i++) { const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); seg.push(d); tot += d; }
  let t = f * tot, i = 0; while (i < seg.length - 1 && t > seg[i]) { t -= seg[i]; i++; }
  const k = seg[i] ? Math.min(1, t / seg[i]) : 0; return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k];
}
function liveMap(id) {  // pickup/drop pins, road route, and a vehicle that moves along the road using the server's progress
  const m = baseMap(id), S = { m, paths: {}, pk: null, dr: null, veh: null, line: null };
  async function path(key, a, b) { if (S.paths[key] !== undefined) return S.paths[key]; S.paths[key] = null; const r = await osrm(a, b); S.paths[key] = r ? r.pts : [a, b]; return S.paths[key]; }
  S.update = async s => {
    if (!m) return; const p = [s.pickup.lat, s.pickup.lng], d = [s.drop.lat, s.drop.lng];
    if (!S.pk) { S.pk = L.marker(p).addTo(m).bindPopup('Pickup: ' + esc(s.pickup.name)); S.dr = L.marker(d).addTo(m).bindPopup('Drop: ' + esc(s.drop.name));
      const tp = await path('trip', p, d); S.line = L.polyline(tp, { color: '#5548e7', weight: 6, opacity: .8 }).addTo(m); m.fitBounds(S.line.getBounds(), { padding: [40, 40] }); }
    const dv = s.driver;
    if (dv && dv.lat != null && s.status !== 'cancelled') {
      let pos = [dv.lat, dv.lng];
      if (s.phase === 'to_pickup' && s.approach_from) pos = pointAt(await path('appr', [s.approach_from.lat, s.approach_from.lng], p), s.progress) || pos;
      else if (s.phase === 'on_trip') pos = pointAt(S.paths.trip, s.progress) || pos;
      else if (s.phase === 'at_pickup') pos = p; else if (s.phase === 'done') pos = d;
      if (!S.veh) S.veh = L.marker(pos, { icon: vIcon(ICON[s.vehicle_class] || '🚕'), zIndexOffset: 900 }).addTo(m); else S.veh.setLatLng(pos);
    } else if (S.veh) { m.removeLayer(S.veh); S.veh = null; }
  };
  return S;
}

/* ---------- booking (rides + parcels share one screen) ---------- */
async function booking(c, kind) {
  const parcel = kind === 'parcel', [w, cps] = await Promise.all([api('/wallet'), api('/coupons')]);
  const st = { pickup: null, drop: null, route: null, routeKey: '', cls: null, est: null }, marks = {}; let seq = 0, nearLayer = null, deb = null;
  const places = JAIPUR.map(x => `<option value="${esc(x[0])}">`).join('');
  c.innerHTML = `<div class="ride-layout"><div class="card ride-search"><div class="sectionTitle"><h3>${parcel ? 'Send a parcel' : 'Book a ride'}</h3><span class="pill">Wallet ${money(w.balance)}</span></div>
  <div id="bk-active"></div><label>Pickup</label><input id="bk-pickup" list="places" placeholder="Search a Jaipur landmark"><label>${parcel ? 'Deliver to' : 'Drop'}</label><input id="bk-drop" list="places" placeholder="Where to?"><datalist id="places">${places}</datalist>
  <div class="map-mode"><button class="outline btn-sm" data-p2="mode" data-k="pickup">📍 Pickup on map</button><button class="outline btn-sm" data-p2="mode" data-k="drop">🏁 Drop on map</button></div>
  <button class="outline btn-sm" style="width:100%" data-p2="locate">◎ Use my current location as pickup</button>
  ${parcel ? `<div class="grid formGrid" style="margin-top:6px"><div><label>Weight (kg)</label><input id="pc-weight" type="number" min="0.1" max="900" step="0.1" value="2"></div><div><label>Size</label><select id="pc-size"><option value="small">Small (shoebox)</option><option value="medium">Medium (carton)</option><option value="large">Large (furniture)</option></select></div>
  <div class="wide"><label class="check"><input id="pc-fragile" type="checkbox" style="width:auto"> Fragile (+₹25)</label></div><div class="wide"><label>What are you sending?</label><input id="pc-desc" maxlength="120" placeholder="Documents, gift, books…"></div>
  <div><label>Recipient name</label><input id="pc-rname" maxlength="60"></div><div><label>Recipient phone</label><input id="pc-rphone" inputmode="numeric" maxlength="10" placeholder="10 digits"></div></div>` : ''}
  <div id="bk-wx" class="muted"></div><div id="bk-opts"><div class="empty">Choose pickup and drop to see prices.</div></div>
  <div class="grid formGrid"><div><label>Payment</label><select id="bk-pay"><option value="cash">Cash</option><option value="wallet">Wallet (${money(w.balance)})</option><option value="upi">UPI (demo)</option><option value="card">Card (demo)</option></select></div>
  <div><label>Coupon</label><input id="bk-coupon" placeholder="e.g. ${esc((cps.find(x => x.scope === 'all' || x.scope === (parcel ? 'parcel' : 'ride')) || { code: 'WELCOME50' }).code)}" style="text-transform:uppercase"></div></div>
  <div id="bk-msg" class="muted" style="min-height:20px;margin:6px 0"></div><button id="bk-book" style="width:100%" disabled data-p2="book">${parcel ? 'Book parcel pickup' : 'Book ride'}</button></div>
  <div class="card ride-map-card"><div class="sectionTitle"><h3>Route & nearby drivers</h3><span class="live"><i></i> Live</span></div><div id="bkMap" class="map real-map"></div></div></div>`;
  const m = baseMap('bkMap');
  if (!parcel) api('/rides').then(rs => { const a = rs.find(r => r.kind === 'ride' && ACTIVE.includes(r.status)); if (a) $('#bk-active').innerHTML = `<div class="notice">You already have an active ride (${esc(a.status)}). <button class="btn-sm" data-p2="track" data-id="${a.id}">Track or cancel it</button></div>`; }).catch(() => {});
  const payload = () => { const a = st.pickup, b = st.drop, o = { pickup: a.name, pickup_lat: a.lat, pickup_lng: a.lng, dropoff: b.name, drop_lat: b.lat, drop_lng: b.lng,
    route_distance_km: st.route ? st.route.distance_km : undefined, route_duration_min: st.route ? st.route.duration_min : undefined, payment_method: $('#bk-pay').value, coupon: $('#bk-coupon').value.trim().toUpperCase() || undefined };
    if (parcel) { Object.assign(o, { weight_kg: +$('#pc-weight').value || 1, size: $('#pc-size').value, fragile: $('#pc-fragile').checked, description: $('#pc-desc').value, recipient_name: $('#pc-rname').value, recipient_phone: $('#pc-rphone').value }); if (st.cls) o.vehicle_class = st.cls; }
    else o.vehicle_class = st.cls || 'cab'; return o; };
  function setPoint(k, p, name) {
    st[k] = { lat: p[0], lng: p[1], name }; $('#bk-' + k).value = name;
    if (m) { if (marks[k]) m.removeLayer(marks[k]); marks[k] = L.marker(p, { draggable: true }).addTo(m); marks[k].on('dragend', e => { const z = e.target.getLatLng(); setPoint(k, [z.lat, z.lng], 'Pinned location'); }); }
    refresh();
  }
  let mode = 'pickup'; if (m) m.on('click', e => setPoint(mode, [e.latlng.lat, e.latlng.lng], `Map point ${e.latlng.lat.toFixed(4)}, ${e.latlng.lng.toFixed(4)}`));
  async function nearby() {
    if (!st.pickup || !m) return; try { const cls = st.cls || (parcel ? 'pbike' : 'cab'); const ds = await api(`/drivers/nearby?lat=${st.pickup.lat}&lng=${st.pickup.lng}&cls=${cls}`);
      if (nearLayer) m.removeLayer(nearLayer); nearLayer = L.layerGroup(ds.map(d => L.marker([d.lat, d.lng], { icon: vIcon(ICON[cls]) }).bindPopup(`${d.eta_min} min away`))).addTo(m); } catch (e) {}
  }
  function paint(x) {
    $('#bk-wx').innerHTML = (x.weather && x.weather.rain ? '🌧 Rain in Jaipur right now, trips may take a little longer. ' : '') + (x.eta_source === 'ml' ? '<span class="pill">AI ETA</span>' : '');
    $('#bk-opts').innerHTML = x.options.map(o => `<div class="opt ${o.vehicle_class === st.cls ? 'sel' : ''}" data-p2="pick" data-c="${esc(o.vehicle_class)}"><div class="opt-ico">${ICON[o.vehicle_class]}</div>
      <div class="opt-main"><b>${esc(o.label)}</b>${o.surge > 1 ? ` <span class="pill status-medium">${o.surge}x demand</span>` : ''}<br><small class="muted">${esc(o.note)} · ${o.eta_min} min trip · ${o.pickup_eta_min != null ? `${o.pickup_eta_min} min away` : 'no driver online'}</small>${o.factors && o.factors.length ? `<br><small class="eta-why">⏱ ${o.factors.map(esc).join(' · ')}</small>` : ''}</div>
      <div class="opt-price"><b>${money(o.fare)}</b></div></div>`).join('');
    const sel = x.options.find(o => o.vehicle_class === st.cls) || x.options[0];
    $('#bk-msg').innerHTML = x.coupon_error ? `<span style="color:#c51f49">${esc(x.coupon_error)}</span>` : (x.discount ? `<span style="color:#087a5d">Coupon applied: you save ${money(x.discount)} · pay <b>${money(x.payable)}</b></span>` : `${x.distance_km} km · pay <b>${money(x.payable)}</b>`);
    $('#bk-book').disabled = false; $('#bk-book').textContent = `${parcel ? 'Book parcel' : 'Book ' + sel.label} · ${money(x.payable)}`;
  }
  async function refresh() {
    if (!st.pickup || !st.drop) return; const my = ++seq; $('#bk-book').disabled = true;
    const key = `${st.pickup.lat},${st.pickup.lng};${st.drop.lat},${st.drop.lng}`;
    if (st.routeKey !== key) { const r = await osrm([st.pickup.lat, st.pickup.lng], [st.drop.lat, st.drop.lng]); if (my !== seq) return; st.routeKey = key;
      st.route = r ? { distance_km: +r.km.toFixed(2), duration_min: r.min, pts: r.pts } : null;
      if (m) { if (marks.route) m.removeLayer(marks.route); marks.route = L.polyline(st.route ? st.route.pts : [[st.pickup.lat, st.pickup.lng], [st.drop.lat, st.drop.lng]], { color: '#5548e7', weight: 6 }).addTo(m); m.fitBounds(marks.route.getBounds(), { padding: [40, 40] }); } }
    try { const x = await api(parcel ? '/parcels/estimate' : '/rides/estimate', { method: 'POST', body: JSON.stringify(payload()) }); if (my !== seq) return;
      st.est = x; if (!st.cls || !x.options.find(o => o.vehicle_class === st.cls)) st.cls = x.options[0].vehicle_class; paint(x); nearby(); }
    catch (e) { $('#bk-opts').innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }
  const later = () => { clearTimeout(deb); deb = setTimeout(refresh, 450); };
  ['#bk-coupon', '#bk-pay', '#pc-weight', '#pc-size', '#pc-fragile'].forEach(q => { const n = $(q); if (n) { n.onchange = later; if (n.tagName === 'INPUT' && n.type !== 'checkbox') n.oninput = later; } });
  ['pickup', 'drop'].forEach(k => $('#bk-' + k).onchange = () => { const z = byName($('#bk-' + k).value); if (z) setPoint(k, [z[1], z[2]], z[0]); else toast('Pick a suggested landmark or tap the map', true); });
  A.mode = b => { mode = b.dataset.k; toast(mode === 'pickup' ? 'Tap the map to set pickup' : 'Tap the map to set drop'); };
  A.locate = () => navigator.geolocation ? navigator.geolocation.getCurrentPosition(p => { setPoint('pickup', [p.coords.latitude, p.coords.longitude], 'My location'); m && m.setView([p.coords.latitude, p.coords.longitude], 14); }, () => toast('Location permission denied', true), { enableHighAccuracy: true, timeout: 10000 }) : toast('Location not supported', true);
  A.pick = b => { st.cls = b.dataset.c; if (st.est) paint(st.est); refresh(); };
  A.book = async () => { const btn = $('#bk-book'); btn.disabled = true; btn.textContent = 'Booking…';
    try { const x = await api(parcel ? '/parcels' : '/rides', { method: 'POST', body: JSON.stringify(payload()) }); trackId = x.id; sessionStorage.setItem('rn_track', x.id); toast(x.status === 'matched' ? `Driver ${x.driver.name} is on the way` : 'Looking for a driver…'); navigate('track'); }
    catch (e) { toast(e.message, true); btn.disabled = false; refresh(); } };
  setPoint('pickup', [JAIPUR[0][1], JAIPUR[0][2]], JAIPUR[0][0]); setPoint('drop', [JAIPUR[1][1], JAIPUR[1][2]], JAIPUR[1][0]);
}
H['customer:rides'] = c => booking(c, 'ride');
H['customer:parcel'] = c => booking(c, 'parcel');

/* ---------- live tracking (customer) ---------- */
const STEPS = ['booked', 'matched', 'arriving', 'started', 'completed'], STEP_LABEL = { booked: 'Booked', matched: 'Driver assigned', arriving: 'Driver arrived', started: 'On the way', completed: 'Done' };
function paintTrack(s) {
  const parcel = s.kind === 'parcel', reached = new Set(s.timeline.map(t => t.status)), dv = s.driver;
  const stars = n => '★'.repeat(n) + '☆'.repeat(5 - n);
  $('#trPanel').innerHTML = `<div class="trk-head"><div class="opt-ico">${ICON[s.vehicle_class] || '🚕'}</div><div><h3 style="margin:0">${esc(stext(s.status, s.kind))}</h3>
    <small class="muted">${s.status === 'matched' || s.status === 'started' ? `Arriving in about <b>${s.eta_min} min</b>` : s.status === 'searching' ? 'Matching the nearest driver…' : esc(s.pickup.name) + ' → ' + esc(s.drop.name)}</small></div>${pill(s.status)}</div>
    <div class="steps">${STEPS.map(k => `<div class="stp ${reached.has(k) ? 'on' : ''}"><i></i><span>${STEP_LABEL[k]}</span></div>`).join('')}</div>
    ${s.otp ? `<div class="otp"><small>Share this OTP with the driver at pickup</small><strong>${esc(s.otp)}</strong></div>` : ''}
    ${s.delivery_otp ? `<div class="otp alt"><small>Recipient gives this OTP to the driver at delivery</small><strong>${esc(s.delivery_otp)}</strong></div>` : ''}
    ${dv ? `<div class="drv"><div class="avatar">${esc(dv.name[0])}</div><div style="flex:1"><b>${esc(dv.name)}</b> · ★ ${Number(dv.rating).toFixed(1)}<br><small class="muted">${esc(dv.vehicle_type || '')} · ${esc(dv.plate || '')}</small></div>${s.can_cancel || s.status === 'started' ? `<a class="callbtn" href="tel:${esc(dv.phone || '')}">📞 Call</a>` : ''}</div>` : ''}
    <div class="sum"><p><span>${parcel ? 'Parcel' : 'Distance'}</span><b>${parcel ? esc(s.parcel.weight_kg) + ' kg · ' + esc(s.parcel.size) + (s.parcel.fragile ? ' · fragile' : '') : s.distance_km + ' km'}</b></p>
      ${parcel ? `<p><span>Recipient</span><b>${esc(s.parcel.recipient_name)}</b></p>` : ''}<p><span>Fare</span><b>${money(s.fare)}</b></p>${s.discount ? `<p><span>Coupon ${esc(s.coupon || '')}</span><b style="color:#087a5d">−${money(s.discount)}</b></p>` : ''}
      <p><span>You pay</span><b>${money(s.payable)}</b></p><p><span>Payment</span><b>${esc(s.payment_method)} · ${esc(s.payment_status)}</b></p>${s.surge > 1 ? `<p><span>Demand</span><b>${s.surge}x</b></p>` : ''}</div>
    ${s.can_cancel ? `<button class="danger" style="width:100%" data-p2="cancel">Cancel ${parcel ? 'parcel' : 'ride'}</button>` : ''}
    ${s.status === 'cancelled' ? `<div class="empty">${esc(s.cancel_reason || 'Cancelled')}${s.payment_status === 'refunded' ? '<br>Refund sent to your RouteNex wallet.' : ''}</div>` : ''}
    ${s.status === 'completed' ? (s.rating ? `<div class="empty">You rated this trip <b class="stars">${stars(s.rating)}</b></div>` : `<div class="rate"><h3>Rate your ${parcel ? 'delivery' : 'ride'}</h3><div class="starrow">${[1, 2, 3, 4, 5].map(n => `<button class="star ${rating >= n ? 'on' : ''}" data-p2="star" data-v="${n}">★</button>`).join('')}</div><input id="rv" placeholder="Add a comment (optional)" maxlength="300"><button style="width:100%;margin-top:10px" data-p2="rate">Submit rating</button></div>`) : ''}
    ${s.demo && ACTIVE.includes(s.status) ? '<p class="muted" style="text-align:center;margin-top:12px"><small>Demo mode: the driver is simulated</small></p>' : ''}`;
}
H.track = async c => {
  if (!trackId) return H['customer:trips'](c);
  c.innerHTML = '<div class="track-layout"><div class="card ride-map-card"><div id="trMap" class="map real-map"></div></div><div class="card" id="trPanel"><div class="loading-state">Loading trip…</div></div></div>';
  const lm = liveMap('trMap'); let last = null;
  let key = ''; const tick = async () => { try { const s = await api(`/rides/${trackId}/track`); last = s; lm.update(s); const k = [s.status, s.eta_min, s.driver && s.driver.id, s.rating].join('|'); if (k !== key) { key = k; paintTrack(s); } if (['completed', 'cancelled'].includes(s.status)) stopAll(); } catch (e) { $('#trPanel').innerHTML = `<div class="empty">${esc(e.message)}</div>`; stopAll(); } };
  await tick(); if (last && ACTIVE.includes(last.status)) every(tick, 2000);
};
A.cancel = async () => { if (!confirm('Cancel this trip?')) return; const r = await api(`/rides/${trackId}/cancel`, { method: 'POST', body: JSON.stringify({ reason: 'Changed my mind' }) });
  toast(r.refund > 0 ? `Cancelled. ${money(r.refund)} refunded to your wallet` : 'Trip cancelled'); navigate('track'); };
A.star = b => { rating = +b.dataset.v; document.querySelectorAll('.star').forEach(x => x.classList.toggle('on', +x.dataset.v <= rating)); };
A.rate = async () => { if (!rating) return toast('Tap a star first', true); await api(`/rides/${trackId}/rate`, { method: 'POST', body: JSON.stringify({ rating, review: $('#rv').value }) }); toast('Thanks for rating!'); rating = 0; navigate('track'); };
A.track = b => { trackId = +b.dataset.id; sessionStorage.setItem('rn_track', trackId); navigate('track'); };
A.go = b => navigate(b.dataset.page);

/* ---------- customer home / trips / wallet ---------- */
const tile = (page, ico, title, sub) => `<button class="tile" data-p2="go" data-page="${page}"><span class="tile-ico">${ico}</span><b>${title}</b><small>${sub}</small></button>`;
H['customer:overview'] = async c => {
  const [w, rs, os, cp] = await Promise.all([api('/wallet'), api('/rides'), api('/orders'), api('/coupons')]);
  const live = rs.filter(r => ACTIVE.includes(r.status));
  c.innerHTML = `<div class="hero card"><div><h2 style="margin:0">Hi ${esc(session.user.name.split(' ')[0])} 👋</h2><p class="muted" style="margin:4px 0 0">Where to today?</p></div><div class="walletchip" data-p2="go" data-page="wallet">₹ <b>${money(w.balance).slice(1)}</b><small>Wallet</small></div></div>
  <div class="tiles">${tile('rides', '🚕', 'Book a ride', 'Bike · Auto · Cab')}${tile('parcel', '📦', 'Send a parcel', 'Door to door in minutes')}${tile('shop', '🛍️', 'Shop & services', 'Delivered by our fleet')}</div>
  ${live.length ? `<div class="card" style="margin-top:18px"><h3>Happening now</h3>${live.map(r => `<div class="row"><span>${ICON[r.vehicle_class] || '🚕'} <b>${esc(r.pickup)}</b> → ${esc(r.dropoff)}</span>${pill(r.status)}<button class="btn-sm" data-p2="track" data-id="${r.id}">Track</button></div>`).join('')}</div>` : ''}
  <div class="grid two"><div class="card"><h3>Offers for you</h3>${cp.map(x => `<div class="offer"><b>${esc(x.code)}</b><br><small class="muted">${esc(x.title)}</small></div>`).join('')}</div>
  <div class="card"><h3>Recent activity</h3>${rs.slice(0, 3).map(r => `<div class="row"><span>${ICON[r.vehicle_class] || '🚕'} ${esc(r.pickup)} → ${esc(r.dropoff)}</span>${pill(r.status)}</div>`).join('') + os.slice(0, 2).map(o => `<div class="row"><span>🛍️ Order #${o.id}</span>${pill(o.status)}</div>`).join('') || '<div class="empty">Nothing yet. Book your first trip!</div>'}</div></div>`;
};
H['customer:trips'] = async c => {
  const [rs, os] = await Promise.all([api('/rides'), api('/orders')]);
  const all = [...rs.map(r => ({ t: r.kind === 'parcel' ? 'parcel' : 'ride', id: r.id, title: `${esc(r.pickup)} → ${esc(r.dropoff)}`, sub: `${r.kind === 'parcel' ? 'Parcel' : 'Ride'} #${r.id}`, amt: r.fare - (r.discount || 0), st: r.status, at: r.created_at })),
    ...os.map(o => ({ t: 'order', id: o.id, title: `Order #${o.id}`, sub: esc(o.delivery_window || ''), amt: o.total, st: o.status, at: o.created_at }))].sort((a, b) => String(b.at).localeCompare(String(a.at)));
  c.innerHTML = `<div class="card"><div class="toolbar"><input class="search" id="tq" placeholder="Search trips and orders"><div class="filters">${['all', 'ride', 'parcel', 'order'].map((f, i) => `<button class="${i ? '' : 'on'}" data-p2="filter" data-f="${f}">${({ all: 'All', ride: 'Rides', parcel: 'Parcels', order: 'Orders' })[f]}</button>`).join('')}</div></div><div id="tlist"></div></div>`;
  let f = 'all'; const draw = () => { const q = $('#tq').value.toLowerCase(), xs = all.filter(x => (f === 'all' || x.t === f) && (x.title + x.sub + x.st).toLowerCase().includes(q));
    $('#tlist').innerHTML = xs.length ? xs.map(x => `<div class="row"><span class="opt-ico sm">${{ ride: '🚕', parcel: '📦', order: '🛍️' }[x.t]}</span><span style="flex:1"><b>${x.title}</b><br><small class="muted">${x.sub} · ${esc(String(x.at || '').slice(0, 10))}</small></span><b>${money(x.amt)}</b>${pill(x.st)}
      ${x.t === 'order' ? (!['delivered', 'cancelled', 'failed', 'in_transit', 'picked_up'].includes(x.st) ? `<button class="btn-sm danger" data-act="cancelOrder" data-id="${x.id}">Cancel</button>` : '') : `<button class="btn-sm" data-p2="track" data-id="${x.id}">${ACTIVE.includes(x.st) ? 'Track' : 'Details'}</button>`}</div>`).join('') : '<div class="empty">No matching activity.</div>'; };
  $('#tq').oninput = draw; A.filter = b => { f = b.dataset.f; document.querySelectorAll('[data-p2=filter]').forEach(x => x.classList.toggle('on', x === b)); draw(); }; draw();
};
H['customer:orders'] = H['customer:history'] = H['customer:trips'];
H['customer:wallet'] = async c => {
  const [w, cp] = await Promise.all([api('/wallet'), api('/coupons')]);
  c.innerHTML = `<div class="grid two"><div class="card"><div class="walletbig"><small>Available balance</small><strong>${money(w.balance)}</strong></div><h3>Add money (demo UPI)</h3><div class="filters">${[100, 500, 1000].map(n => `<button data-p2="topup" data-n="${n}">+ ₹${n}</button>`).join('')}</div>
  <h3 style="margin-top:20px">Transactions</h3>${w.txns.length ? w.txns.map(t => `<div class="row"><span style="flex:1"><b>${esc(t.note || t.kind)}</b><br><small class="muted">${esc(lt(t.created_at))}</small></span><b style="color:${t.amount < 0 ? '#c51f49' : '#087a5d'}">${t.amount < 0 ? '−' : '+'}${money(Math.abs(t.amount))}</b></div>`).join('') : '<div class="empty">No transactions yet.</div>'}</div>
  <div class="card"><h3>Offers</h3>${cp.map(x => `<div class="offer"><b>${esc(x.code)}</b> <span class="pill">${esc(x.scope === 'all' ? 'rides, parcels & shop' : x.scope)}</span><br><small class="muted">${esc(x.title)}${x.min_amount ? ' · min ' + money(x.min_amount) : ''}</small></div>`).join('')}</div></div>`;
};
A.topup = async b => { const r = await api('/wallet/topup', { method: 'POST', body: JSON.stringify({ amount: +b.dataset.n }) }); toast(`Added. Balance ${money(r.balance)}`); navigate('wallet'); };

/* ---------- cart / checkout ---------- */
H['customer:cart'] = async c => {
  const [items, adds, w] = await Promise.all([api('/items'), api('/addresses'), api('/wallet')]);
  const chosen = items.filter(x => cart[x.id]), sub = chosen.reduce((s, x) => s + x.price * cart[x.id], 0); applied = null;
  c.innerHTML = `<div class="grid two"><div class="card"><div class="sectionTitle"><h3>Your cart</h3><span>${chosen.length} items</span></div>${chosen.length ? chosen.map(x => `<div class="row"><span>${esc(x.icon)} <b>${esc(x.name)}</b></span><span>${cart[x.id]} × ${money(x.price)}</span></div>`).join('') : '<div class="empty">Your cart is empty. Browse Shop to add services.</div>'}<hr>
  <p class="row"><span>Subtotal</span><b>${money(sub)}</b></p><p class="row" id="cdisc" style="display:none"><span>Discount</span><b style="color:#087a5d" id="cdv"></b></p><h2 class="row"><span>Total</span><span id="ctotal">${money(sub)}</span></h2></div>
  <div class="card"><h3>Delivery details</h3><label>Deliver to</label><select id="address">${adds.map(a => `<option value="${a.id}">${esc(a.label)} · ${esc(a.line1)}</option>`).join('') || '<option value="">Add an address below</option>'}</select>
  <details style="margin:10px 0"><summary class="muted" style="cursor:pointer">+ Add a new address</summary><label>Area</label><select id="na-area">${JAIPUR.map(x => `<option value="${esc(x[0])}">${esc(x[0])}</option>`).join('')}</select><label>Flat / street</label><input id="na-line" placeholder="House no., street"><label>Pincode</label><input id="na-pin" value="302001" maxlength="6" inputmode="numeric"><button class="outline" style="width:100%;margin-top:10px" data-p2="addr">Save address</button></details>
  <div class="grid formGrid"><div><label>Priority</label><select id="priority"><option value="1">Standard</option><option value="3">Priority</option><option value="5">Critical</option></select></div><div><label>Payment</label><select id="pay"><option value="cod">Cash on delivery</option><option value="wallet">Wallet (${money(w.balance)})</option><option value="upi">UPI (demo)</option><option value="card">Card (demo)</option></select></div></div>
  <label>Delivery window</label><input id="window" value="Today 18:00–21:00"><label>Coupon</label><div style="display:flex;gap:8px"><input id="coupon" placeholder="SHOP100" style="text-transform:uppercase"><button class="outline" data-p2="applyc" data-sub="${sub}">Apply</button></div><div id="cmsg" class="muted" style="min-height:20px"></div>
  <button style="width:100%;margin-top:12px" data-p2="place" ${chosen.length ? '' : 'disabled'}>Place order</button></div></div>`;
};
A.applyc = async b => { const code = $('#coupon').value.trim(); if (!code) return; const r = await api('/coupons/validate', { method: 'POST', body: JSON.stringify({ code, amount: +b.dataset.sub || 1, scope: 'shop' }) });
  applied = r.valid ? r.code : null; $('#cmsg').innerHTML = `<span style="color:${r.valid ? '#087a5d' : '#c51f49'}">${esc(r.message)}</span>`;
  $('#cdisc').style.display = r.valid ? 'flex' : 'none'; if (r.valid) { $('#cdv').textContent = '−' + money(r.discount); $('#ctotal').textContent = money(r.final); } else $('#ctotal').textContent = money(+b.dataset.sub); };
A.addr = async () => { const z = byName($('#na-area').value), line = $('#na-line').value.trim(); if (!line) return toast('Enter the flat / street', true);
  await api('/addresses', { method: 'POST', body: JSON.stringify({ label: z[0], line1: `${line}, ${z[0]}`, city: 'Jaipur', state: 'Rajasthan', pincode: $('#na-pin').value, lat: z[1], lng: z[2] }) }); toast('Address saved'); navigate('cart'); };
A.place = async b => { if (!$('#address').value) return toast('Add a delivery address first', true); b.disabled = true;
  try { const r = await api('/orders', { method: 'POST', body: JSON.stringify({ address_id: +$('#address').value, priority: +$('#priority').value, delivery_window: $('#window').value, payment_method: $('#pay').value, coupon: applied || ($('#coupon').value.trim().toUpperCase() || undefined),
      items: Object.entries(cart).map(([item_id, quantity]) => ({ item_id: +item_id, quantity })) }) }); cart = {}; localStorage.setItem('rn_cart', '{}'); toast(`Order #${r.id} placed · ${money(r.total)}`); navigate('trips'); }
  catch (e) { toast(e.message, true); b.disabled = false; } };

/* ---------- driver console ---------- */
H['driver:overview'] = async c => {
  const [e, j] = await Promise.all([api('/driver/earnings'), api('/driver/job')]);
  c.innerHTML = `<div class="hero card"><div><h2 style="margin:0">${j.online ? '🟢 You are online' : '⚪ You are offline'}</h2><p class="muted" style="margin:4px 0 0">★ ${Number(e.rating).toFixed(1)} · ${e.rating_count} ratings</p></div><button data-p2="online" data-on="${j.online ? 0 : 1}" class="${j.online ? 'outline' : ''}">${j.online ? 'Go offline' : 'Go online'}</button></div>
  <div class="grid kpis" style="margin-top:18px"><div class="card kpi"><label>Today</label><strong>${money(e.today.earnings)}</strong><span class="up">${e.today.trips} trips</span></div><div class="card kpi"><label>Last 7 days</label><strong>${money(e.week.earnings)}</strong><span class="up">${e.week.trips} trips</span></div><div class="card kpi"><label>All time</label><strong>${money(e.total.earnings)}</strong><span class="up">${e.total.trips} trips</span></div><div class="card kpi"><label>Status</label><strong style="font-size:20px">${j.job ? esc(j.job.status) : j.online ? 'Waiting' : 'Offline'}</strong><span class="up">${j.job ? 'Active job' : 'No active job'}</span></div></div>
  <div class="track-layout" style="margin-top:18px"><div class="card ride-map-card"><div id="trMap" class="map real-map"></div></div><div class="card" id="jobPanel"></div></div>`;
  let jkey = null; const lm = liveMap('trMap'), paint = d => { jobId = d.job ? d.job.id : null; if (d.job) lm.update(d.job); const k = d.job ? [d.job.id, d.job.status, d.job.payment_status].join('|') : String(d.online); if (k !== jkey) { jkey = k; $('#jobPanel').innerHTML = jobHtml(d); } };
  paint(j); if (j.job || j.online) every(async () => { try { const d = await api('/driver/job'); const was = jobId; paint(d); if (was && !d.job) { toast('Trip finished'); navigate('overview'); } } catch (x) {} }, 2500);
};
function jobHtml(d) {
  const s = d.job; if (!s) return `<div class="empty"><h3>${d.online ? 'Waiting for trip requests…' : 'You are offline'}</h3><p class="muted">${d.online ? 'You are matched automatically when a customer books near you. To test, book a ride or parcel from a customer account.' : 'Go online to receive trips.'}</p></div>`;
  const parcel = s.kind === 'parcel';
  return `<div class="trk-head"><div class="opt-ico">${ICON[s.vehicle_class] || '🚕'}</div><div><h3 style="margin:0">${parcel ? 'Parcel' : 'Ride'} #${s.id}</h3><small class="muted">You earn <b>${money(s.driver_earning)}</b></small></div>${pill(s.status)}</div>
  <div class="sum"><p><span>Pickup</span><b>${esc(s.pickup.name)}</b></p><p><span>Drop</span><b>${esc(s.drop.name)}</b></p><p><span>Customer</span><b>${esc(s.customer ? s.customer.name : '')}</b></p>${parcel ? `<p><span>Parcel</span><b>${esc(s.parcel.weight_kg)} kg · ${esc(s.parcel.size)}${s.parcel.fragile ? ' · fragile' : ''}</b></p><p><span>Recipient</span><b>${esc(s.parcel.recipient_name)} ${esc(s.parcel.recipient_phone)}</b></p>` : ''}<p><span>Collect</span><b>${s.payment_status === 'paid' ? 'Paid online' : 'Cash ' + money(s.payable)}</b></p></div>
  ${s.customer && s.customer.phone ? `<a class="callbtn" href="tel:${esc(s.customer.phone)}" style="display:block;text-align:center;margin-bottom:10px">📞 Call customer</a>` : ''}
  ${s.status === 'matched' ? `<button style="width:100%" data-p2="arrived">I have arrived at pickup</button>` : ''}
  ${s.status === 'arriving' ? `<label>Ask the customer for their 4-digit OTP</label><input id="dotp" inputmode="numeric" maxlength="4" placeholder="••••"><button style="width:100%;margin-top:10px" data-p2="start">Verify OTP & start</button>` : ''}
  ${s.status === 'started' ? (parcel ? `<label>Recipient's delivery OTP</label><input id="dotp" inputmode="numeric" maxlength="4" placeholder="••••"><button style="width:100%;margin-top:10px" data-p2="finish">Confirm delivery</button>` : `<button style="width:100%" data-p2="finish">Complete trip</button>`) : ''}
  ${s.demo ? '<p class="muted" style="text-align:center;margin-top:12px"><small>Demo autopilot may also move this trip along</small></p>' : ''}`;
}
const drv = (path, body) => api(`/rides/${jobId}/${path}`, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
A.online = async b => { await api('/driver/online', { method: 'POST', body: JSON.stringify({ online: b.dataset.on === '1' }) }); navigate('overview'); };
A.arrived = async () => { await drv('arrived'); toast('Marked as arrived'); navigate('overview'); };
A.start = async () => { await drv('start', { otp: $('#dotp').value }); toast('Trip started'); navigate('overview'); };
A.finish = async () => { const o = $('#dotp'); await drv('complete', o ? { otp: o.value } : undefined); toast('Completed. Earnings updated'); navigate('overview'); };
H['driver:trips'] = async c => {
  const e = await api('/driver/earnings');
  c.innerHTML = `<div class="card"><h3>Recent completed trips</h3>${e.recent.length ? `<div class="table-wrap"><table><thead><tr><th>#</th><th>Type</th><th>Route</th><th>Fare</th><th>You earned</th></tr></thead><tbody>${e.recent.map(r => `<tr><td>#${r.id}</td><td>${esc(r.kind)}</td><td>${esc(r.pickup)} → ${esc(r.dropoff)}</td><td>${money(r.fare)}</td><td><b>${money(r.earning)}</b></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No completed trips yet.</div>'}</div>`;
};

/* ---------- admin: users with activate / deactivate ---------- */
H['admin:users'] = async c => {
  const [us, au] = await Promise.all([api('/admin/users'), api('/audit')]);
  c.innerHTML = `<div class="grid two"><div class="card"><h3>Users & roles</h3><div class="table-wrap"><table><thead><tr><th>Name</th><th>Role</th><th>Contact</th><th>Access</th></tr></thead><tbody>${us.map(u => `<tr><td>${esc(u.name)}</td><td>${pill(u.role)}</td><td>${esc(u.email || u.phone)}</td><td>${u.id === session.user.id ? '<small class="muted">You</small>' : `<button class="btn-sm ${u.active ? 'danger' : ''}" data-p2="utoggle" data-id="${u.id}" data-on="${u.active ? 0 : 1}">${u.active ? 'Deactivate' : 'Activate'}</button>`}</td></tr>`).join('')}</tbody></table></div></div>
  <div class="card"><h3>Audit trail</h3>${au.map(x => `<p><b>${esc(x.action)}</b> ${esc(x.entity)} #${esc(x.entity_id)}<br><small class="muted">${esc(x.name || 'System')} · ${esc(x.created_at)}</small></p>`).join('')}</div></div>`;
};
A.utoggle = async b => { await api(`/admin/users/${b.dataset.id}/active`, { method: 'PATCH', body: JSON.stringify({ active: b.dataset.on === '1' }) }); toast('Access updated'); navigate('users'); };

/* ---------- wiring ---------- */
window.rnStopTimers = stopAll;
const _render = render;
render = async function () {
  stopAll(); const r = session.user.role, c = $('#content');
  if (TITLES[page] && (H[r + ':' + page] || H[page])) $('#pageTitle').textContent = r === 'driver' && page === 'overview' ? 'Driver Console' : r === 'driver' && page === 'trips' ? 'Earnings' : TITLES[page];
  const h = H[r + ':' + page] || (page === 'track' ? H.track : null);
  return h ? h(c) : _render();
};
document.addEventListener('click', async e => { const b = e.target.closest('[data-p2]'); if (!b) return; const fn = A[b.dataset.p2]; if (!fn) return;
  try { await fn(b); } catch (err) { toast(err.message, true); } });
})();
