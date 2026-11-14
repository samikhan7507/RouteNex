/* RouteNex Phase 4 UI: Analytics & ML (trained models, forecast, delay risk, registry) + busy-area hints for drivers. */
(() => {
const OPS = ['dispatcher', 'fleet_manager', 'admin'], A = {};
let timer = null;
const clear = () => { if (timer) { clearInterval(timer); timer = null; } };
const f1 = v => v == null ? '—' : (Math.round(v * 10) / 10).toString();

/* ---------- tiny SVG charts (no libraries, CSP-safe) ---------- */
function lineChart(f, w = 640, h = 230) {
  const pad = { l: 38, r: 10, t: 10, b: 26 }, iw = w - pad.l - pad.r, ih = h - pad.t - pad.b, max = Math.max(...f.high, 1) * 1.08, n = f.labels.length;
  const x = i => pad.l + iw * i / (n - 1), y = v => pad.t + ih * (1 - v / max);
  const band = f.high.map((v, i) => `${x(i)},${y(v)}`).concat(f.low.map((v, i) => `${x(n - 1 - i)},${y(f.low[n - 1 - i])}`)).join(' ');
  const grid = [0, .25, .5, .75, 1].map(t => `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y(max * t)}" y2="${y(max * t)}" stroke="#e8ecf3"/><text x="${pad.l - 6}" y="${y(max * t) + 4}" text-anchor="end" font-size="10" fill="#8a94a6">${Math.round(max * t)}</text>`).join('');
  const xl = f.labels.map((l, i) => i % 4 === 0 ? `<text x="${x(i)}" y="${h - 8}" text-anchor="middle" font-size="10" fill="#8a94a6">${esc(l.split(' ')[1])}</text>` : '').join('');
  return `<svg viewBox="0 0 ${w} ${h}" class="chart-svg" role="img" aria-label="Demand forecast">${grid}<polygon points="${band}" fill="#5548e7" opacity=".12"/><polyline fill="none" stroke="#5548e7" stroke-width="3" points="${f.total.map((v, i) => `${x(i)},${y(v)}`).join(' ')}"/>${xl}</svg>`;
}
function scatter(pairs, w = 360, h = 300) {
  const pad = 34, max = Math.max(...pairs.flat(), 10) * 1.05, s = v => pad + (w - pad - 10) * v / max, t = v => h - pad - (h - pad - 10) * v / max;
  return `<svg viewBox="0 0 ${w} ${h}" class="chart-svg" role="img" aria-label="Predicted vs actual"><line x1="${s(0)}" y1="${t(0)}" x2="${s(max)}" y2="${t(max)}" stroke="#08bda7" stroke-dasharray="5 4" stroke-width="2"/>
  ${pairs.map(([a, p]) => `<circle cx="${s(a)}" cy="${t(p)}" r="3" fill="#5548e7" opacity=".55"/>`).join('')}<text x="${w / 2}" y="${h - 6}" text-anchor="middle" font-size="11" fill="#667085">Actual minutes</text><text x="12" y="${h / 2}" font-size="11" fill="#667085" transform="rotate(-90 12 ${h / 2})" text-anchor="middle">Predicted</text></svg>`;
}
function calib(cal, w = 360, h = 300) {
  const pad = 34, s = v => pad + (w - pad - 10) * v, t = v => h - pad - (h - pad - 10) * v;
  return `<svg viewBox="0 0 ${w} ${h}" class="chart-svg" role="img" aria-label="Calibration"><line x1="${s(0)}" y1="${t(0)}" x2="${s(1)}" y2="${t(1)}" stroke="#08bda7" stroke-dasharray="5 4" stroke-width="2"/>
  <polyline fill="none" stroke="#5548e7" stroke-width="3" points="${cal.map(c => `${s(c.pred)},${t(c.observed)}`).join(' ')}"/>${cal.map(c => `<circle cx="${s(c.pred)}" cy="${t(c.observed)}" r="4" fill="#5548e7"/>`).join('')}
  <text x="${w / 2}" y="${h - 6}" text-anchor="middle" font-size="11" fill="#667085">Predicted risk</text><text x="12" y="${h / 2}" font-size="11" fill="#667085" transform="rotate(-90 12 ${h / 2})" text-anchor="middle">Actually late</text></svg>`;
}
const importance = items => { const mx = Math.max(...items.map(i => i.value), 1e-9); return items.slice(0, 6).map(i => `<div class="imp-row"><span>${esc(i.feature)}</span><div class="bar2"><i style="width:${Math.max(3, i.value / mx * 100)}%"></i></div></div>`).join(''); };

/* ---------- analytics page ---------- */
async function analytics(c) {
  const d = await api('/ml/predictions'), st = d.status, rep = d.report, m = rep ? rep.models : null, w = d.weather;
  const eta = m && m.eta.metrics, del = m && m.delay.metrics, dem = m && m.demand.metrics;
  const ready = st.models.eta && st.models.delay && st.models.demand;
  c.innerHTML = `<div class="chips"><span class="chip">${w.rain ? '🌧 Rain in Jaipur' : '☀ Clear in Jaipur'}${w.temp_c != null ? ' · ' + Math.round(w.temp_c) + '°C' : ''} <small>(${w.source === 'open-meteo' ? 'live weather' : 'weather offline'})</small></span>
    <span class="chip ${st.training ? 'warn' : ready ? 'ok' : 'bad'}">${st.training ? '⏳ Training models…' : !st.sklearn ? '⚠ scikit-learn not installed' : ready ? '✓ Models ready' : '⚠ Models not trained'}</span>
    <span class="chip">Training data: <b>synthetic</b></span>${st.trained_at ? `<span class="chip">Trained ${esc(st.trained_at)}</span>` : ''}
    ${session.user.role === 'admin' ? `<button class="btn-sm" data-p4="retrain" ${st.training || !st.sklearn ? 'disabled' : ''}>Retrain models</button>` : ''}</div>
  <div class="grid kpis" style="margin-top:14px">
    <div class="card kpi"><label>ETA error (MAE)</label><strong>${eta ? f1(eta.mae_min) + ' min' : '—'}</strong><span class="up">${eta ? `old formula ${f1(eta.baseline_mae_min)} min · ${eta.mae_improvement_pct}% better` : 'train the models'}</span></div>
    <div class="card kpi"><label>Delay model (AUC)</label><strong>${del ? del.auc : '—'}</strong><span class="up">${del ? `simple rule ${del.baseline_auc_rule} · Brier ${del.brier}` : ''}</span></div>
    <div class="card kpi"><label>Demand error (MAE)</label><strong>${dem ? f1(dem.mae) : '—'}</strong><span class="up">${dem ? `${dem.mae_improvement_pct}% better than “same hour last week”` : ''}</span></div>
    <div class="card kpi"><label>Delay risk, live routes</label><strong>${d.network_delay_risk != null ? Math.round(d.network_delay_risk * 100) + '%' : '—'}</strong><span class="up">${d.active_stops} planned stops</span></div></div>
  <div class="grid two" style="margin-top:18px"><div class="card"><div class="sectionTitle"><h3>Demand forecast · next 24 hours</h3><span class="pill">${d.forecast.source === 'ml' ? 'ML model' : 'rule of thumb'}</span></div>${lineChart(d.forecast)}
    <small class="muted">Requests per hour across all areas (rides + parcels + orders); shaded band = likely range.${w.source === 'open-meteo' ? ' Uses the live rain forecast.' : ''}</small></div>
    <div class="card"><h3>Busy areas, next 2 hours</h3>${d.hotspots.map(h => `<div class="row"><span><b>${esc(h.zone)}</b></span><span class="pill ${h.vs_avg >= 1.2 ? 'status-medium' : ''}">${h.vs_avg}× average</span><b>${h.expected}</b></div>`).join('')}
    <div class="grid kpis" style="grid-template-columns:1fr 1fr;margin-top:14px"><div class="mini-stat"><small>Fleet in use</small><b>${d.fleet_utilization_pct}%</b></div><div class="mini-stat"><small>Route performance</small><b>${d.route_performance_score != null ? d.route_performance_score + '/100' : '—'}</b></div>
    <div class="mini-stat"><small>Requests, last 24 h</small><b>${d.requests_last_24h}</b></div><div class="mini-stat"><small>Price nudge from forecast</small><b>${eta ? '±10% max' : '—'}</b></div></div></div></div>
  ${eta ? `<div class="grid two" style="margin-top:18px"><div class="card"><div class="sectionTitle"><h3>ETA model · predicted vs actual</h3><span class="pill">held-out last 15 days</span></div>${scatter(eta.scatter)}<small class="muted">Dots on the dashed line are perfect. 90% of predictions are within ${eta.p90_abs_error_min} min · R² ${eta.r2} (old formula ${eta.baseline_r2}).</small></div>
    <div class="card"><h3>What drives the ETA</h3>${importance(eta.importance)}<h3 style="margin-top:18px">What drives delay risk</h3>${importance(del.importance)}</div></div>
  <div class="grid two" style="margin-top:18px"><div class="card"><div class="sectionTitle"><h3>Delay risk · is it honest?</h3><span class="pill">calibration</span></div>${calib(del.calibration)}<small class="muted">When the model says 30% risk, about 30% of those stops really were late. Closer to the dashed line is better.</small></div>
    <div class="card"><h3>Stops most at risk right now</h3>${d.high_risk_stops.length ? `<div class="table-wrap"><table><thead><tr><th>Order</th><th>Vehicle</th><th>ETA</th><th>Risk</th></tr></thead><tbody>${d.high_risk_stops.map(s => `<tr><td>#${s.order_id}</td><td>${esc(s.plate || '')}</td><td>${esc(s.eta || '')}</td><td><span class="pill ${s.risk >= .5 ? 'status-high' : s.risk >= .25 ? 'status-medium' : 'status-low'}">${Math.round(s.risk * 100)}%</span></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No planned routes yet. Apply a plan on the Optimizer page.</div>'}</div></div>
  <div class="card" style="margin-top:18px"><h3>Model registry</h3><div class="table-wrap"><table><thead><tr><th>Model</th><th>Version</th><th>Quality gate</th><th>Result</th><th>Test rows</th></tr></thead><tbody>
  ${[['ETA', 'eta', 'MAE ≥ 5% better than old formula and R² ≥ 0.5'], ['Delay risk', 'delay', 'AUC ≥ 0.70'], ['Demand', 'demand', 'MAE not worse than “same hour last week”']].map(([n, k, g]) => `<tr><td><b>${n}</b></td><td>${esc(m[k].version)}</td><td>${g}</td><td><span class="pill ${m[k].promoted ? 'status-low' : 'status-high'}">${m[k].promoted ? 'promoted' : 'rejected, previous kept'}</span></td><td>${m[k].metrics.rows_test}</td></tr>`).join('')}</tbody></table></div>
  <p class="muted" style="margin-top:12px"><small><b>Read this honestly:</b> there is no public per-trip dataset for Jaipur, so these models are trained on realistic <b>synthetic</b> trips generated in <code>ml/data.py</code>. The metrics prove the pipeline (temporal validation, baselines, quality gates, explanations), not real-world accuracy. Weather, fleet and request counts shown here are real.</small></p></div>` : `<div class="card" style="margin-top:18px"><div class="empty"><h3>No trained models yet</h3><p class="muted">${st.training ? 'Training in progress, this page refreshes by itself.' : st.sklearn ? 'Admins can press “Retrain models”.' : 'Install scikit-learn (setup.bat does this) and restart.'}</p></div></div>`}`;
  if (st.training) timer = setInterval(async () => { try { const s = await api('/ml/status'); if (!s.training) { clear(); navigate('analytics'); } } catch (e) {} }, 3000);
}
A.retrain = async () => { await api('/ml/retrain', { method: 'POST' }); toast('Training started. This takes about 10 seconds'); navigate('analytics'); };

/* ---------- drivers: where demand is coming ---------- */
async function hotspots() {
  try { const h = await api('/ml/hotspots'); const c = $('#content'); if (!c || !h.zones.length) return;
    c.insertAdjacentHTML('beforeend', `<div class="card" style="margin-top:18px"><h3>🔥 Busy areas soon</h3><div class="chips">${h.zones.map(z => `<span class="chip">${esc(z.zone)} <small>${z.vs_avg}× average</small></span>`).join('')}</div><small class="muted">Forecast for the next two hours. Waiting there means shorter pickups.</small></div>`); } catch (e) {}
}

/* ---------- wiring ---------- */
const _r = render;
render = async function () {
  clear(); const role = session.user.role;
  if (OPS.includes(role) && page === 'analytics') {
    window.rnStopTimers && window.rnStopTimers(); $('#pageTitle').textContent = 'Analytics & ML'; $('#subtitle').textContent = 'Trained models, forecasts and delay risk';
    try { return await analytics($('#content')); } catch (e) { $('#content').innerHTML = `<div class="card"><div class="empty">${esc(e.message)}</div></div>`; return; }
  }
  const out = await _r(); if (role === 'driver' && page === 'overview') hotspots(); return out;
};
document.addEventListener('click', async e => { const b = e.target.closest('[data-p4]'); if (!b) return; const fn = A[b.dataset.p4]; if (!fn) return; try { await fn(b); } catch (err) { toast(err.message, true); } });
})();
