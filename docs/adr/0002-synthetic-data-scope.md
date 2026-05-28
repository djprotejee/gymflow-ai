# ADR 0002 – Treat synthetic occupancy data as scenario support, not empirical truth

## Status

Accepted – 2026-05-24

## Context

The real dataset covers a short period in 2026. A synthetic extension was generated to support scenario demonstrations, stress testing, and future-product exploration.

## Decision

Keep synthetic occupancy rows clearly separated from real observations and do not present them as empirical improvement to the forecasting model.

## Rationale

- The real-only versus real+synthetic diagnostic shows that the current synthetic supplement worsens the real holdout metric.
- Synthetic rows are generated from project assumptions and observed profiles, not collected as real measurements.
- Mixing them into the scientific narrative as “more data” would weaken the validity of the thesis conclusions.

## Consequences

- Synthetic data can still be used for scenario demos, UI stress tests, and future-scope exploration.
- The thesis should explicitly label synthetic artifacts and discuss their limitations.
