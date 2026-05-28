from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "ml" / "reports"


def add_rows(path: Path, family: str, dataset_scope: str, rows: list[dict[str, object]]) -> None:
    if not path.exists():
        return
    df = pd.read_csv(path)
    for row in df.to_dict(orient="records"):
        if family == "feature_ablation":
            model = f'hgb_{row.get("feature_group")}'
            scope = "feature_ablation"
        elif family == "weather_ablation":
            model = f'{row.get("model")}_{row.get("feature_set")}'
            scope = "weather_ablation"
        else:
            model = row.get("model") or row.get("feature_group") or row.get("experiment")
            scope = row.get("scope") or row.get("experiment") or dataset_scope
        rows.append(
            {
                "family": family,
                "model": model,
                "target": "next_set_weight_kg" if family == "training_progression" else "occupancy_people",
                "scope": scope,
                "dataset_scope": dataset_scope,
                "train_rows": row.get("train_rows", ""),
                "test_rows": row.get("test_rows", row.get("rows", "")),
                "mae": row.get("mae", ""),
                "rmse": row.get("rmse", ""),
                "wape": row.get("wape", ""),
                "source_file": str(path.relative_to(ROOT)),
            }
        )


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    add_rows(REPORTS_DIR / "baseline_metrics.csv", "baseline", "real_holdout", rows)
    add_rows(REPORTS_DIR / "ml_experiment_metrics.csv", "tabular_ml", "real_holdout", rows)
    add_rows(REPORTS_DIR / "feature_ablation_metrics.csv", "feature_ablation", "real_holdout", rows)
    add_rows(REPORTS_DIR / "sequence_neural_metrics.csv", "sklearn_neural_sequence", "real_holdout", rows)
    add_rows(REPORTS_DIR / "deep_learning_metrics.csv", "pytorch_sequence", "real_holdout", rows)
    add_rows(REPORTS_DIR / "sarimax_metrics.csv", "statistical_exogenous", "selected_real_holdout", rows)
    add_rows(REPORTS_DIR / "weather_ablation_metrics.csv", "weather_ablation", "real_holdout", rows)
    add_rows(REPORTS_DIR / "synthetic_training_metrics.csv", "synthetic_training_diagnostic", "real_holdout", rows)
    add_rows(REPORTS_DIR / "progression_supervised_metrics.csv", "training_progression", "demo_workout_history", rows)

    registry = pd.DataFrame(rows)
    if registry.empty:
        raise FileNotFoundError("No report files found for registry.")
    registry["mae_numeric"] = pd.to_numeric(registry["mae"], errors="coerce")
    registry = registry.sort_values(["target", "mae_numeric", "family", "model"]).drop(columns=["mae_numeric"])
    registry.to_csv(REPORTS_DIR / "model_registry.csv", index=False)
    (REPORTS_DIR / "model_registry.json").write_text(
        json.dumps(registry.to_dict(orient="records"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    top = registry.groupby("target", group_keys=False).head(12)
    lines = [
        "# Unified Model Registry",
        "",
        "Date: 2026-05-24",
        "",
        "This registry consolidates available forecasting experiment metrics into one thesis-ready comparison table.",
        "",
        "| Target | Family | Model | Scope | MAE | RMSE | WAPE | Source |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for row in top.to_dict(orient="records"):
        lines.append(
            f'| {row["target"]} | {row["family"]} | {row["model"]} | {row["scope"]} | {row["mae"]} | {row["rmse"]} | {row["wape"]} | `{row["source_file"]}` |'
        )
    (REPORTS_DIR / "model_registry_report.md").write_text("\n".join(lines), encoding="utf-8")
    best_by_target = {
        target: {
            "model": str(group.iloc[0]["model"]),
            "mae": float(group.iloc[0]["mae"]),
        }
        for target, group in registry.groupby("target")
    }
    print({"rows": int(len(registry)), "best_by_target": best_by_target})


if __name__ == "__main__":
    main()
