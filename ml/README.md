# RouteNex ML

Three scikit-learn gradient-boosting models, trained with `python ml\train.py` (or the **Retrain models** button on Analytics & ML):

| Model | Predicts | Used for | Baseline it must beat |
|---|---|---|---|
| `eta` | trip / delivery minutes | ETAs shown when booking rides and parcels (+ plain-language reasons) | the old formula: distance / speed x peak factor |
| `delay` | P(delivery window missed) per stop | risk badge on every optimizer stop, saved with the route | base rate, and the rule "less slack = riskier" |
| `demand` | requests per area per hour | 24 h forecast, busy-area hints for drivers, small surge nudge (max +-10%) | same hour last week (seasonal naive) |

* **Validation is temporal**: train on earlier days, test on the last days (never a random split).
* **Quality gates** (`GATES` in `train.py`): a new model is promoted into `artifacts/registry.json` only if it passes; otherwise the previous one stays live.
* **Explanations**: ETA reasons ("Heavy traffic +4 min") and delay reasons ("Tight window") come from re-predicting with one factor neutralised; the Analytics page also shows permutation importance.
* **Graceful fallback**: no scikit-learn or no artifacts -> formulas / rules are used and the app keeps working.
* **Data is synthetic** (`data.py`). There is no public per-trip dataset for Jaipur. Real data hook: `data.load_real()`. Weather (Open-Meteo), fleet and request counts shown in the app are real.
