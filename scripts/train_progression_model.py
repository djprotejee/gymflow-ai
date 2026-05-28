from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import joblib
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.app.database import SessionLocal
from apps.api.app.models import WorkoutSetORM
from apps.api.app.services.progression import (
    SetObservation,
    _predict_next_set_policy,
    build_progression_feature_row,
)


ARTIFACT_PATH = ROOT / "ml" / "models" / "artifacts" / "progression_next_set_model.joblib"
REPORT_JSON = ROOT / "ml" / "reports" / "progression_supervised_metrics.json"
REPORT_MD = ROOT / "ml" / "reports" / "progression_supervised_report.md"
REPORT_CSV = ROOT / "ml" / "reports" / "progression_supervised_metrics.csv"
PREDICTIONS_CSV = ROOT / "ml" / "reports" / "progression_supervised_predictions.csv"
MODEL_VERSION = "progression_v3_supervised_next_set"


def load_rows(user_id: str = "demo") -> list[WorkoutSetORM]:
    with SessionLocal() as session:
        return session.query(WorkoutSetORM).filter(WorkoutSetORM.user_id == user_id).order_by(
            WorkoutSetORM.exercise.asc(),
            WorkoutSetORM.performed_at.asc(),
            WorkoutSetORM.set_index.asc(),
        ).all()


def build_cases(rows: list[WorkoutSetORM]) -> list[dict[str, Any]]:
    by_exercise: dict[str, list[WorkoutSetORM]] = defaultdict(list)
    for row in rows:
        by_exercise[row.exercise].append(row)

    cases: list[dict[str, Any]] = []
    for exercise, exercise_rows in by_exercise.items():
        by_day: dict[str, list[WorkoutSetORM]] = defaultdict(list)
        for row in exercise_rows:
            by_day[row.performed_at[:10]].append(row)
        history_rows: list[WorkoutSetORM] = []
        for day in sorted(by_day):
            actual_rows = sorted(by_day[day], key=lambda item: item.set_index)
            if history_rows:
                history = [
                    SetObservation(
                        exercise=item.exercise,
                        weight_kg=item.weight_kg,
                        reps=item.reps,
                        set_index=item.set_index,
                        performed_at=item.performed_at,
                    )
                    for item in history_rows
                ]
                current_session: list[SetObservation] = []
                for actual in actual_rows:
                    features = build_progression_feature_row(
                        exercise=exercise,
                        history=history,
                        set_index=actual.set_index,
                        current_session=current_session,
                        preferred_rep_mode="auto",
                        preferred_rep_min=8,
                        preferred_rep_max=10,
                    )
                    policy = _predict_next_set_policy(
                        exercise=exercise,
                        history=history,
                        set_index=actual.set_index,
                        current_session=current_session,
                        preferred_rep_mode="auto",
                        preferred_rep_min=8,
                        preferred_rep_max=10,
                    )
                    cases.append(
                        {
                            "exercise": exercise,
                            "day": day,
                            "set_index": actual.set_index,
                            "features": features,
                            "actual_weight_kg": float(actual.weight_kg),
                            "actual_reps": int(actual.reps),
                            "policy_weight_kg": float(policy.target_weight_kg),
                            "policy_reps": int(policy.target_reps),
                            "policy_reps_min": int(policy.target_reps_min),
                            "policy_reps_max": int(policy.target_reps_max),
                            "policy_strategy": policy.strategy,
                        }
                    )
                    current_session.append(
                        SetObservation(
                            exercise=actual.exercise,
                            weight_kg=actual.weight_kg,
                            reps=actual.reps,
                            set_index=actual.set_index,
                            performed_at=actual.performed_at,
                        )
                    )
            history_rows.extend(actual_rows)
    return sorted(cases, key=lambda item: (item["day"], item["exercise"], item["set_index"]))


