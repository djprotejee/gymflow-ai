# ADR 0003 – Keep weather as a modest exogenous feature branch

## Status

Accepted – 2026-05-24

## Context

The project integrates Open-Meteo data for both observation-period weather and future-horizon weather forecasts. Weather features were evaluated through a dedicated ablation experiment.

## Decision

Retain weather features in the main forecasting pipeline, but describe them as a modest auxiliary signal rather than the core predictive driver.

## Rationale

- The weather/no-weather ablation shows a small but positive MAE improvement.
- The improvement is real enough to justify keeping the branch.
- The gain is not large enough to claim that weather dominates occupancy behavior.

## Consequences

- The thesis can present weather as an evidence-based external factor.
- The main scientific story remains centered on calendar, lag, and operational demand patterns.
