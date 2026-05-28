# Forecasting Research Plan

## Goal

Compare multiple forecasting approaches for gym occupancy prediction and use the best defensible model family in the GymFlow AI application.

## Model Families

1. Baseline models:
   - previous observation;
   - rolling mean;
   - daily seasonal lag.
2. Calendar profile:
   - gym + weekday + hour aggregate profile.
3. Regression models:
   - Ridge regression with calendar, lag, rolling, and categorical gym features.
4. Tree-based ML:
   - Random Forest;
   - Histogram Gradient Boosting;
   - optional XGBoost or LightGBM.
5. Statistical time-series models:
   - ARIMA;
   - SARIMAX for selected gym series.
6. Neural forecasting:
   - LSTM or GRU if runtime and data volume allow.
7. Advanced research candidates:
   - Transformer-based forecasting;
   - time-series foundation model;
   - hybrid or ensemble approach.

## Evaluation Protocol

- Use time-respecting train/test splits per gym.
- Avoid random shuffling for forecasting evaluation.
- Report MAE, RMSE, and WAPE.
- Add error analysis by gym, weekday, and hour.
- Compare feature groups through ablation:
  - calendar-only;
  - lag-only;
  - rolling-only;
  - calendar + lag + rolling;
  - external factors when available.

## Thesis Value

This plan supports the F3 computer science focus by comparing algorithmic approaches, feature sets, and error behavior instead of presenting only one model.
