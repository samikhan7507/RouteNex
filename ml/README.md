# RouteNex ML

RouteNex includes an optional, gated ML pipeline for ETA, delivery-delay risk and demand forecasts.

From the repository root, with the Python environment activated:

```bash
python ml/train.py
```

Or queue a training job from the Operations ML tab / `POST /api/ml/train` and run the background
worker (`python scripts/worker.py`).

| Model | Target | Promotion gate |
|---|---|---|
| `eta` | Trip/delivery duration in minutes | At least 5% MAE improvement over the formula and R² ≥ 0.5 |
| `delay` | Delivery-window miss probability | ROC AUC ≥ 0.70 |
| `demand` | Requests per area/hour | MAE no worse than the same-hour-last-week baseline |

- Validation is **temporal**: earlier days train the candidate; later days test it.
- Candidates are versioned under `ml/artifacts/` (configurable with `ML_ARTIFACT_DIR`).
- Only candidates passing their gates enter `registry.json`; publication uses an atomic replace.
- Serving reads the active registry, not the latest candidate. Rejected models never become live.
- Reports retain metrics and promotion decisions. Generated artifacts are git-ignored.
- Without an available artifact, the application uses explicitly labelled heuristic fallbacks.

**Data limitation:** the included training data is synthetic (`data.py`). Its metrics validate the
pipeline, not real-world Jaipur accuracy. ML predictions are labelled `ml-synthetic`. Replace the
training-data loader with approved operational data and revalidate before using predictions for real
dispatch decisions. Weather inputs can use Open-Meteo when reachable, with a labelled offline fallback.
