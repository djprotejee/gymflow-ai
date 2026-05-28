# Synthetic Data Card - GymFlow AI Scenario Extension

Date: 2026-05-23

## Purpose

The synthetic dataset extends the real GymFlow AI occupancy observations for scenario testing, future-horizon demonstrations, robustness checks, and model-development experiments.

It must not be described as directly collected gym traffic. It is generated from the empirical April-May 2026 occupancy profiles.

## Real Empirical Basis

Current verified project dataset:

- rows: `16597`
- gyms: `16`
- date range: `2026-04-15 16:00:14` to `2026-05-26 11:06:27`
- median observation interval: approximately `20` minutes

Source artifact: `ml/reports/data_summary.json`.

## Generated Files

```text
data/synthetic/occupancy_synthetic_6m.csv
data/processed/occupancy_research_extended.csv
data/processed/occupancy_research_features.csv
ml/reports/synthetic_data_summary.json
```

## Generation Method

The generator uses:

- gym-specific historical profiles;
- day-of-week and hour-of-day means;
- residual bootstrap noise from real observations;
- weekend multipliers;
- encoded network opening hours: weekdays `07:00-22:00`, weekends `09:00-18:00`;
- 2026 Ukrainian public-holiday and major low-traffic holiday multipliers;
- closed-holiday zero-traffic rules for configured major holidays;
- broad seasonal multipliers;
- deterministic random seed `42`.

Implementation: `scripts/generate_synthetic_occupancy.py`.

## Research Use

Recommended experiment framing:

1. Real-only training and real-only testing for primary empirical claims.
2. Synthetic-only or real+synthetic training as a scenario experiment.
3. Real holdout testing as the main comparison target.

## Academic Constraint

In the thesis, claims based on real observations must be separated from claims based on synthetic scenario data. The synthetic extension can support stress testing and product demonstration, but it cannot be presented as a real six-month collection period.
