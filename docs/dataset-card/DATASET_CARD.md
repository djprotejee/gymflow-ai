# Dataset Card – GymFlow AI Occupancy Dataset

## Dataset Name

GymFlow AI Occupancy Dataset.

## Source

The project-local raw occupancy dataset is stored in:

- `data/raw/occupancy_observations_2026.csv`

This file is the canonical raw input for the current project pipeline.

## Fields

Raw fields:

- `timestamp`
- `city`
- `address`
- `active_people`

Processed fields add:

- `gym_id`
- `source_file`
- calendar features
- lag features
- rolling statistics

## Date Range

The raw dataset already uses 2026 timestamps. `scripts/prepare_data.py` validates that all raw timestamps belong to 2026 and does not perform year conversion during data preparation.

## Intended Use

The dataset is used for:

- gym occupancy forecasting;
- backtesting forecasting models;
- training-slot recommendation;
- dashboard visualization.

## Limitations

The observed period is short for proving long-term seasonal effects. Calendar and holiday effects can be engineered, but claims about long-term seasonality require either longer real observation or clearly marked synthetic scenario data.
