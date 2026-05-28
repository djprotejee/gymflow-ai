# ADR 0001 - Select a tabular gradient-boosting model as the main forecasting artifact

## Status

Accepted - 2026-05-24

## Context

The thesis focuses on forecasting gym occupancy for a personalized training process. The project evaluated multiple model families: linear regression, random forest, HistGradientBoosting, ARIMA/SARIMAX, compact sequence MLP, and PyTorch sequence models.

## Decision

Use the weather-aware `HistGradientBoostingRegressor` pipeline as the main production forecasting artifact for the current project state.

## Rationale

- It delivers the strongest validated pooled regression quality among the operationally integrated models in the current pipeline.
- It performs better than the current deep sequence models on the available real holdout.
- It is cheaper to retrain and easier to explain than the heavier sequence models.
- It fits the current dataset size better than the deep-learning branch.

## Consequences

- Deep models remain part of the scientific comparison, not the deployed default.
- The thesis can make an evidence-based argument that higher model complexity was evaluated and rejected for the current data regime.
