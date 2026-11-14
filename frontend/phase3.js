/* RouteNex Phase 3 UI: route optimizer (preview / apply / before-vs-after) and the driver's delivery route. */
(() => {
const COLORS = ['#5548e7', '#08bda7', '#e43d65', '#f3a522', '#0ea5e9', '#8b5cf6', '#16a34a', '#f97316'];
const OPS = ['dispatcher', 'fleet_manager', 'admin'], H = {}, A = {};
let plan = null;
menu.driver = [['overview', 'Driver Console', '◫'], ['route', 'My Route', '⌖'], ['trips', 'Earnings', '₹'], ['fleet', 'My Vehicle', '◆']];

const MAPS = {};                                   // one Leaflet map per container id; Leaflet refuses a second map on the same element
function baseMap(id) {
  const n = document.getElementById(id); if (!n) return null;
  if (MAPS[id]) { try { MAPS[id].remove(); } catch (e) {} delete MAPS[id]; }
  if (typeof L === 'undefined') { n.innerHTML = '<div class="empty">The map needs an internet connection.</div>'; return null; }
  n.innerHTML = ''; const m = L.map(id).setView([26.9124, 75.7873], 12); MAPS[id] = m;
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap contributors' }).addTo(m); setTimeout(() => m.invalidateSize(), 150); return m;
}
const numIcon = (n, color) => L.divIcon({ html: `<div class="stopnum" style="background:${color}">${n}</div>`, className: '', iconSize: [26, 26], iconAnchor: [13, 13] });
const delta = (b, o, lowerIsBetter = true) => { const d = o - b; if (!d) return '<td>—</td>'; const good = lowerIsBetter ? d < 0 : d > 0; return `<td class="${good ? 'good' : 'bad'}">${d > 0 ? '+' : ''}${Number.isInteger(d) ? d : d.toFixed(1)}</td>`; };

/* ---------- optimizer ---------- */
H.optimizer = async c => {
  const ov = await api('/optimizer/overview'), pend = ov.pending, free = ov.vehicles;
  c.innerHTML = `<div class="grid kpis"><div class="card kpi"><label>Orders waiting</label><strong>${pend}</strong><span class="up">Ready to plan</span></div><div class="card kpi"><label>Vehicles available</label><strong>${free}</strong><span class="up">Delivery-ready, free driver</span></div>
  <div class="card kpi"><label>Method</label><strong style="font-size:20px">Capacity + time windows</strong><span class="up">Priority-aware VRP</span></div><div class="card kpi"><label>Safe to try</label><strong style="font-size:20px">Preview first</strong><span class="up">Nothing saved until you apply</span></div></div>
  <div class="grid two" style="margin-top:18px"><div class="card"><div class="sectionTitle"><h3>Plan routes</h3></div>
  <label>Solver effort</label><select id="op-time"><option value="0.5">Fast (0.5 s)</option><option value="1.5" selected>Balanced (1.5 s)</option><option value="4">Thorough (4 s)</option></select>
  <label>Traffic multiplier: <b id="op-tv">1.00×</b></label><div class="slider"><input id="op-traffic" type="range" min="0.8" max="1.6" step="0.05" value="1"></div>
  <label class="check"><input id="op-roads" type="checkbox" style="width:auto" checked> Use real road distances (needs internet)</label>
  <div class="btnrow"><button class="outline" data-p3="plan" data-apply="0">Preview plan</button><button data-p3="plan" data-apply="1">Apply plan</button></div>
  <p class="muted" style="margin-top:12px"><small>Weights, delivery windows and priorities come from your orders. Overdue windows are served first; windows opening more than 2 hours later wait for a later plan.</small></p></div>
  <div class="card"><div class="sectionTitle"><h3>Map</h3><span id="op-src" class="pill">no plan yet</span></div><div id="opMap" class="map real-map"></div></div></div><div id="opOut"></div>`;
  $('#op-traffic').oninput = e => $('#op-tv').textContent = (+e.target.value).toFixed(2) + '×';
  baseMap('opMap'); if (plan) paintPlan(plan);
};
A.plan = async b => {
  const apply = b.dataset.apply === '1'; if (apply && !confirm('Apply this plan? Orders will be assigned and drivers notified.')) return;
  document.querySelectorAll('[data-p3=plan]').forEach(x => x.disabled = true); $('#opOut').innerHTML = '<div class="loading-state" style="margin-top:18px">Optimizing routes…</div>';
  try { plan = await api('/optimizer/run', { method: 'POST', body: JSON.stringify({ apply, traffic_factor: +$('#op-traffic').value, use_roads: $('#op-roads').checked, time_limit_s: +$('#op-time').value }) });
    paintPlan(plan); toast(plan.applied ? `Plan applied: ${plan.routes.length} routes` : plan.routes.length ? 'Preview ready. Nothing saved yet' : (plan.message || 'Nothing to plan')); }
  catch (e) { $('#opOut').innerHTML = `<div class="card" style="margin-top:18px"><div class="empty">${esc(e.message)}</div></div>`; toast(e.message, true); }
  document.querySelectorAll('[data-p3=plan]').forEach(x => x.disabled = false);
};
function paintPlan(x) {
  const out = $('#opOut'); if (!out) return; $('#op-src') && ($('#op-src').textContent = x.distance_source === 'osrm' ? 'Real road distances' : 'Estimated distances');
  if (!x.routes.length) { out.innerHTML = `<div class="card" style="margin-top:18px"><div class="empty">${esc(x.message || 'No routes could be planned.')}${(x.excluded || []).length ? '<br>' + x.excluded.map(e => `Order #${e.order_id}: ${esc(e.reason)}`).join('<br>') : ''}</div></div>`; return; }
  const b = x.metrics.baseline, o = x.metrics.optimized, im = x.metrics.improvement;
  const row = (l, bv, ov, lower = true) => `<tr><td>${l}</td><td>${bv}</td><td><b>${ov}</b></td>${delta(+String(bv).replace(/[^0-9.\-]/g, ''), +String(ov).replace(/[^0-9.\-]/g, ''), lower)}</tr>`;
  out.innerHTML = `<div class="card" style="margin-top:18px"><div class="sectionTitle"><h3>${x.applied ? '✅ Plan applied' : '👁 Preview (not saved)'}</h3><span class="pill">${x.routes.length} routes · ${x.routes.reduce((s, r) => s + r.stops, 0)} orders</span></div>
  <div class="table-wrap"><table class="cmp"><thead><tr><th></th><th>Old method</th><th>Optimizer</th><th>Change</th></tr></thead><tbody>
  ${row('Distance (km)', b.distance_km, o.distance_km)}${row('Late minutes', b.late_minutes, o.late_minutes)}${row('Travel cost (₹)', Math.round(b.travel_cost), Math.round(o.travel_cost))}${row('Vehicles used', b.vehicles_used, o.vehicles_used)}${row('Orders left unplanned', b.unassigned, o.unassigned)}</tbody></table></div>
  <p class="muted" style="margin-top:10px"><small>“Old method” = nearest-neighbour planning on the same distances, ignoring delivery windows. Distance ${im.distance_pct >= 0 ? 'saved' : 'added'}: <b>${Math.abs(im.distance_pct)}%</b> · lateness removed: <b>${im.late_minutes_saved} min</b>. Delay risk per stop: ${x.risk_source === 'ml' ? 'trained model' : 'rule of thumb'}.</small></p></div>
  ${x.routes.map((r, i) => `<div class="rcard"><div class="rcard-h"><span class="dot" style="background:${COLORS[i % COLORS.length]}"></span><b>${esc(r.vehicle)}</b><span class="muted">${esc(r.vehicle_type)}</span><span class="pill">${r.stops} stops</span><span class="pill">${r.distance_km} km</span><span class="pill">${r.duration_min} min</span><span class="pill">${money(r.cost)}</span>${r.route_id ? `<span class="pill status-completed">Route #${r.route_id}</span>` : ''}${r.high_risk_stops ? `<span class="pill status-high">${r.high_risk_stops} high-risk stop${r.high_risk_stops > 1 ? 's' : ''}</span>` : ''}</div>
  <div class="bar2"><i style="width:${r.capacity_utilization}%"></i></div><small class="muted">Load ${r.load_kg} / ${r.capacity_kg} kg (${r.capacity_utilization}%)</small>
  <div style="margin-top:8px">${r.stop_details.map(s => `<div class="stoprow"><span class="seq" style="background:${COLORS[i % COLORS.length]}">${s.sequence}</span><span style="flex:1"><b>Order #${s.order_id}</b> <small class="muted">· ${s.weight_kg} kg · priority ${s.priority}</small></span><span>ETA <b>${esc(s.arrive)}</b></span><small class="muted">window ${esc(s.window)}</small>${s.late_min ? `<span class="pill status-high">${s.late_min} min late</span>` : '<span class="pill status-low">on time</span>'}${s.delay_risk != null ? `<span class="pill ${s.risk_level === 'high' ? 'status-high' : s.risk_level === 'medium' ? 'status-medium' : 'status-low'}" title="${esc((s.risk_factors || []).join(', '))}">${Math.round(s.delay_risk * 100)}% delay risk</span>` : ''}</div>`).join('')}</div></div>`).join('')}
  ${(x.unassigned_detail || []).length || (x.excluded || []).length ? `<div class="card"><h3>Not planned</h3>${(x.unassigned_detail || []).map(u => `<p><b>Order #${u.order_id}</b> · ${esc(u.reason)}</p>`).join('')}${(x.excluded || []).map(u => `<p><b>Order #${u.order_id}</b> · ${esc(u.reason)}</p>`).join('')}</div>` : ''}`;
  const n = document.getElementById('opMap'); if (!n || typeof L === 'undefined') return; const m = baseMap('opMap'), all = [];
  x.routes.forEach((r, i) => { const col = COLORS[i % COLORS.length], pts = [r.depot, ...r.stop_details.map(s => [s.lat, s.lng])]; L.polyline(pts, { color: col, weight: 5, opacity: .85 }).addTo(m);
    L.marker(r.depot, { icon: L.divIcon({ html: `<div class="veh">🚚</div>`, className: 'veh-wrap', iconSize: [36, 36], iconAnchor: [18, 18] }) }).addTo(m).bindPopup(`${esc(r.vehicle)} start`);
    r.stop_details.forEach(s => L.marker([s.lat, s.lng], { icon: numIcon(s.sequence, col) }).addTo(m).bindPopup(`Order #${s.order_id} · ETA ${esc(s.arrive)}`)); all.push(...pts); });
  if (all.length) m.fitBounds(all, { padding: [30, 30] });
}

/* ---------- driver: my delivery route ---------- */
const NEXT = { assigned: [['picked_up', 'Picked up']], picked_up: [['in_transit', 'Out for delivery'], ['delivered', 'Delivered']], in_transit: [['delivered', 'Delivered']] };
H['driver:route'] = async c => {
  const { route: r } = await api('/driver/route');
  if (!r) { c.innerHTML = '<div class="card"><div class="empty"><h3>No delivery route right now</h3><p class="muted">When the dispatcher plans routes, your stops appear here with timings and what to collect.</p></div></div>'; return; }
  const left = r.stops.filter(s => !['delivered', 'failed', 'cancelled'].includes(s.status)).length;
  c.innerHTML = `<div class="grid kpis"><div class="card kpi"><label>Vehicle</label><strong style="font-size:20px">${esc(r.plate)}</strong><span class="up">${esc(r.vtype)}</span></div><div class="card kpi"><label>Stops left</label><strong>${left}/${r.stops.length}</strong><span class="up">${r.distance_km} km planned</span></div>
  <div class="card kpi"><label>Load</label><strong>${Math.round(r.load_kg || 0)} kg</strong><span class="up">of ${r.capacity_kg} kg</span></div><div class="card kpi"><label>Cash to collect</label><strong>${money(r.stops.reduce((s, x) => s + (x.collect || 0), 0))}</strong><span class="up">Cash on delivery</span></div></div>
  <div class="track-layout" style="margin-top:18px"><div class="card ride-map-card"><div id="rtMap" class="map real-map"></div></div><div class="card"><h3>Your stops</h3>${r.stops.map(s => `<div class="rcard"><div class="rcard-h"><span class="seq" style="width:26px;height:26px;border-radius:50%;background:var(--brand);color:#fff;display:grid;place-items:center;font-weight:800">${s.seq}</span><b>Order #${s.order_id}</b>${pill(s.status)}<span class="muted" style="margin-left:auto">ETA <b>${esc(s.eta || '')}</b></span></div>
  <p style="margin:8px 0 2px"><b>${esc(s.customer)}</b> · ${esc(s.address || 'Address on map')}</p><small class="muted">Window ${esc(s.delivery_window || '')} · ${s.weight_kg ? Math.round(s.weight_kg) + ' kg' : ''}</small>
  ${s.collect ? `<div class="notice" style="margin:8px 0 0">Collect cash <b>${money(s.collect)}</b></div>` : ''}
  <div class="btnrow"><a class="callbtn" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=${s.lat},${s.lng}">🧭 Navigate</a>${s.phone ? `<a class="callbtn" href="tel:${esc(s.phone)}">📞 Call</a>` : ''}
  ${(NEXT[s.status] || []).map(([st, label]) => `<button class="btn-sm" data-p3="ostat" data-id="${s.order_id}" data-s="${st}">${label}</button>`).join('')}${['assigned', 'picked_up', 'in_transit'].includes(s.status) ? `<button class="btn-sm danger" data-p3="ostat" data-id="${s.order_id}" data-s="failed">Failed</button>` : ''}</div></div>`).join('')}</div></div>`;
  const m = baseMap('rtMap'); if (m) { const pts = [[r.vlat, r.vlng], ...r.stops.map(s => [s.lat, s.lng])].filter(p => p[0] != null); L.polyline(pts, { color: '#5548e7', weight: 5, opacity: .85 }).addTo(m);
    r.stops.forEach(s => L.marker([s.lat, s.lng], { icon: numIcon(s.seq, ['delivered'].includes(s.status) ? '#16a34a' : s.status === 'failed' ? '#e43d65' : '#5548e7') }).addTo(m).bindPopup(`Order #${s.order_id} · ${esc(s.customer)}`)); if (pts.length) m.fitBounds(pts, { padding: [30, 30] }); }
};
A.ostat = async b => { if (b.dataset.s === 'failed' && !confirm('Mark this delivery as failed?')) return; await api(`/orders/${b.dataset.id}/status`, { method: 'PATCH', body: JSON.stringify({ status: b.dataset.s }) }); toast('Order updated'); navigate('route'); };

/* ---------- wiring ---------- */
const _r = render;
render = async function () {
  const role = session.user.role, h = H[role + ':' + page] || (OPS.includes(role) && page === 'optimizer' ? H.optimizer : null);
  $('#subtitle').textContent = 'Live operational intelligence';
  if (!h) return _r();
  window.rnStopTimers && window.rnStopTimers(); $('#pageTitle').textContent = page === 'route' ? 'My Delivery Route' : 'Route Optimizer'; $('#subtitle').textContent = page === 'route' ? 'Your stops, in the best order' : 'Plan, compare and apply delivery routes';
  return h($('#content'));
};
document.addEventListener('click', async e => { const b = e.target.closest('[data-p3]'); if (!b) return; const fn = A[b.dataset.p3]; if (!fn) return; try { await fn(b); } catch (err) { toast(err.message, true); } });
})();
