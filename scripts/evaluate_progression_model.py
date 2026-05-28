from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.app.database import SessionLocal
from apps.api.app.models import WorkoutSetORM
from apps.api.app.services.progression import SetObservation, predict_next_set


REPORT_JSON = ROOT / "ml" / "reports" / "progression_model_eval.json"
REPORT_MD = ROOT / "ml" / "reports" / "progression_model_eval.md"


def main() -> None:
    with SessionLocal() as session:
        rows = session.query(WorkoutSetORM).filter(WorkoutSetORM.user_id == "demo").order_by(
            WorkoutSetORM.exercise.asc(),
            WorkoutSetORM.performed_at.asc(),
            WorkoutSetORM.set_index.asc(),
        ).all()

    by_exercise: dict[str, list[WorkoutSetORM]] = defaultdict(list)
    for row in rows:
        by_exercise[row.exercise].append(row)

    cases: list[dict[str, object]] = []
    for exercise, exercise_rows in by_exercise.items():
        by_day: dict[str, list[WorkoutSetORM]] = defaultdict(list)
        for row in exercise_rows:
            by_day[row.performed_at[:10]].append(row)
        days = sorted(by_day)
        if len(days) < 2:
            continue
        history_rows: list[WorkoutSetORM] = []
        for day in days:
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
                    prediction = predict_next_set(exercise, history=history, set_index=actual.set_index, current_session=current_session)
                    cases.append(
                        {
                            "exercise": exercise,
                            "day": day,
                            "set_index": actual.set_index,
                            "actual_weight_kg": actual.weight_kg,
                            "predicted_weight_kg": prediction.target_weight_kg,
                            "actual_reps": actual.reps,
                            "predicted_reps": prediction.target_reps,
                            "strategy": prediction.strategy,
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

    if cases:
        weight_mae = sum(abs(float(row["actual_weight_kg"]) - float(row["predicted_weight_kg"])) for row in cases) / len(cases)
        reps_mae = sum(abs(int(row["actual_reps"]) - int(row["predicted_reps"])) for row in cases) / len(cases)
    else:
        weight_mae = 0.0
        reps_mae = 0.0

    strategy_counts: dict[str, int] = defaultdict(int)
    for row in cases:
        strategy_counts[str(row["strategy"])] += 1

    report = {
        "model_version": "progression_v2_preferences_e1rm",
        "user_id": "demo",
        "cases": len(cases),
        "weight_mae_kg": round(weight_mae, 3),
        "reps_mae": round(reps_mae, 3),
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "note": "Backtest over deterministic demo workout history. This is a product/demo progression evaluation, not a clinical training prescription.",
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    REPORT_MD.write_text(
        "\n".join(
            [
                "# Progression Model Evaluation",
                "",
                f"- Model version: `{report['model_version']}`",
                f"- User: `{report['user_id']}`",
                f"- Backtest cases: `{report['cases']}`",
                f"- Weight MAE: `{report['weight_mae_kg']}` kg",
                f"- Reps MAE: `{report['reps_mae']}` reps",
                f"- Strategy counts: `{json.dumps(report['strategy_counts'], ensure_ascii=False)}`",
                "",
                str(report["note"]),
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
