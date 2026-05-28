# Model Card - GymFlow AI Forecasting Models

## Model Purpose

The forecasting models estimate future gym visitor load for selected gym locations. Their output is used by the GymFlow AI web application to recommend lower-traffic training slots and support personalized training planning.

## Implemented Models

The current implemented models are:

- previous observation baseline;
- one-day seasonal lag baseline;
- rolling mean baseline;
- calendar profile model by gym, weekday, and hour;
- ridge regression;
- random forest;
- histogram gradient boosting;
- compact ARIMA experiment for a selected gym;
- feature ablation for calendar, lag, rolling, and holiday feature groups.
- weather-aware main training pipeline when Open-Meteo weather caches are present.
- compact neural sequence baseline using flattened lag windows and scikit-learn MLP.
- PyTorch LSTM sequence model.
- PyTorch GRU sequence model.
- PyTorch Transformer encoder sequence model.
- SARIMAX with exogenous variables for a selected gym.
- real-only versus real+synthetic training diagnostic.
- empirical future-forecast uncertainty proxy.

## Target Variable

`active_people` - number of active gym visitors at a timestamp.

## Evaluation

Evaluation uses time-respecting train/test splits per gym.

Metrics:

- MAE;
- RMSE;
- WAPE.

Generated reports:

- `ml/reports/baseline_metrics.csv`
- `ml/reports/baseline_metrics.json`
- `ml/reports/ml_experiment_metrics.csv`
- `ml/reports/ml_experiment_metrics.json`
- `ml/reports/ml_predictions_sample.csv`
- `ml/reports/error_by_hour.csv`
- `ml/reports/error_by_weekday.csv`
- `ml/reports/error_by_gym.csv`
- `ml/reports/feature_ablation_metrics.csv`
- `ml/reports/feature_ablation_report.md`

## Current Results

| Model | Scope | MAE | RMSE | WAPE |
|---|---|---:|---:|---:|
| HistGradientBoostingRegressor with weather | all gyms pooled | 6.5723 | 9.7546 | 0.1497 |
| RandomForestRegressor with weather | all gyms pooled | 7.1203 | 10.5220 | 0.1622 |
| Ridge regression with weather | all gyms pooled | 8.1694 | 12.5823 | 0.1861 |
| Previous observation baseline | all gyms pooled | 8.3206 | 13.5099 | 0.1896 |
| ARIMA(2,0,2) | selected gym only | 28.0387 | 37.8481 | 0.3878 |
| SARIMAX(1,0,1) with exogenous features | selected gym only | 11.2694 | 16.3245 | 0.1559 |

Feature ablation shows the best current feature group is calendar plus lag features: MAE `6.3751`, RMSE `9.4323`, WAPE `0.1452`.

Holiday indicators are included in the feature pipeline. They are necessary for future holiday-aware forecasts and synthetic scenario generation, but the current real holdout is too short to prove major holiday behavior empirically. Closed-holiday behavior is implemented as a scenario/business rule for configured major holidays.

Business-hours features are included with the network schedule: weekdays `07:00-22:00`, weekends `09:00-18:00`. Future closed-hour predictions are set to zero before product use.

Weather features are loaded from Open-Meteo caches when available. Weather ablation showed a small improvement for the main HistGradientBoosting model: MAE `6.5723` with weather versus `6.5896` without weather.

The compact neural sequence baseline currently reaches MAE `8.0350`, RMSE `11.7279`, WAPE `0.1843`. It is retained as a neural-family comparison, but it does not replace the main weather-aware HistGradientBoosting model.

The latest PyTorch deep-learning experiment is stored in `ml/reports/deep_learning_metrics.csv`.

| Model | Scope | Window | MAE | RMSE | WAPE |
|---|---|---:|---:|---:|---:|
| Transformer encoder | all gyms pooled sequence | 12 | 7.5006 | 11.2579 | 0.1720 |
| GRU | all gyms pooled sequence | 12 | 7.6568 | 11.3203 | 0.1756 |
| LSTM | all gyms pooled sequence | 12 | 8.2176 | 12.0631 | 0.1884 |

These deep-learning models were trained with a time-respecting per-gym train/validation/test split, gym embeddings, lag/rolling feature parity, weather features, and a `log1p` target transformation. They are retained as advanced research comparisons. They do not replace the current weather-aware HistGradientBoosting model because their latest verified errors are higher.

The real-only versus real+synthetic diagnostic found that adding the current synthetic supplement worsened the real holdout MAE from `6.5896` to `7.7724`. Synthetic rows should therefore support scenario analysis and product demos, not claims of improved real-world predictive quality.

Future forecasts include `prediction_interval_low`, `prediction_interval_high`, and `uncertainty_abs_error_p80`. These are empirical uncertainty proxy bands based on historical holdout absolute error, not formal probabilistic confidence intervals.

## Limitations

- The verified real dataset covers `2026-04-15` to `2026-05-26`, not a full year.
- New Year, Christmas, Independence Day, and most major holiday periods are not present in the real holdout.
- Deep-learning results are based on the current short real observation window and should not be overgeneralized to a full-year deployment dataset.
- Weather features currently use Open-Meteo cache files. The observed gain is small on the current holdout.

Future planned models include SARIMAX with exogenous features, optional foundation forecasting experiments, additional hyperparameter tuning, and fine-tuning/RAG work for the assistant component.
