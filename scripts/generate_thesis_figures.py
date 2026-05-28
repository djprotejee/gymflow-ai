from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "ml" / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"


def save_model_comparison() -> None:
    metrics_path = REPORTS_DIR / "ml_experiment_metrics.csv"
    if not metrics_path.exists():
        return
    df = pd.read_csv(metrics_path).sort_values("mae")
    plt.figure(figsize=(9, 5))
    plt.barh(df["model"], df["mae"], color="#ff7a2d")
    plt.xlabel("MAE")
    plt.ylabel("Model")
    plt.title("Forecasting model comparison")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "model_comparison_mae.png", dpi=180)
    plt.close()


def save_error_by_hour() -> None:
    error_path = REPORTS_DIR / "error_by_hour.csv"
    if not error_path.exists():
        return
    df = pd.read_csv(error_path)
    plt.figure(figsize=(10, 5))
    plt.plot(df["hour"], df["mae"], marker="o", color="#ff7a2d")
    plt.xlabel("Hour of day")
    plt.ylabel("MAE")
    plt.title("Forecast error by hour")
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "error_by_hour_mae.png", dpi=180)
    plt.close()


def save_error_by_weekday() -> None:
    error_path = REPORTS_DIR / "error_by_weekday.csv"
    if not error_path.exists():
        return
    df = pd.read_csv(error_path)
    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    labels = [weekday_names[int(value)] for value in df["day_of_week"]]
    plt.figure(figsize=(8, 5))
    plt.bar(labels, df["mae"], color="#00d9a4")
    plt.xlabel("Weekday")
    plt.ylabel("MAE")
    plt.title("Forecast error by weekday")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "error_by_weekday_mae.png", dpi=180)
    plt.close()


def save_forecast_sample() -> None:
    predictions_path = REPORTS_DIR / "ml_predictions_sample.csv"
    if not predictions_path.exists():
        return
    df = pd.read_csv(predictions_path, parse_dates=["timestamp"])
    gym_id = df["gym_id"].value_counts().index[0]
    sample = df[df["gym_id"] == gym_id].sort_values("timestamp").tail(120)
    plt.figure(figsize=(12, 5))
    plt.plot(sample["timestamp"], sample["active_people"], label="Actual", color="#00d9a4")
    plt.plot(sample["timestamp"], sample["pred_hist_gradient_boosting"], label="Predicted", color="#ff7a2d")
    plt.xlabel("Timestamp")
    plt.ylabel("Active people")
    plt.title(f"Actual vs predicted occupancy for {gym_id}")
    plt.legend()
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "forecast_actual_vs_predicted.png", dpi=180)
    plt.close()


def save_deep_model_comparison() -> None:
    metrics_path = REPORTS_DIR / "deep_learning_metrics.csv"
    if not metrics_path.exists():
        return
    df = pd.read_csv(metrics_path).sort_values("mae")
    plt.figure(figsize=(8, 4.6))
    plt.barh(df["model"], df["mae"], color="#6ea8fe")
    plt.xlabel("MAE")
    plt.ylabel("PyTorch model")
    plt.title("Deep sequence model comparison")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "deep_model_comparison_mae.png", dpi=180)
    plt.close()


def save_deep_forecast_sample() -> None:
    predictions_path = REPORTS_DIR / "deep_learning_predictions_sample.csv"
    if not predictions_path.exists():
        return
    df = pd.read_csv(predictions_path, parse_dates=["timestamp"])
    prediction_columns = [column for column in df.columns if column.startswith("pred_")]
    if not prediction_columns:
        return
    best_column = prediction_columns[-1]
    metrics_path = REPORTS_DIR / "deep_learning_metrics.csv"
    if metrics_path.exists():
        metrics_df = pd.read_csv(metrics_path).sort_values("mae")
        if not metrics_df.empty:
            best_column = f'pred_{metrics_df.iloc[0]["model"]}'
    if best_column not in df.columns:
        return
    gym_id = df["gym_id"].value_counts().index[0]
    sample = df[df["gym_id"] == gym_id].sort_values("timestamp").tail(120)
    plt.figure(figsize=(12, 5))
    plt.plot(sample["timestamp"], sample["actual_active_people"], label="Actual", color="#00d9a4")
    plt.plot(sample["timestamp"], sample[best_column], label=best_column.replace("pred_", "Predicted "), color="#6ea8fe")
    plt.xlabel("Timestamp")
    plt.ylabel("Active people")
    plt.title(f"Deep model actual vs predicted occupancy for {gym_id}")
    plt.legend()
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "deep_forecast_actual_vs_predicted.png", dpi=180)
    plt.close()


def save_registry_model_comparison() -> None:
    registry_path = REPORTS_DIR / "model_registry.csv"
    if not registry_path.exists():
        return
    df = pd.read_csv(registry_path)
    df["mae"] = pd.to_numeric(df["mae"], errors="coerce")
    plot_df = df.dropna(subset=["mae"]).sort_values("mae").head(14)
    if plot_df.empty:
        return
    labels = plot_df["family"].astype(str) + ": " + plot_df["model"].astype(str)
    plt.figure(figsize=(11, 6))
    plt.barh(labels, plot_df["mae"], color="#ff7a2d")
    plt.xlabel("MAE")
    plt.ylabel("Experiment")
    plt.title("Unified forecasting experiment registry")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "model_registry_mae.png", dpi=180)
    plt.close()


def save_synthetic_training_comparison() -> None:
    metrics_path = REPORTS_DIR / "synthetic_training_metrics.csv"
    if not metrics_path.exists():
        return
    df = pd.read_csv(metrics_path).sort_values("mae")
    plt.figure(figsize=(8, 4.6))
    plt.barh(df["experiment"], df["mae"], color="#00d9a4")
    plt.xlabel("MAE on real holdout")
    plt.ylabel("Training setup")
    plt.title("Real-only vs real+synthetic training")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "synthetic_training_mae.png", dpi=180)
    plt.close()


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    save_model_comparison()
    save_error_by_hour()
    save_error_by_weekday()
    save_forecast_sample()
    save_deep_model_comparison()
    save_deep_forecast_sample()
    save_registry_model_comparison()
    save_synthetic_training_comparison()
    print({"figures_dir": str(FIGURES_DIR)})


if __name__ == "__main__":
    main()
