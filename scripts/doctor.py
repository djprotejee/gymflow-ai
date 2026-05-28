from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CRITICAL_FILES = [
    "README.md",
    "Makefile",
    "requirements.txt",
    "docker-compose.yml",
    ".env.example",
    "apps/api/app/ai_provider.py",
    "apps/api/app/main.py",
    "apps/web/package.json",
    "data/raw/occupancy_observations_2026.csv",
    "data/processed/occupancy_observations.csv",
    "data/processed/occupancy_features.csv",
    "ml/reports/ml_experiment_metrics.csv",
    "ml/reports/future_forecast_7d.csv",
    "scripts/import_exercise_source.py",
]

OPTIONAL_FILES = [
    "ml/models/artifacts/hist_gradient_boosting.joblib",
    "ml/reports/figures/model_comparison_mae.png",
    "data/external/weather_future_features.csv",
    "data/external/weather_observation_features.csv",
    "data/external/city_coordinates.json",
    "ml/reports/weather_feature_summary.json",
    "ml/reports/weather_observation_feature_summary.json",
    "ml/reports/weather_ablation_metrics.csv",
    "ml/reports/sequence_neural_metrics.csv",
    "ml/reports/deep_learning_metrics.csv",
    "ml/reports/sarimax_metrics.csv",
    "ml/reports/synthetic_training_metrics.csv",
    "ml/reports/model_registry.csv",
    "ml/reports/figures/deep_model_comparison_mae.png",
    "ml/reports/figures/model_registry_mae.png",
    "ml/models/artifacts/lstm_sequence_torch.pt",
    "ml/models/artifacts/gru_sequence_torch.pt",
    "ml/models/artifacts/transformer_sequence_torch.pt",
    "apps/web/node_modules",
    ".venv",
]

PYTHON_PACKAGES = [
    "fastapi",
    "pandas",
    "numpy",
    "sklearn",
    "statsmodels",
    "joblib",
    "matplotlib",
    "sqlalchemy",
]


def exists(path: str) -> bool:
    return (ROOT / path).exists()


def package_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> None:
    missing_critical = [path for path in CRITICAL_FILES if not exists(path)]
    missing_optional = [path for path in OPTIONAL_FILES if not exists(path)]
    missing_packages = [name for name in PYTHON_PACKAGES if not package_available(name)]

    tools = {
        "python": sys.version.split()[0],
        "make": shutil.which("make") is not None,
        "docker": shutil.which("docker") is not None,
        "docker-compose": shutil.which("docker-compose") is not None,
        "npm": shutil.which("npm") is not None or shutil.which("npm.cmd") is not None,
    }

    status = "ok"
    if missing_critical or missing_packages:
        status = "fail"
    elif missing_optional or not all(tools.values()):
        status = "warn"

    payload = {
        "status": status,
        "project_root": str(ROOT),
        "missing_critical": missing_critical,
        "missing_optional": missing_optional,
        "missing_python_packages": missing_packages,
        "tools": tools,
        "recommended_resume_commands": [
            "make doctor",
            "make data",
            "make train",
            "make future",
            "make weather",
            "make weather-observed",
            "make weather-ablation",
            "make sequence",
            "make torch-setup",
            "make deep",
            "make sarimax",
            "make synthetic-experiment",
            "make registry",
            "make validate",
            "make test",
            "make smoke",
            "make build",
        ],
        "docker_resume_commands": [
            "make docker-up-d",
            "make docker-smoke",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(1 if status == "fail" else 0)


if __name__ == "__main__":
    main()
