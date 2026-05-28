# Feature Ablation Report

Date: 2026-05-23

## Purpose

This experiment evaluates how different feature groups affect gym occupancy forecasting quality on the canonical 2026 occupancy dataset.

## Data

- Dataset: `data/processed/occupancy_features.csv`
- Split: time-respecting 80/20 split per gym
- Model: HistGradientBoostingRegressor
- Metrics: MAE, RMSE, WAPE

## Result Summary

Best feature group: `calendar_lag` with MAE `6.3751`, RMSE `9.4323`, WAPE `0.1452`.

Weakest feature group: `rolling_only` with MAE `12.4207`, RMSE `17.9005`, WAPE `0.283`.

## Full Table

| Feature group | MAE | RMSE | WAPE |
|---|---:|---:|---:|
| calendar_lag | 6.3751 | 9.4323 | 0.1452 |
| calendar_holiday_lag | 6.5747 | 9.789 | 0.1498 |
| all_features | 6.5896 | 9.7668 | 0.1501 |
| lag_rolling | 7.7067 | 11.6886 | 0.1756 |
| lag_only | 7.7534 | 11.7877 | 0.1766 |
| calendar_rolling | 8.3731 | 11.6775 | 0.1908 |
| calendar_only | 10.1653 | 14.1 | 0.2316 |
| calendar_holiday | 10.3694 | 14.2421 | 0.2362 |
| rolling_only | 12.4207 | 17.9005 | 0.283 |

## Interpretation

The ablation isolates the contribution of calendar, lag, and rolling-window features while keeping gym identity features available in every run. The result should be used in the thesis to justify the final forecasting feature set instead of presenting the model as a black box.

## Figure

`ml/reports/figures/feature_ablation_mae.png`
