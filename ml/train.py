"""Train, validate and promote RouteNex models.   Run:  python ml\\train.py        (from the project folder)

Three scikit-learn gradient-boosting models:
  eta     - trip / delivery duration (minutes)      baseline = old formula: distance / free-flow speed x peak factor
  delay   - P(delivery window missed) per stop      baseline = base rate and the rule 'less slack = riskier'
  demand  - requests per area per hour (Poisson)    baseline = same hour last week (seasonal naive)
Validation is TEMPORAL (train on earlier days, test on the last days). A model is promoted into registry.json only if it passes its gate.
Data is synthetic (see data.py) - the metrics prove the pipeline, not real-world accuracy."""
import json, sys, time, pathlib
import numpy as np
import joblib
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, brier_score_loss, mean_absolute_error, r2_score, roc_auc_score

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from ml import data, features as F

GATES = {"eta": {"mae_improvement_pct_min": 5.0, "r2_min": 0.5}, "delay": {"auc_min": 0.70}, "demand": {"mae_improvement_pct_min": 0.0}}
CAT = {"eta": [F.ETA_FEATURES.index("vclass")], "delay": [F.DELAY_FEATURES.index("vclass")], "demand": [0]}


def _split(day, test_days):
    cut = day.max() - test_days + 1
    return day < cut, day >= cut


def _pct(before, after):
    return round(100.0 * (before - after) / before, 1) if before else 0.0


def _save(out, name, model, features, meta, version):
    path = out / f"{name}-{version}.joblib"
    joblib.dump({"model": model, "features": features, "version": version, "sklearn": sklearn.__version__, "meta": meta}, path)
    return path.name


def train_eta(n, seed):
    X, y, day = data.make_eta(n, seed=seed)
    tr, te = _split(day, 15)
    m = HistGradientBoostingRegressor(max_iter=350, learning_rate=0.08, max_leaf_nodes=31, categorical_features=CAT["eta"], early_stopping=True, random_state=seed)
    m.fit(X[tr], np.log1p(y[tr]))
    pred = np.expm1(m.predict(X[te])); yt = y[te]
    hrs, vcs, kms = X[te][:, 1], X[te][:, 5], X[te][:, 0]
    base = np.array([F.heuristic_eta(F.VCLASSES[int(v)], k, h) for v, k, h in zip(vcs, kms, hrs)], dtype=float)
    mae, bmae = mean_absolute_error(yt, pred), mean_absolute_error(yt, base)
    idx = np.random.default_rng(1).choice(len(yt), size=min(220, len(yt)), replace=False)
    sub = np.random.default_rng(2).choice(len(yt), size=min(2500, len(yt)), replace=False)
    imp = permutation_importance(m, X[te][sub], np.log1p(yt[sub]), n_repeats=3, random_state=0)
    labels = {"distance_km": "Trip distance", "hour": "Time of day", "dow": "Day of week", "rain": "Rain", "cong": "Area traffic level", "vclass": "Vehicle type", "load_kg": "Load weight"}
    metrics = {"rows_train": int(tr.sum()), "rows_test": int(te.sum()), "mae_min": round(mae, 2), "baseline_mae_min": round(bmae, 2), "mae_improvement_pct": _pct(bmae, mae),
               "rmse_min": round(float(np.sqrt(np.mean((yt - pred) ** 2))), 2), "baseline_rmse_min": round(float(np.sqrt(np.mean((yt - base) ** 2))), 2),
               "r2": round(r2_score(yt, pred), 3), "baseline_r2": round(r2_score(yt, base), 3),
               "mape_pct": round(float(np.mean(np.abs(yt - pred) / yt) * 100), 1), "p90_abs_error_min": round(float(np.percentile(np.abs(yt - pred), 90)), 1),
               "scatter": [[round(float(a), 1), round(float(b), 1)] for a, b in zip(yt[idx], pred[idx])],
               "importance": sorted([{"feature": labels[f], "value": round(float(v), 4)} for f, v in zip(F.ETA_FEATURES, imp.importances_mean)], key=lambda r: -r["value"])}
    return m, metrics


