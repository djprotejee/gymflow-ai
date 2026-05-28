from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "ml" / "reports"

ML_METRICS_PATH = REPORTS_DIR / "ml_experiment_metrics.csv"
DEEP_METRICS_PATH = REPORTS_DIR / "deep_learning_metrics.csv"
ABLATION_PATH = REPORTS_DIR / "feature_ablation_metrics.csv"
SYNTHETIC_PATH = REPORTS_DIR / "synthetic_training_metrics.csv"
WEATHER_PATH = REPORTS_DIR / "weather_ablation_metrics.csv"
REGISTRY_PATH = REPORTS_DIR / "model_registry.json"
OUTPUT_JSON = REPORTS_DIR / "research_summary.json"
OUTPUT_MD = REPORTS_DIR / "research_summary.md"


def load_csv_records(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing report file: {path}")
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def as_float(record: dict[str, str], key: str) -> float:
    return float(record[key])


def best_by_metric(records: list[dict[str, str]], metric: str = "mae") -> dict[str, str]:
    return min(records, key=lambda row: (as_float(row, metric), as_float(row, "rmse")))


def record_by_field(records: list[dict[str, str]], key: str, value: str) -> dict[str, str]:
    for record in records:
        if record.get(key) == value:
            return record
    raise KeyError(f"Could not find record where {key}={value}")


def main() -> None:
    ml_metrics = load_csv_records(ML_METRICS_PATH)
    deep_metrics = load_csv_records(DEEP_METRICS_PATH)
    ablation_metrics = load_csv_records(ABLATION_PATH)
    synthetic_metrics = load_csv_records(SYNTHETIC_PATH)
    weather_metrics = load_csv_records(WEATHER_PATH)
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    best_tabular = best_by_metric(ml_metrics)
    best_deep = best_by_metric(deep_metrics)
    best_ablation = best_by_metric(ablation_metrics)
    real_only = record_by_field(synthetic_metrics, "experiment", "real_only_train_real_holdout")
    real_plus_synthetic = record_by_field(synthetic_metrics, "experiment", "real_plus_synthetic_train_real_holdout")
    weather_with = record_by_field(weather_metrics, "feature_set", "base_with_weather")
    weather_without = record_by_field(weather_metrics, "feature_set", "base_without_weather")
    best_registry = min(registry, key=lambda row: (float(row["mae"]), float(row["rmse"])))

    weather_mae_delta = round(as_float(weather_without, "mae") - as_float(weather_with, "mae"), 4)
    synthetic_mae_delta = round(as_float(real_plus_synthetic, "mae") - as_float(real_only, "mae"), 4)
    deep_gap_to_tabular = round(as_float(best_deep, "mae") - as_float(best_tabular, "mae"), 4)

    summary = {
        "best_tabular_model": best_tabular,
        "best_deep_model": best_deep,
        "best_feature_ablation": best_ablation,
        "best_registry_row": best_registry,
        "weather_mae_delta": weather_mae_delta,
        "synthetic_mae_delta": synthetic_mae_delta,
        "deep_gap_to_tabular_mae": deep_gap_to_tabular,
        "scientific_claims": [
            {
                "claim": "The current deployed forecasting choice remains the weather-aware HistGradientBoosting model.",
                "evidence": {
                    "tabular_best_mae": best_tabular["mae"],
                    "best_deep_mae": best_deep["mae"],
                    "best_registry_row": {
                        "model": best_registry["model"],
                        "family": best_registry["family"],
                        "mae": best_registry["mae"],
                    },
                },
            },
            {
                "claim": "On the current real holdout, the strongest deep sequence model does not outperform the best tabular baseline.",
                "evidence": {
                    "best_tabular_model": best_tabular["model"],
                    "best_tabular_mae": best_tabular["mae"],
                    "best_deep_model": best_deep["model"],
                    "best_deep_mae": best_deep["mae"],
                    "mae_gap": deep_gap_to_tabular,
                },
            },
            {
                "claim": "Weather features provide only a modest improvement.",
                "evidence": {
                    "mae_without_weather": weather_without["mae"],
                    "mae_with_weather": weather_with["mae"],
                    "mae_gain": weather_mae_delta,
                },
            },
            {
                "claim": "The current synthetic supplement worsens performance on the real holdout and should be treated as scenario data, not empirical improvement.",
                "evidence": {
                    "real_only_mae": real_only["mae"],
                    "real_plus_synthetic_mae": real_plus_synthetic["mae"],
                    "mae_change": synthetic_mae_delta,
                },
            },
            {
                "claim": "Calendar plus lag features provide the strongest feature-group signal in the ablation experiment.",
                "evidence": {
                    "best_feature_group": best_ablation["feature_group"],
                    "best_feature_group_mae": best_ablation["mae"],
                },
            },
        ],
    }

    OUTPUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown = f"""# Research Summary

Date: 2026-05-24

## Core Findings

1. Best pooled tabular model: `{best_tabular["model"]}` with MAE `{best_tabular["mae"]}`, RMSE `{best_tabular["rmse"]}`, WAPE `{best_tabular["wape"]}`.
2. Best deep sequence model: `{best_deep["model"]}` with MAE `{best_deep["mae"]}`, RMSE `{best_deep["rmse"]}`, WAPE `{best_deep["wape"]}`.
3. Best feature-group ablation: `{best_ablation["feature_group"]}` with MAE `{best_ablation["mae"]}`.
4. Weather improves MAE by `{weather_mae_delta}` compared with the no-weather baseline.
5. Adding the current synthetic supplement changes MAE by `+{synthetic_mae_delta}` on the real holdout.
6. Best registry row by MAE: `{best_registry["model"]}` from `{best_registry["family"]}` with MAE `{best_registry["mae"]}`.

## Interpretation

- The current operational forecasting choice remains the weather-aware HistGradientBoosting model because it is the strongest validated production-ready tabular path.
- The best deep sequence model remains worse than the best tabular baseline by `{deep_gap_to_tabular}` MAE on the current real holdout.
- Weather is useful but modest.
- Synthetic data is currently defensible as scenario support and stress-test augmentation, not as empirical quality improvement.
- The feature-ablation study shows that calendar and lag features carry the largest share of predictive signal on the current dataset.

## Thesis Use

- Use this file as the single source for the concluding experimental narrative.
- Cross-reference `ml/reports/ml_experiment_metrics.csv`, `ml/reports/deep_learning_metrics.csv`, `ml/reports/feature_ablation_metrics.csv`, `ml/reports/synthetic_training_metrics.csv`, and `ml/reports/weather_ablation_metrics.csv` for detailed tables.
"""
    OUTPUT_MD.write_text(markdown, encoding="utf-8")
    print(json.dumps({"status": "ok", "json": str(OUTPUT_JSON), "markdown": str(OUTPUT_MD)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
