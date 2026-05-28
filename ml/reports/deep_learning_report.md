# Deep Learning Forecasting Report

Date: 2026-05-23

This report summarizes the PyTorch sequence forecasting experiment for GymFlow AI.

## Experiment

- Script: `scripts/run_deep_forecasting_experiments.py`
- Command: `make deep`
- Optional dependency command: `make torch-setup`
- Dataset: `data/processed/occupancy_features.csv`
- Optional weather join: `data/external/weather_observation_features.csv`
- Sequence window: `12` observations
- Split: time-respecting per-gym split with `70%` train, `10%` validation, `20%` test
- Features: previous occupancy sequence, lag features, rolling features, calendar features, holiday features, weather features, current-context vector, and gym embedding
- Target transform: `log1p` before standardization, transformed back with `expm1` for evaluation
- Loss: Smooth L1 loss
- Device used in the latest local run: `cpu`

## Results

| Model | Train rows | Validation rows | Test rows | Epochs | MAE | RMSE | WAPE |
|---|---:|---:|---:|---:|---:|---:|---:|
| LSTM | 11476 | 1643 | 3286 | 8 | 8.2176 | 12.0631 | 0.1884 |
| GRU | 11476 | 1643 | 3286 | 14 | 7.6568 | 11.3203 | 0.1756 |
| Transformer encoder | 11476 | 1643 | 3286 | 14 | 7.5006 | 11.2579 | 0.1720 |

## Interpretation

The best PyTorch sequence model in this run is the Transformer encoder. It does not outperform the current weather-aware HistGradientBoosting model from `make train`, but the gap is substantially smaller after adding lag/rolling feature parity and using a shorter sequence window.

This is a useful academic result: on the current short real observation window, a heavier sequence neural architecture is not automatically better than a carefully engineered tabular model with lag, calendar, holiday, and weather features. The LSTM, GRU, and Transformer branches should therefore be presented as evaluated advanced research models, while the production MVP can keep HistGradientBoosting as the main forecasting model.

## Generated Files

- `ml/reports/deep_learning_metrics.csv`
- `ml/reports/deep_learning_metrics.json`
- `ml/reports/deep_learning_predictions_sample.csv`
- `ml/models/artifacts/lstm_sequence_torch.pt`
- `ml/models/artifacts/gru_sequence_torch.pt`
- `ml/models/artifacts/transformer_sequence_torch.pt`