def split_cases(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(cases) < 10:
        raise RuntimeError("Not enough progression cases to train a supervised model.")
    split_index = max(1, int(len(cases) * 0.75))
    return cases[:split_index], cases[split_index:]


def model_candidates() -> dict[str, Pipeline]:
    return {
        "ridge": Pipeline(
            [
                ("features", DictVectorizer(sparse=False)),
                ("model", Ridge(alpha=1.0)),
            ]
        ),
        "random_forest": Pipeline(
            [
                ("features", DictVectorizer(sparse=False)),
                ("model", RandomForestRegressor(n_estimators=240, min_samples_leaf=2, random_state=42)),
            ]
        ),
        "extra_trees": Pipeline(
            [
                ("features", DictVectorizer(sparse=False)),
                ("model", ExtraTreesRegressor(n_estimators=240, min_samples_leaf=2, random_state=42)),
            ]
        ),
    }


def evaluate_predictions(cases: list[dict[str, Any]], predictions: list[tuple[float, float]]) -> dict[str, float]:
    y_weight = [float(row["actual_weight_kg"]) for row in cases]
    y_reps = [float(row["actual_reps"]) for row in cases]
    pred_weight = [max(0.0, float(item[0])) for item in predictions]
    pred_reps = [max(1.0, float(item[1])) for item in predictions]
    rounded_reps = [int(round(value)) for value in pred_reps]
    range_hits = [
        int(max(1, rep - 1) <= int(row["actual_reps"]) <= min(30, rep + 1))
        for row, rep in zip(cases, rounded_reps, strict=False)
    ]
    return {
        "weight_mae_kg": round(mean_absolute_error(y_weight, pred_weight), 3),
        "weight_rmse_kg": round(mean_squared_error(y_weight, pred_weight) ** 0.5, 3),
        "reps_mae": round(mean_absolute_error(y_reps, pred_reps), 3),
        "reps_rmse": round(mean_squared_error(y_reps, pred_reps) ** 0.5, 3),
        "rep_range_hit_rate": round(sum(range_hits) / max(1, len(range_hits)), 3),
    }


def evaluate_policy(cases: list[dict[str, Any]]) -> dict[str, float]:
    predictions = [(float(row["policy_weight_kg"]), float(row["policy_reps"])) for row in cases]
    metrics = evaluate_predictions(cases, predictions)
    range_hits = [
        int(int(row["policy_reps_min"]) <= int(row["actual_reps"]) <= int(row["policy_reps_max"]))
        for row in cases
    ]
    metrics["rep_range_hit_rate"] = round(sum(range_hits) / max(1, len(range_hits)), 3)
    return metrics


def write_prediction_sample(cases: list[dict[str, Any]], predictions: list[tuple[float, float]]) -> None:
    lines = ["day,exercise,set_index,actual_weight_kg,pred_weight_kg,policy_weight_kg,actual_reps,pred_reps,policy_reps"]
    for row, prediction in list(zip(cases, predictions, strict=False))[:120]:
        lines.append(
            ",".join(
                [
                    str(row["day"]),
                    str(row["exercise"]).replace(",", " "),
                    str(row["set_index"]),
                    str(row["actual_weight_kg"]),
                    str(round(float(prediction[0]), 3)),
                    str(row["policy_weight_kg"]),
                    str(row["actual_reps"]),
                    str(round(float(prediction[1]), 3)),
                    str(row["policy_reps"]),
                ]
            )
        )
    PREDICTIONS_CSV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def hybrid_predictions(cases: list[dict[str, Any]], weight_predictions: list[tuple[float, float]], reps_predictions: list[tuple[float, float]] | None) -> list[tuple[float, float]]:
    if reps_predictions is None:
        return [(float(prediction[0]), float(row["policy_reps"])) for row, prediction in zip(cases, weight_predictions, strict=False)]
    return [(float(weight_prediction[0]), float(reps_prediction[1])) for weight_prediction, reps_prediction in zip(weight_predictions, reps_predictions, strict=False)]


def main() -> None:
    rows = load_rows()
    cases = build_cases(rows)
    train_cases, test_cases = split_cases(cases)
    x_train = [row["features"] for row in train_cases]
    y_train = [[row["actual_weight_kg"], row["actual_reps"]] for row in train_cases]
    x_test = [row["features"] for row in test_cases]

    rows_by_model: dict[str, dict[str, float]] = {"policy_baseline": evaluate_policy(test_cases)}
    fitted_models: dict[str, Pipeline] = {}
    predictions_by_model: dict[str, list[tuple[float, float]]] = {}

    for model_name, model in model_candidates().items():
        model.fit(x_train, y_train)
        raw_predictions = model.predict(x_test)
        predictions = [(float(row[0]), float(row[1])) for row in raw_predictions]
        fitted_models[model_name] = model
        predictions_by_model[model_name] = predictions
        rows_by_model[model_name] = evaluate_predictions(test_cases, predictions)

    def score(metrics: dict[str, float]) -> float:
        return metrics["weight_mae_kg"] + metrics["reps_mae"] * 2.0 - metrics["rep_range_hit_rate"]

    best_weight_name = min((name for name in rows_by_model if name != "policy_baseline"), key=lambda item: rows_by_model[item]["weight_mae_kg"])
    best_reps_name = min((name for name in rows_by_model if name != "policy_baseline"), key=lambda item: rows_by_model[item]["reps_mae"])
    use_policy_reps = rows_by_model["policy_baseline"]["reps_mae"] <= rows_by_model[best_reps_name]["reps_mae"]
    selected_name = f"hybrid_{best_weight_name}_weight_{'policy' if use_policy_reps else best_reps_name}_reps"
    selected_predictions = hybrid_predictions(
        test_cases,
        predictions_by_model[best_weight_name],
        None if use_policy_reps else predictions_by_model[best_reps_name],
    )
    rows_by_model[selected_name] = evaluate_predictions(test_cases, selected_predictions)
    if use_policy_reps:
        rows_by_model[selected_name]["rep_range_hit_rate"] = rows_by_model["policy_baseline"]["rep_range_hit_rate"]
    best_metrics = rows_by_model[selected_name]
    confidence = round(max(0.55, min(0.86, 1.0 - score(best_metrics) / 25.0)), 3)

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model_version": MODEL_VERSION,
            "model_name": selected_name,
            "weight_model_name": best_weight_name,
            "reps_model_name": None if use_policy_reps else best_reps_name,
            "reps_source": "policy_guardrail" if use_policy_reps else "supervised_regressor",
            "model": fitted_models[best_weight_name],
            "reps_model": None if use_policy_reps else fitted_models[best_reps_name],
            "metrics": best_metrics,
            "policy_baseline_metrics": rows_by_model["policy_baseline"],
            "confidence": confidence,
            "strategy": "supervised_weight_policy_reps" if use_policy_reps else "supervised_next_set_regressor",
            "reason": "Supervised model predicts target load from personal set history; reps remain under policy guardrails because the policy performed better on held-out rep targets." if use_policy_reps else "Supervised model predicts target load and reps from personal set history, same-session fatigue, estimated strength trend, and selected rep policy.",
            "feature_contract": "apps.api.app.services.progression.build_progression_feature_row",
        },
        ARTIFACT_PATH,
    )
    write_prediction_sample(test_cases, selected_predictions)

    report = {
        "model_version": MODEL_VERSION,
        "dataset": {
            "user_id": "demo",
            "workout_sets": len(rows),
            "cases": len(cases),
            "train_cases": len(train_cases),
            "test_cases": len(test_cases),
            "split": "chronological_75_25",
        },
        "selected_model": selected_name,
        "weight_model": best_weight_name,
        "reps_model": None if use_policy_reps else best_reps_name,
        "reps_source": "policy_guardrail" if use_policy_reps else "supervised_regressor",
        "selection_score": round(score(best_metrics), 3),
        "artifact": str(ARTIFACT_PATH.relative_to(ROOT)),
        "prediction_sample": str(PREDICTIONS_CSV.relative_to(ROOT)),
        "metrics": rows_by_model,
        "note": "Supervised next-set regression trained on deterministic demo workout history. Use as a thesis/product artifact, not a clinical prescription.",
    }
    REPORT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    csv_lines = ["model,scope,train_rows,test_rows,mae,rmse,wape,reps_mae,reps_rmse,rep_range_hit_rate"]
    for name, metrics in sorted(rows_by_model.items(), key=lambda item: score(item[1])):
        csv_lines.append(
            ",".join(
                [
                    name,
                    "next_set_progression",
                    str(len(train_cases)),
                    str(len(test_cases)),
                    str(metrics["weight_mae_kg"]),
                    str(metrics["weight_rmse_kg"]),
                    "",
                    str(metrics["reps_mae"]),
                    str(metrics["reps_rmse"]),
                    str(metrics["rep_range_hit_rate"]),
                ]
            )
        )
    REPORT_CSV.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
    lines = [
        "# Supervised Progression Model",
        "",
        f"- Model version: `{MODEL_VERSION}`",
        f"- Selected model: `{selected_name}`",
        f"- Weight model: `{best_weight_name}`",
        f"- Reps source: `{'policy_guardrail' if use_policy_reps else best_reps_name}`",
        f"- Artifact: `{report['artifact']}`",
        f"- Dataset: `{len(rows)}` workout sets, `{len(cases)}` supervised cases",
        f"- Split: `{report['dataset']['split']}`, train `{len(train_cases)}`, test `{len(test_cases)}`",
        "",
        "| Model | Weight MAE kg | Weight RMSE kg | Reps MAE | Reps RMSE | Rep range hit-rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in sorted(rows_by_model.items(), key=lambda item: score(item[1])):
        lines.append(
            f"| {name} | {metrics['weight_mae_kg']} | {metrics['weight_rmse_kg']} | {metrics['reps_mae']} | {metrics['reps_rmse']} | {metrics['rep_range_hit_rate']} |"
        )
    lines.extend(["", str(report["note"]), ""])
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
