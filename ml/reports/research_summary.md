# Research Summary

Date: 2026-05-24

## Core Findings

1. Best pooled tabular model: `hist_gradient_boosting` with MAE `6.5723`, RMSE `9.7546`, WAPE `0.1497`.
2. Best deep sequence model: `transformer_sequence_torch` with MAE `7.5006`, RMSE `11.2579`, WAPE `0.172`.
3. Best feature-group ablation: `calendar_lag` with MAE `6.3751`.
4. Weather improves MAE by `0.0173` compared with the no-weather baseline.
5. Adding the current synthetic supplement changes MAE by `+1.1828` on the real holdout.
6. Best registry row by MAE: `hybrid_ridge_weight_policy_reps` from `training_progression` with MAE `5.997`.

## Interpretation

- The current operational forecasting choice remains the weather-aware HistGradientBoosting model because it is the strongest validated production-ready tabular path.
- The best deep sequence model remains worse than the best tabular baseline by `0.9283` MAE on the current real holdout.
- Weather is useful but modest.
- Synthetic data is currently defensible as scenario support and stress-test augmentation, not as empirical quality improvement.
- The feature-ablation study shows that calendar and lag features carry the largest share of predictive signal on the current dataset.

## Thesis Use

- Use this file as the single source for the concluding experimental narrative.
- Cross-reference `ml/reports/ml_experiment_metrics.csv`, `ml/reports/deep_learning_metrics.csv`, `ml/reports/feature_ablation_metrics.csv`, `ml/reports/synthetic_training_metrics.csv`, and `ml/reports/weather_ablation_metrics.csv` for detailed tables.
