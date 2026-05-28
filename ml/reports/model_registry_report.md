# Unified Model Registry

Date: 2026-05-24

This registry consolidates available forecasting experiment metrics into one thesis-ready comparison table.

| Target | Family | Model | Scope | MAE | RMSE | WAPE | Source |
|---|---|---|---|---:|---:|---:|---|
| next_set_weight_kg | training_progression | hybrid_ridge_weight_policy_reps | next_set_progression | 5.997 | 13.752 | nan | `ml\reports\progression_supervised_metrics.csv` |
| next_set_weight_kg | training_progression | ridge | next_set_progression | 5.997 | 13.752 | nan | `ml\reports\progression_supervised_metrics.csv` |
| next_set_weight_kg | training_progression | extra_trees | next_set_progression | 6.175 | 12.738 | nan | `ml\reports\progression_supervised_metrics.csv` |
| next_set_weight_kg | training_progression | random_forest | next_set_progression | 6.272 | 14.196 | nan | `ml\reports\progression_supervised_metrics.csv` |
| next_set_weight_kg | training_progression | policy_baseline | next_set_progression | 6.999 | 14.247 | nan | `ml\reports\progression_supervised_metrics.csv` |
| occupancy_people | feature_ablation | hgb_calendar_lag | feature_ablation | 6.3751 | 9.4323 | 0.1452 | `ml\reports\feature_ablation_metrics.csv` |
| occupancy_people | tabular_ml | hist_gradient_boosting | all_gyms_pooled | 6.5723 | 9.7546 | 0.1497 | `ml\reports\ml_experiment_metrics.csv` |
| occupancy_people | weather_ablation | hist_gradient_boosting_base_with_weather | weather_ablation | 6.5723 | 9.7546 | 0.1497 | `ml\reports\weather_ablation_metrics.csv` |
| occupancy_people | feature_ablation | hgb_calendar_holiday_lag | feature_ablation | 6.5747 | 9.789 | 0.1498 | `ml\reports\feature_ablation_metrics.csv` |
| occupancy_people | feature_ablation | hgb_all_features | feature_ablation | 6.5896 | 9.7668 | 0.1501 | `ml\reports\feature_ablation_metrics.csv` |
| occupancy_people | synthetic_training_diagnostic | hist_gradient_boosting | real_only_train_real_holdout | 6.5896 | 9.7668 | 0.1501 | `ml\reports\synthetic_training_metrics.csv` |
| occupancy_people | weather_ablation | hist_gradient_boosting_base_without_weather | weather_ablation | 6.5896 | 9.7668 | 0.1501 | `ml\reports\weather_ablation_metrics.csv` |
| occupancy_people | tabular_ml | random_forest | all_gyms_pooled | 7.1203 | 10.522 | 0.1622 | `ml\reports\ml_experiment_metrics.csv` |
| occupancy_people | pytorch_sequence | transformer_sequence_torch | all_gyms_pooled_sequence | 7.5006 | 11.2579 | 0.172 | `ml\reports\deep_learning_metrics.csv` |
| occupancy_people | pytorch_sequence | gru_sequence_torch | all_gyms_pooled_sequence | 7.6568 | 11.3203 | 0.1756 | `ml\reports\deep_learning_metrics.csv` |
| occupancy_people | feature_ablation | hgb_lag_rolling | feature_ablation | 7.7067 | 11.6886 | 0.1756 | `ml\reports\feature_ablation_metrics.csv` |
| occupancy_people | feature_ablation | hgb_lag_only | feature_ablation | 7.7534 | 11.7877 | 0.1766 | `ml\reports\feature_ablation_metrics.csv` |