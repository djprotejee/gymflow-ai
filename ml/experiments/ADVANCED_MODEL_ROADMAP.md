# Advanced Forecasting Model Roadmap

Date: 2026-05-23

This roadmap keeps the broader thesis idea explicit: GymFlow AI is not limited to one regressor. The project investigates a family of forecasting approaches and uses the best defensible model in the product layer.

## Already Implemented

| Family | Current Implementation | Artifact |
|---|---|---|
| Naive baseline | previous observation | `ml/reports/baseline_metrics.csv` |
| Seasonal/profile baseline | daily lag, rolling mean, gym-weekday-hour profile | `ml/reports/baseline_metrics.csv` |
| Regression | Ridge regression | `ml/reports/ml_experiment_metrics.csv` |
| Tree-based ML | Random Forest, HistGradientBoostingRegressor | `ml/reports/ml_experiment_metrics.csv` |
| Statistical model | compact ARIMA(2,0,2) for selected gym | `ml/reports/ml_experiment_metrics.csv` |

## Newly Completed Research Block

### Feature Ablation

The current ablation run uses HistGradientBoostingRegressor on a time-respecting 80/20 split per gym.

| Feature group | MAE | RMSE | WAPE |
|---|---:|---:|---:|
| calendar_lag | 6.3853 | 9.4751 | 0.1455 |
| all_features | 6.5138 | 9.6478 | 0.1484 |
| calendar_holiday_lag | 6.5244 | 9.7505 | 0.1486 |
| lag_rolling | 7.7067 | 11.6886 | 0.1756 |
| lag_only | 7.7534 | 11.7877 | 0.1766 |
| calendar_rolling | 8.3383 | 11.6231 | 0.1900 |
| calendar_only | 10.1734 | 14.0493 | 0.2318 |
| calendar_holiday | 10.3305 | 14.2122 | 0.2354 |
| rolling_only | 12.4207 | 17.9005 | 0.2830 |

Current interpretation: the best observed feature group is calendar plus lag features. Rolling-window features do not improve the current real-data holdout when added to that feature set. Holiday features are included for future and synthetic scenarios, but the current real holdout is too short to prove holiday effects empirically.

Artifacts:

- `ml/reports/feature_ablation_metrics.csv`
- `ml/reports/feature_ablation_report.md`
- `ml/reports/figures/feature_ablation_mae.png`

## Next Research Blocks

### 1. LSTM or GRU

Use selected gym-level sequences or pooled gym windows.

Recommended first version:

- input window: 24–96 observations;
- horizon: 1–12 steps;
- target: `active_people`;
- compare against HistGradientBoosting on the same split.

Constraint: the current real dataset is short. LSTM/GRU should be evaluated carefully and may be more useful on the synthetic scenario extension than on the real holdout.

### 2. Transformer-Based Forecasting

Candidate approaches:

- compact PyTorch Transformer encoder for sequence windows;
- temporal fusion or patch-based time-series model if time permits;
- documented research branch if implementation cost becomes too high.

Constraint: Transformer models can overfit small datasets and require a stronger evaluation protocol than a simple dashboard demo.

### 3. External Factors

Planned factors:

- public holidays;
- weekend/open-hours indicators;
- weather adapter after official/free source verification;
- abnormal-event flags if available.

Current implementation includes Ukrainian 2026 holiday flags and low-traffic holiday windows in the real feature pipeline, synthetic generator, and future forecast artifacts. Current verified holiday sources include the Verkhovna Rada 2026 official holiday calendar and a public 2026 Ukraine holiday list used to cross-check major public dates.

### 4. Assistant Fine-Tuning

Fine-tuning belongs to the AI coach branch, not the occupancy forecast branch.

Planned comparison:

- base assistant;
- RAG assistant with curated exercise knowledge;
- optional fine-tuned or LoRA-adapted assistant.

Details: `ml/fine_tuning/README.md`.

## Thesis Position

The defended core should emphasize verified model comparisons on real data. LSTM, Transformer, and fine-tuning can strengthen the work, but they should not replace the already working forecasting pipeline unless they produce better, reproducible results.