def train_delay(n, seed):
    X, y, day = data.make_delay(n, seed=seed + 4)
    tr, te = _split(day, 15)
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=31, categorical_features=CAT["delay"], early_stopping=True, random_state=seed)
    m.fit(X[tr], y[tr])
    p = m.predict_proba(X[te])[:, 1]; yt = y[te]
    rule = -X[te][:, 0]                                        # baseline: the less slack, the riskier
    bins = np.linspace(0, 1, 11); cal = []
    for a, b in zip(bins[:-1], bins[1:]):
        mask = (p >= a) & (p < b if b < 1 else p <= b)
        if mask.sum() >= 30:
            cal.append({"pred": round(float(p[mask].mean()), 3), "observed": round(float(yt[mask].mean()), 3), "n": int(mask.sum())})
    sub = np.random.default_rng(3).choice(len(yt), size=min(2500, len(yt)), replace=False)
    imp = permutation_importance(m, X[te][sub], yt[sub], n_repeats=3, random_state=0, scoring="roc_auc")
    labels = {"slack": "Window slack", "seq": "Position in route", "n_stops": "Stops on route", "leg_km": "Leg distance", "route_km": "Route length", "load_ratio": "Load vs capacity",
              "hour": "Time of day", "dow": "Day of week", "rain": "Rain", "cong": "Area traffic level", "priority": "Priority", "vclass": "Vehicle type"}
    metrics = {"rows_train": int(tr.sum()), "rows_test": int(te.sum()), "late_rate": round(float(yt.mean()), 3), "auc": round(roc_auc_score(yt, p), 3), "baseline_auc_rule": round(roc_auc_score(yt, rule), 3),
               "baseline_auc_prior": 0.5, "avg_precision": round(average_precision_score(yt, p), 3), "brier": round(brier_score_loss(yt, p), 4), "baseline_brier": round(brier_score_loss(yt, np.full_like(p, yt.mean())), 4),
               "accuracy_at_0.5": round(float(((p > 0.5) == yt).mean()), 3), "calibration": cal,
               "importance": sorted([{"feature": labels[f], "value": round(float(v), 4)} for f, v in zip(F.DELAY_FEATURES, imp.importances_mean)], key=lambda r: -r["value"])}
    return m, metrics


def train_demand(days, seed):
    X, y, day = data.make_demand(days, seed=seed + 14)
    tr, te = _split(day, 10)
    m = HistGradientBoostingRegressor(loss="poisson", max_iter=250, learning_rate=0.08, categorical_features=CAT["demand"], early_stopping=False, random_state=seed)
    m.fit(X[tr], y[tr])
    pred = m.predict(X[te])
    key = {(int(r[0]), int(d), int(r[1])): v for r, d, v in zip(X, day, y)}          # last week's count for the same area + hour
    naive = np.array([key.get((int(r[0]), int(d) - 7, int(r[1])), np.nan) for r, d in zip(X[te], day[te])])
    ok = ~np.isnan(naive); yt = y[te]
    mae, bmae = mean_absolute_error(yt[ok], pred[ok]), mean_absolute_error(yt[ok], naive[ok])
    disp = float(np.std((yt - pred) / np.sqrt(np.maximum(pred, 0.5))))
    metrics = {"rows_train": int(tr.sum()), "rows_test": int(te.sum()), "mae": round(mae, 3), "baseline_mae": round(bmae, 3), "mae_improvement_pct": _pct(bmae, mae),
               "r2": round(r2_score(yt, pred), 3), "dispersion": round(disp, 3), "mean_per_zone_hour": round(float(yt.mean()), 2)}
    return m, metrics, float(np.mean(y[tr]))


def run(out_dir, n_eta=40000, n_delay=30000, days=70, seed=7, log=print):
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    version = time.strftime("%Y%m%d-%H%M%S")
    reg_path = out / "registry.json"
    registry = json.loads(reg_path.read_text()) if reg_path.exists() else {}
    report = {"version": version, "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"), "data": "synthetic", "sklearn": sklearn.__version__, "models": {}}
    jobs = [("eta", lambda: train_eta(n_eta, seed)), ("delay", lambda: train_delay(n_delay, seed)), ("demand", lambda: train_demand(days, seed))]
    for name, fn in jobs:
        t0 = time.time(); res = fn(); model, metrics = res[0], res[1]
        g = GATES[name]
        if name == "eta": passed = metrics["mae_improvement_pct"] >= g["mae_improvement_pct_min"] and metrics["r2"] >= g["r2_min"]
        elif name == "delay": passed = metrics["auc"] >= g["auc_min"]
        else: passed = metrics["mae_improvement_pct"] >= g["mae_improvement_pct_min"]
        meta = {"metrics_summary": {k: v for k, v in metrics.items() if not isinstance(v, list)}}
        if name == "demand": meta["mean_demand"] = res[2]; meta["dispersion"] = metrics["dispersion"]
        file = _save(out, name, model, {"eta": F.ETA_FEATURES, "delay": F.DELAY_FEATURES, "demand": F.DEMAND_FEATURES}[name], meta, version)
        if passed:
            registry[name] = {"current": file, "version": version, "history": (registry.get(name, {}).get("history", []) + [file])[-5:]}
        report["models"][name] = {"version": version, "file": file, "promoted": bool(passed), "gate": g, "metrics": metrics, "seconds": round(time.time() - t0, 1)}
        log(f"[{name}] {'PROMOTED' if passed else 'REJECTED (kept previous)'}  {json.dumps({k: v for k, v in metrics.items() if not isinstance(v, list)})}")
    registry["trained_at"], registry["version"] = report["trained_at"], version
    (out / "metrics.json").write_text(json.dumps(report, indent=1))
    reg_path.write_text(json.dumps(registry, indent=1))
    return report


if __name__ == "__main__":
    run(ROOT / "ml" / "artifacts")
