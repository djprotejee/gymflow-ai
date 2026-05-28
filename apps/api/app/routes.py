from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gymflow_core.business_hours import is_business_open

from .anatomy import (
    allows_empty_primary_muscles,
    anatomy_region_catalog,
    resolve_anatomy_regions,
    validate_anatomy_assignment,
)
from .config import (
    DATA_SUMMARY_PATH,
    FUTURE_FORECAST_PATH,
    METRICS_PATH,
    ML_METRICS_PATH,
    ML_PREDICTIONS_PATH,
    OBSERVATIONS_PATH,
    ROOT,
)
from .ai_provider import AIProviderError, generate_with_configured_provider, get_ai_provider_status
from .database import get_session
from .models import (
    AchievementORM,
    ChatMessageORM,
    ChatSessionORM,
    ChatToolActionORM,
    ExerciseMediaORM,
    ExerciseORM,
    PromotionORM,
    RecommendationEventORM,
    ScheduledWorkoutORM,
    UserAccountORM,
    UserPreferenceORM,
    UserSessionORM,
    VisitORM,
    WorkoutSetORM,
    WorkoutTemplateORM,
)
from .services.forecast_data import is_open_forecast_row, read_future_rows, read_observation_rows
from .services.exercise_import_preview import import_preview_records, load_preview, summarize_preview
from .services.exercise_retrieval import format_exercise_context, retrieve_exercise_knowledge
from .services.rag_retrieval import format_rag_context, retrieve_rag_context
from .services.progression import SetObservation, predict_next_set
from .services.preferences import get_or_create_preferences, serialize_preference
from .services.serializers import serialize_exercise, serialize_template, serialize_user
from .schemas import (
    Achievement,
    AuthUser,
    ChatCitation,
    ChatMessageCreate,
    ChatMessageRecord,
    ChatRequest,
    ChatResponse,
    ChatSessionCreate,
    ChatSessionRecord,
    ChatSessionUpdate,
    ChatToolAction,
    ChatToolActionTrace,
    ChatToolActionTraceCreate,
    ChatToolActionTraceUpdate,
    CustomExerciseCreate,
    CustomExerciseUpdate,
    Exercise,
    ExerciseMedia,
    ExerciseMediaCreate,
    ExercisePreviewImportRequest,
    LoginRequest,
    LoginResponse,
    Promotion,
    PromotionCreate,
    RecommendationEvent,
    RecommendationEventUpdate,
    RegisterRequest,
    ScheduledWorkout,
    ScheduledWorkoutCreate,
    ScheduledWorkoutUpdate,
    UserPreference,
    UserPreferenceUpdate,
    Visit,
    VisitCreate,
    WorkoutSet,
    WorkoutSetCreate,
    WorkoutSetModifiers,
    WorkoutTemplate,
    WorkoutTemplateCreate,
)


router = APIRouter()
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 120_000
SESSION_DAYS = 7


def demo_mode_enabled() -> bool:
    return os.getenv("GYMFLOW_DEMO_MODE", "true").lower() not in {"0", "false", "no"}


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_ITERATIONS).hex()
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(stored: str, password: str) -> bool:
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != PASSWORD_SCHEME:
        return secrets.compare_digest(stored, password)
    _, raw_iterations, salt, digest = parts
    try:
        iterations = int(raw_iterations)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return secrets.compare_digest(candidate, digest)


def now_utc() -> datetime:
    return datetime.utcnow()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session_token(session: Session, row: UserAccountORM) -> str:
    token = secrets.token_urlsafe(48)
    created_at = now_utc()
    session.add(
        UserSessionORM(
            user_id=row.user_id,
            token_hash=token_hash(token),
            role=row.role,
            created_at=created_at.isoformat(),
            expires_at=(created_at + timedelta(days=SESSION_DAYS)).isoformat(),
            revoked_at="",
        )
    )
    session.commit()
    return token


def auth_user_from_session(row: UserAccountORM) -> AuthUser:
    return AuthUser(user_id=row.user_id, email=row.email, display_name=row.display_name, role=row.role)


def user_from_authorization(authorization: str | None, session: Session) -> AuthUser | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    stored = session.scalar(select(UserSessionORM).where(UserSessionORM.token_hash == token_hash(token)))
    if stored is None or stored.revoked_at:
        return None
    try:
        expires_at = datetime.fromisoformat(stored.expires_at)
    except ValueError:
        return None
    if expires_at <= now_utc():
        return None
    user_row = session.get(UserAccountORM, stored.user_id)
    if user_row is None:
        return None
    return auth_user_from_session(user_row)


def require_authenticated_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> AuthUser:
    user = user_from_authorization(authorization, session)
    if user is None:
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token.")
    return user


def require_manager_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> AuthUser:
    user = user_from_authorization(authorization, session)
    if user is None and demo_mode_enabled():
        return AuthUser(user_id="manager", email="manager@gymflow.ai", display_name="Demo Manager", role="manager")
    if user is None:
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token.")
    if user.role != "manager":
        raise HTTPException(status_code=403, detail="Manager role required.")
    return user


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "gymflow-ai-api"}


@router.post("/auth/login")
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> LoginResponse:
    row = session.scalar(select(UserAccountORM).where(func.lower(UserAccountORM.email) == payload.email.lower()))
    if row is None or not verify_password(row.password_demo, payload.password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not row.password_demo.startswith(f"{PASSWORD_SCHEME}$"):
        row.password_demo = hash_password(payload.password)
        session.commit()
    user = serialize_user(row)
    token = issue_session_token(session, row)
    return LoginResponse(token=token, user=user)


@router.post("/auth/register", status_code=201)
def register(payload: RegisterRequest, session: Session = Depends(get_session)) -> LoginResponse:
    email = payload.email.strip().lower()
    if session.scalar(select(UserAccountORM).where(func.lower(UserAccountORM.email) == email)) is not None:
        raise HTTPException(status_code=409, detail="Email is already registered.")
    user_id = f"user_{secrets.token_urlsafe(10)}"
    row = UserAccountORM(
        user_id=user_id,
        email=email,
        display_name=payload.display_name.strip(),
        role="member",
        password_demo=hash_password(payload.password),
    )
    session.add(row)
    session.add(UserPreferenceORM(user_id=user_id, preferred_gym_id="gym_008"))
    session.commit()
    token = issue_session_token(session, row)
    return LoginResponse(token=token, user=serialize_user(row))


@router.get("/auth/me")
def auth_me(current_user: AuthUser = Depends(require_authenticated_user)) -> AuthUser:
    return current_user


@router.post("/auth/logout")
def logout(
    current_user: AuthUser = Depends(require_authenticated_user),
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    _, _, token = (authorization or "").partition(" ")
    if token:
        stored = session.scalar(select(UserSessionORM).where(UserSessionORM.token_hash == token_hash(token)))
        if stored and not stored.revoked_at:
            stored.revoked_at = now_utc().isoformat()
            session.commit()
    return {"logged_out": True, "user_id": current_user.user_id}


@router.get("/metrics", response_class=PlainTextResponse)
def metrics_endpoint(session: Session = Depends(get_session)) -> str:
    lines = [
        "# HELP gymflow_api_up API availability flag.",
        "# TYPE gymflow_api_up gauge",
        "gymflow_api_up 1",
    ]

    if DATA_SUMMARY_PATH.exists():
        data = json.loads(DATA_SUMMARY_PATH.read_text(encoding="utf-8"))
        lines.extend(
            [
                "# HELP gymflow_dataset_rows Number of processed occupancy rows.",
                "# TYPE gymflow_dataset_rows gauge",
                f"gymflow_dataset_rows {data['rows']}",
                "# HELP gymflow_dataset_gyms Number of tracked gyms.",
                "# TYPE gymflow_dataset_gyms gauge",
                f"gymflow_dataset_gyms {data['gyms']}",
            ]
        )

    if ML_METRICS_PATH.exists():
        with ML_METRICS_PATH.open("r", encoding="utf-8", newline="") as file:
            for row in csv.DictReader(file):
                label = row["model"].replace("-", "_")
                lines.extend(
                    [
                        f'gymflow_model_mae{{model="{label}"}} {row["mae"]}',
                        f'gymflow_model_rmse{{model="{label}"}} {row["rmse"]}',
                        f'gymflow_model_wape{{model="{label}"}} {row["wape"]}',
                    ]
                )

    workout_sets = session.scalar(select(func.count()).select_from(WorkoutSetORM)) or 0
    lines.extend(
        [
            "# HELP gymflow_workout_sets Number of persisted workout set records.",
            "# TYPE gymflow_workout_sets gauge",
            f"gymflow_workout_sets {workout_sets}",
        ]
    )

    return "\n".join(lines) + "\n"


@router.get("/summary")
def summary() -> dict[str, object]:
    if not DATA_SUMMARY_PATH.exists():
        raise HTTPException(status_code=404, detail="Data summary not found. Run scripts/prepare_data.py.")
    return json.loads(DATA_SUMMARY_PATH.read_text(encoding="utf-8"))


@router.get("/gyms")
def gyms() -> list[dict[str, str]]:
    if not OBSERVATIONS_PATH.exists():
        raise HTTPException(status_code=404, detail="Processed observations not found.")

    seen: dict[str, dict[str, str]] = {}
    with OBSERVATIONS_PATH.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            seen[row["gym_id"]] = {
                "gym_id": row["gym_id"],
                "city": row["city"],
                "address": row["address"],
            }
    return sorted(seen.values(), key=lambda item: (item["city"], item["address"]))


@router.get("/gyms/{gym_id}/occupancy")
def occupancy(gym_id: str, limit: int = 300) -> list[dict[str, object]]:
    if not OBSERVATIONS_PATH.exists():
        raise HTTPException(status_code=404, detail="Processed observations not found.")

    rows: list[dict[str, object]] = []
    with OBSERVATIONS_PATH.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            if row["gym_id"] == gym_id:
                rows.append(
                    {
                        "timestamp": row["timestamp"],
                        "active_people": int(row["active_people"]),
                    }
                )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Gym not found: {gym_id}")
    return rows[-limit:]


@router.get("/models/baseline-metrics")
def baseline_metrics() -> list[dict[str, object]]:
    if not METRICS_PATH.exists():
        raise HTTPException(status_code=404, detail="Metrics not found. Run scripts/run_baseline_backtest.py.")

    rows: list[dict[str, object]] = []
    with METRICS_PATH.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            rows.append(
                {
                    "model": row["model"],
                    "rows": int(row["rows"]),
                    "mae": float(row["mae"]),
                    "rmse": float(row["rmse"]),
                    "wape": float(row["wape"]),
                }
            )
    return rows


@router.get("/models/ml-metrics")
def ml_metrics() -> list[dict[str, object]]:
    if not ML_METRICS_PATH.exists():
        raise HTTPException(status_code=404, detail="ML metrics not found. Run scripts/run_ml_experiments.py.")

    rows: list[dict[str, object]] = []
    with ML_METRICS_PATH.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            rows.append(
                {
                    "model": row["model"],
                    "scope": row["scope"],
                    "train_rows": int(row["train_rows"]),
                    "test_rows": int(row["test_rows"]),
                    "mae": float(row["mae"]),
                    "rmse": float(row["rmse"]),
                    "wape": float(row["wape"]),
                }
            )
    return rows


@router.get("/gyms/{gym_id}/forecast")
def forecast(gym_id: str, model: str = "hist_gradient_boosting", limit: int = 120) -> list[dict[str, object]]:
    if not ML_PREDICTIONS_PATH.exists():
        raise HTTPException(status_code=404, detail="Prediction sample not found. Run scripts/run_ml_experiments.py.")

    prediction_column = f"pred_{model}"
    rows: list[dict[str, object]] = []
    with ML_PREDICTIONS_PATH.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if prediction_column not in (reader.fieldnames or []):
            raise HTTPException(status_code=404, detail=f"Prediction column not found for model: {model}")

        for row in reader:
            if row["gym_id"] == gym_id:
                rows.append(
                    {
                        "timestamp": row["timestamp"],
                        "actual": float(row["active_people"]),
                        "prediction": float(row[prediction_column]),
                    }
                )

    if not rows:
        raise HTTPException(status_code=404, detail=f"Forecast not found for gym: {gym_id}")
    return rows[-limit:]


def format_training_window(timestamp: datetime, minutes: int = 90) -> str:
    rounded = timestamp.replace(second=0, microsecond=0)
    if rounded.minute <= 15:
        rounded = rounded.replace(minute=0)
    elif rounded.minute <= 45:
        rounded = rounded.replace(minute=30)
    else:
        rounded = (rounded + timedelta(hours=1)).replace(minute=0)
    end = rounded + timedelta(minutes=minutes)
    return f"{rounded.strftime('%A %H:%M')}-{end.strftime('%H:%M')}"


@router.get("/gyms/{gym_id}/forecast/future")
def future_forecast(
    gym_id: str,
    model: str = "hist_gradient_boosting",
    days: int = 7,
    limit: int | None = None,
) -> list[dict[str, object]]:
    if not FUTURE_FORECAST_PATH.exists():
        raise HTTPException(status_code=404, detail="Future forecast not found. Run scripts/generate_future_forecast.py.")

    rows: list[dict[str, object]] = []
    safe_days = max(1, min(days, 7))
    now = datetime.now().replace(microsecond=0)
    horizon_end = now + timedelta(days=safe_days)
    with FUTURE_FORECAST_PATH.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            if row["gym_id"] == gym_id and row["model"] == model:
                timestamp = datetime.fromisoformat(row["timestamp"])
                if timestamp < now or timestamp >= horizon_end:
                    continue
                rows.append(
                    {
                        "timestamp": row["timestamp"],
                        "prediction": float(row["prediction"]),
                        "prediction_interval_low": float(row.get("prediction_interval_low", row["prediction"])),
                        "prediction_interval_high": float(row.get("prediction_interval_high", row["prediction"])),
                        "uncertainty_abs_error_p80": float(row.get("uncertainty_abs_error_p80", 0)),
                        "model": row["model"],
                        "is_weekend": int(row["is_weekend"]),
                        "is_open_estimated": int(row.get("is_open_estimated", 1)),
                        "business_hours": row.get("business_hours", ""),
                        "is_public_holiday_ua": int(row["is_public_holiday_ua"]),
                        "is_gym_closed_holiday": int(row.get("is_gym_closed_holiday", 0)),
                        "is_major_low_traffic_holiday": int(row.get("is_major_low_traffic_holiday", 0)),
                        "is_major_holiday_window": int(row.get("is_major_holiday_window", 0)),
                    }
                )

    if not rows:
        raise HTTPException(status_code=404, detail=f"Future forecast not found for gym: {gym_id}")
    effective_limit = limit if limit is not None else safe_days * 72
    return rows[:effective_limit]


@router.get("/recommendations/slots")
def recommended_slots(
    gym_id: str,
    model: str = "hist_gradient_boosting",
    max_results: int = 5,
) -> list[dict[str, object]]:
    forecast_rows = forecast(gym_id=gym_id, model=model, limit=240)
    ranked = sorted(forecast_rows, key=lambda row: (row["prediction"], row["timestamp"]))
    recommendations: list[dict[str, object]] = []
    seen_hours: set[str] = set()

    for row in ranked:
        timestamp = datetime.fromisoformat(str(row["timestamp"]))
        if not is_business_open(timestamp):
            continue
        hour_key = timestamp.strftime("%Y-%m-%d %H")
        if hour_key in seen_hours:
            continue
        seen_hours.add(hour_key)
        load = float(row["prediction"])
        recommendations.append(
            {
                "timestamp": row["timestamp"],
                "window_label": format_training_window(timestamp),
                "expected_people": round(load, 1),
                "score": round(max(0.0, 100.0 - load), 1),
                "reason": "Lower predicted occupancy compared with other available forecast slots.",
            }
        )
        if len(recommendations) >= max_results:
            break

    return recommendations


@router.get("/recommendations/future-slots")
def future_recommended_slots(
    gym_id: str,
    model: str = "hist_gradient_boosting",
    max_results: int = 5,
    days: int = 7,
    min_hour: int | None = None,
    max_hour: int | None = None,
) -> list[dict[str, object]]:
    forecast_rows = future_forecast(gym_id=gym_id, model=model, days=days)
    ranked = sorted(forecast_rows, key=lambda row: (row["prediction"], row["timestamp"]))
    recommendations: list[dict[str, object]] = []
    seen_hours: set[str] = set()

    for row in ranked:
        timestamp = datetime.fromisoformat(str(row["timestamp"]))
        if int(row.get("is_gym_closed_holiday", 0)) == 1:
            continue
        if int(row.get("is_open_estimated", 0)) == 0 or not is_business_open(timestamp):
            continue
        hour_value = timestamp.hour + timestamp.minute / 60
        if min_hour is not None and hour_value < min_hour:
            continue
        if max_hour is not None and hour_value >= max_hour:
            continue
        hour_key = timestamp.strftime("%Y-%m-%d %H")
        if hour_key in seen_hours:
            continue
        seen_hours.add(hour_key)
        load = float(row["prediction"])
        recommendations.append(
            {
                "timestamp": row["timestamp"],
                "window_label": format_training_window(timestamp),
                "expected_people": round(load, 1),
                "score": round(max(0.0, 100.0 - load), 1),
                "reason": "Lowest predicted occupancy in the next seven-day forecast horizon.",
            }
        )
        if len(recommendations) >= max_results:
            break

    return recommendations


@router.get("/users/{user_id}/preferences")
def get_preferences(user_id: str = "demo", session: Session = Depends(get_session)) -> UserPreference:
    return serialize_preference(get_or_create_preferences(user_id, session))


@router.put("/users/{user_id}/preferences")
def update_preferences(
    user_id: str,
    payload: UserPreferenceUpdate,
    session: Session = Depends(get_session),
) -> UserPreference:
    if payload.preferred_min_hour >= payload.preferred_max_hour:
        raise HTTPException(status_code=422, detail="preferred_min_hour must be lower than preferred_max_hour.")
    weekdays = sorted({day for day in payload.preferred_weekdays if 0 <= day <= 6})
    if not weekdays:
        raise HTTPException(status_code=422, detail="preferred_weekdays must contain at least one weekday in 0..6.")
    if payload.preferred_rep_min > payload.preferred_rep_max:
        raise HTTPException(status_code=422, detail="preferred_rep_min must be lower than or equal to preferred_rep_max.")

    row = get_or_create_preferences(user_id, session)
    row.preferred_min_hour = payload.preferred_min_hour
    row.preferred_max_hour = payload.preferred_max_hour
    row.max_crowd_people = payload.max_crowd_people
    row.weekly_goal_sessions = payload.weekly_goal_sessions
    row.preferred_weekdays = ",".join(str(day) for day in weekdays)
    row.off_peak_bonus_enabled = 1 if payload.off_peak_bonus_enabled else 0
    row.preferred_gym_id = payload.preferred_gym_id
    row.preferred_rep_mode = payload.preferred_rep_mode
    row.preferred_rep_min = payload.preferred_rep_min
    row.preferred_rep_max = payload.preferred_rep_max
    session.commit()
    session.refresh(row)
    return serialize_preference(row)


def remember_recommendation_event(
    session: Session,
    *,
    user_id: str,
    recommendation_type: str,
    context_key: str,
    title: str,
    detail: str,
    score: float = 0,
    expected_people: float = 0,
    metadata: dict[str, object] | None = None,
) -> None:
    existing = session.scalar(
        select(RecommendationEventORM)
        .where(RecommendationEventORM.user_id == user_id)
        .where(RecommendationEventORM.recommendation_type == recommendation_type)
        .where(RecommendationEventORM.context_key == context_key)
    )
    if existing is not None:
        existing.title = title
        existing.detail = detail
        existing.score = score
        existing.expected_people = expected_people
        existing.metadata_json = json.dumps(metadata or {})
        return
    session.add(
        RecommendationEventORM(
            user_id=user_id,
            recommendation_type=recommendation_type,
            context_key=context_key,
            title=title,
            detail=detail,
            status="suggested",
            score=score,
            expected_people=expected_people,
            created_at=datetime.now().replace(microsecond=0).isoformat(),
            acted_at="",
            metadata_json=json.dumps(metadata or {}),
        )
    )


@router.get("/users/{user_id}/recommendation-history")
def recommendation_history(user_id: str, session: Session = Depends(get_session)) -> list[RecommendationEvent]:
    rows = session.scalars(
        select(RecommendationEventORM)
        .where(RecommendationEventORM.user_id == user_id)
        .order_by(RecommendationEventORM.created_at.desc(), RecommendationEventORM.id.desc())
        .limit(50)
    ).all()
    return [RecommendationEvent.model_validate(row) for row in rows]


@router.put("/users/{user_id}/recommendation-history/{event_id}")
def update_recommendation_history(
    user_id: str,
    event_id: int,
    payload: RecommendationEventUpdate,
    session: Session = Depends(get_session),
) -> RecommendationEvent:
    row = session.get(RecommendationEventORM, event_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Recommendation event not found.")
    row.status = payload.status
    row.acted_at = datetime.now().replace(microsecond=0).isoformat()
    session.commit()
    session.refresh(row)
    return RecommendationEvent.model_validate(row)


@router.get("/users/{user_id}/recommendations/future-slots")
def personalized_future_slots(
    user_id: str,
    gym_id: str,
    model: str = "hist_gradient_boosting",
    max_results: int = 5,
    days: int = 7,
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    recommendations = preference_matched_future_slots(
        user_id=user_id,
        gym_id=gym_id,
        model=model,
        max_results=max_results,
        days=days,
        session=session,
    )

    if recommendations:
        for item in recommendations:
            remember_recommendation_event(
                session,
                user_id=user_id,
                recommendation_type="training_slot",
                context_key=f"{gym_id}:{model}:{item['timestamp']}",
                title="Low-traffic training slot",
                detail=str(item["reason"]),
                score=float(item["score"]),
                expected_people=float(item["expected_people"]),
                metadata={"gym_id": gym_id, "model": model, "timestamp": item["timestamp"], "days": days},
            )
        session.commit()
        return recommendations

    preferences = serialize_preference(get_or_create_preferences(user_id, session))
    return future_recommended_slots(
        gym_id=gym_id,
        model=model,
        max_results=max_results,
        days=days,
        min_hour=preferences.preferred_min_hour,
        max_hour=preferences.preferred_max_hour,
    )


def preference_matched_future_slots(
    user_id: str,
    gym_id: str,
    model: str = "hist_gradient_boosting",
    max_results: int = 5,
    days: int = 7,
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    preferences = serialize_preference(get_or_create_preferences(user_id, session))
    forecast_rows = future_forecast(gym_id=gym_id, model=model, days=days)
    ranked = sorted(forecast_rows, key=lambda row: (row["prediction"], row["timestamp"]))
    recommendations: list[dict[str, object]] = []
    seen_hours: set[str] = set()

    for row in ranked:
        timestamp = datetime.fromisoformat(str(row["timestamp"]))
        if int(row.get("is_gym_closed_holiday", 0)) == 1:
            continue
        if int(row.get("is_open_estimated", 0)) == 0 or not is_business_open(timestamp):
            continue
        hour_value = timestamp.hour + timestamp.minute / 60
        if hour_value < preferences.preferred_min_hour or hour_value >= preferences.preferred_max_hour:
            continue
        if timestamp.weekday() not in preferences.preferred_weekdays:
            continue
        load = float(row["prediction"])
        if load > preferences.max_crowd_people:
            continue
        hour_key = timestamp.strftime("%Y-%m-%d %H")
        if hour_key in seen_hours:
            continue
        seen_hours.add(hour_key)
        recommendations.append(
            {
                "timestamp": row["timestamp"],
                "window_label": format_training_window(timestamp),
                "expected_people": round(load, 1),
                "score": round(max(0.0, 100.0 - load), 1),
                "reason": "Matches your preferred days, time window, and crowd tolerance.",
            }
        )
        if len(recommendations) >= max(1, min(max_results, 20)):
            break

    return recommendations


@router.get("/users/{user_id}/gamification")
def user_gamification(user_id: str = "demo", session: Session = Depends(get_session)) -> dict[str, object]:
    preferences = serialize_preference(get_or_create_preferences(user_id, session))
    rows = session.scalars(
        select(WorkoutSetORM)
        .where(WorkoutSetORM.user_id == user_id)
        .order_by(WorkoutSetORM.performed_at.asc(), WorkoutSetORM.id.asc())
    ).all()

    dates = sorted({datetime.fromisoformat(row.performed_at).date() for row in rows})
    if dates:
        latest_date = dates[-1]
        window_start = latest_date - timedelta(days=6)
        weekly_sessions = len([date for date in dates if date >= window_start])
        streak = 0
        cursor = latest_date
        date_set = set(dates)
        while cursor in date_set:
            streak += 1
            cursor = cursor - timedelta(days=1)
    else:
        weekly_sessions = 0
        streak = 0

    consistency_score = round(min(100.0, weekly_sessions / preferences.weekly_goal_sessions * 100.0), 1)
    off_peak_bonus = 0
    if preferences.off_peak_bonus_enabled:
        for row in rows:
            performed_at = datetime.fromisoformat(row.performed_at)
            hour = performed_at.hour + performed_at.minute / 60
            if preferences.preferred_min_hour <= hour < preferences.preferred_max_hour:
                off_peak_bonus += 1

    return {
        "user_id": user_id,
        "weekly_goal_sessions": preferences.weekly_goal_sessions,
        "weekly_sessions": weekly_sessions,
        "current_streak_days": streak,
        "consistency_score": consistency_score,
        "off_peak_bonus_points": off_peak_bonus * 10,
        "level": "Consistent Builder" if consistency_score >= 75 else "Momentum Starter",
        "next_action": "Book a low-traffic slot that matches your preferred window.",
    }


@router.get("/manager/overview")
def manager_overview(
    model: str = "hist_gradient_boosting",
    days: int = 7,
    current_user: AuthUser = Depends(require_manager_user),
) -> dict[str, object]:
    observation_rows = read_observation_rows()
    future_rows = read_future_rows(model=model, days=days)
    latest_by_gym: dict[str, dict[str, object]] = {}
    for row in observation_rows:
        existing = latest_by_gym.get(str(row["gym_id"]))
        if existing is None or row["timestamp"] > existing["timestamp"]:
            latest_by_gym[str(row["gym_id"])] = row

    latest_values = [float(row["active_people"]) for row in latest_by_gym.values()]
    open_future = [row for row in future_rows if is_open_forecast_row(row)]
    low_traffic = [row for row in open_future if float(row["prediction"]) <= 35]
    peak_location = max(latest_by_gym.values(), key=lambda row: float(row["active_people"])) if latest_by_gym else None
    best_model = ml_metrics()[0] if ML_METRICS_PATH.exists() else None

    return {
        "gyms": len(latest_by_gym),
        "latest_total_people": round(sum(latest_values), 1),
        "avg_latest_people": round(sum(latest_values) / len(latest_values), 1) if latest_values else 0,
        "future_avg_prediction": round(sum(float(row["prediction"]) for row in open_future) / len(open_future), 1) if open_future else 0,
        "low_traffic_slots": len(low_traffic),
        "forecast_points": len(future_rows),
        "best_model": best_model,
        "peak_location": {
            "gym_id": peak_location["gym_id"],
            "city": peak_location["city"],
            "address": peak_location["address"],
            "active_people": round(float(peak_location["active_people"]), 1),
            "timestamp": peak_location["timestamp"].isoformat(sep=" "),
        }
        if peak_location
        else None,
    }


@router.get("/manager/locations")
def manager_locations(
    model: str = "hist_gradient_boosting",
    days: int = 7,
    current_user: AuthUser = Depends(require_manager_user),
) -> list[dict[str, object]]:
    observation_rows = read_observation_rows()
    future_rows = read_future_rows(model=model, days=days)
    grouped_observations: dict[str, list[dict[str, object]]] = {}
    grouped_future: dict[str, list[dict[str, object]]] = {}

    for row in observation_rows:
        grouped_observations.setdefault(str(row["gym_id"]), []).append(row)
    for row in future_rows:
        if is_open_forecast_row(row):
            grouped_future.setdefault(str(row["gym_id"]), []).append(row)

    locations: list[dict[str, object]] = []
    for gym_id, rows in grouped_observations.items():
        rows = sorted(rows, key=lambda row: row["timestamp"])
        latest = rows[-1]
        future = grouped_future.get(gym_id, [])
        future_predictions = [float(row["prediction"]) for row in future]
        campaign_candidates = [value for value in future_predictions if value <= 35]
        locations.append(
            {
                "gym_id": gym_id,
                "city": latest["city"],
                "address": latest["address"],
                "latest_people": round(float(latest["active_people"]), 1),
                "avg_people": round(sum(float(row["active_people"]) for row in rows) / len(rows), 1),
                "peak_people": round(max(float(row["active_people"]) for row in rows), 1),
                "future_avg_prediction": round(sum(future_predictions) / len(future_predictions), 1) if future_predictions else 0,
                "future_peak_prediction": round(max(future_predictions), 1) if future_predictions else 0,
                "campaign_candidate_slots": len(campaign_candidates),
            }
        )

    return sorted(locations, key=lambda row: row["future_avg_prediction"], reverse=True)


@router.get("/manager/campaigns")
def manager_campaigns(
    model: str = "hist_gradient_boosting",
    days: int = 7,
    max_results: int = 12,
    current_user: AuthUser = Depends(require_manager_user),
) -> list[dict[str, object]]:
    future_rows = [row for row in read_future_rows(model=model, days=days) if is_open_forecast_row(row)]
    ranked = sorted(future_rows, key=lambda row: (float(row["prediction"]), row["timestamp"]))
    campaigns: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    for row in ranked:
        timestamp = row["timestamp"]
        hour_key = timestamp.strftime("%Y-%m-%d %H")
        identity = (str(row["gym_id"]), hour_key)
        if identity in seen:
            continue
        seen.add(identity)
        prediction = float(row["prediction"])
        campaigns.append(
            {
                "gym_id": row["gym_id"],
                "city": row["city"],
                "address": row["address"],
                "timestamp": timestamp.isoformat(sep=" "),
                "expected_people": round(prediction, 1),
                "score": round(max(0.0, 100.0 - prediction), 1),
                "campaign_type": "off_peak_bonus",
                "reason": "Low predicted occupancy during configured opening hours.",
            }
        )
        if len(campaigns) >= max(1, min(max_results, 30)):
            break

    return campaigns


@router.get("/exercise-library")
def exercise_library(
    muscle_group: str | None = None,
    query: str | None = None,
    session: Session = Depends(get_session),
) -> list[Exercise]:
    statement = select(ExerciseORM).order_by(ExerciseORM.muscle_group.asc(), ExerciseORM.name.asc())
    rows = [row for row in session.scalars(statement).all() if is_member_visible_exercise(row)]
    media_rows = session.scalars(
        select(ExerciseMediaORM).order_by(ExerciseMediaORM.exercise_slug.asc(), ExerciseMediaORM.sort_order.asc(), ExerciseMediaORM.id.asc())
    ).all()
    media_by_slug: dict[str, list[ExerciseMediaORM]] = {}
    for item in media_rows:
        media_by_slug.setdefault(item.exercise_slug, []).append(item)
    exercises = dedupe_exercises_for_member([serialize_exercise(row, media_rows=media_by_slug.get(row.slug, [])) for row in rows])
    if muscle_group:
        exercises = [item for item in exercises if item.muscle_group.lower() == muscle_group.lower()]
    if query:
        needle = query.lower()
        exercises = [
            item
            for item in exercises
            if needle in item.name.lower() or needle in item.category.lower() or needle in item.muscle_group.lower()
        ]
    return exercises


def dedupe_exercises_for_member(exercises: list[Exercise]) -> list[Exercise]:
    preferred_by_name: dict[str, Exercise] = {}
    for exercise in exercises:
        key = re.sub(r"[^a-z0-9]+", " ", exercise.name.lower()).strip()
        current = preferred_by_name.get(key)
        if current is None or exercise_member_priority(exercise) > exercise_member_priority(current):
            preferred_by_name[key] = exercise
    return sorted(preferred_by_name.values(), key=lambda item: (item.muscle_group, item.name))


def exercise_member_priority(exercise: Exercise) -> tuple[int, int, int]:
    has_demo_media = any(item.source_name != "GymFlow AI generated reference" for item in exercise.media_gallery)
    is_project_seed = exercise.source_name in {"GymFlow AI local seed", "Renaissance Periodization YouTube"}
    has_anatomy = bool(exercise.primary_muscles)
    return (1 if has_demo_media else 0, 1 if is_project_seed else 0, 1 if has_anatomy else 0)


def slugify_exercise_name(value: str) -> str:
    return (
        value.lower()
        .replace("&", "and")
        .replace("/", " ")
        .replace("_", " ")
        .replace("  ", " ")
        .strip()
        .replace(" ", "-")
    )


def dedupe_region_ids(region_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for region_id in region_ids:
        normalized = region_id.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def is_custom_exercise(row: ExerciseORM) -> bool:
    return row.source_name == "GymFlow AI user custom exercise"


def is_member_visible_exercise(row: ExerciseORM) -> bool:
    # The first wger demo batch mixed translations and media provenance, so keep it internal until a clean reimport.
    if row.source_name.lower() == "wger":
        return False
    return True


def apply_custom_exercise_payload(
    row: ExerciseORM,
    payload: CustomExerciseCreate | CustomExerciseUpdate,
    slug: str,
) -> None:
    allow_empty_primary = payload.allow_empty_primary or allows_empty_primary_muscles(payload.muscle_group, payload.category)
    primary_muscles = dedupe_region_ids(payload.primary_muscles)
    secondary_muscles = [region for region in dedupe_region_ids(payload.secondary_muscles) if region not in primary_muscles]
    if not primary_muscles and not secondary_muscles and not allow_empty_primary:
        primary_muscles, secondary_muscles = resolve_anatomy_regions(slug=slug, muscle_group=payload.muscle_group)
    validate_anatomy_assignment(slug, primary_muscles, secondary_muscles, require_primary=not allow_empty_primary)
    row.category = payload.category
    row.muscle_group = payload.muscle_group
    row.difficulty = payload.difficulty
    row.primary_muscles_json = json.dumps(primary_muscles)
    row.secondary_muscles_json = json.dumps(secondary_muscles)
    if isinstance(payload, CustomExerciseUpdate):
        row.instructions_json = json.dumps([item.strip() for item in payload.instructions if item.strip()])
        row.cues_json = json.dumps([item.strip() for item in payload.cues if item.strip()])
        row.mistakes_json = json.dumps([item.strip() for item in payload.mistakes if item.strip()])


@router.get("/exercise-library/anatomy-regions")
def exercise_anatomy_regions() -> list[dict[str, object]]:
    return anatomy_region_catalog()


@router.get("/exercise-library/import-preview")
def exercise_import_preview(path: str | None = None, limit: int = 48) -> dict[str, object]:
    preview_path = Path(path) if path else None
    try:
        return summarize_preview(path=preview_path, limit=max(1, min(limit, 200)))
    except FileNotFoundError as error:
        return {
            "path": str(preview_path) if preview_path else "",
            "status": "missing",
            "source_name": "",
            "source_license": "",
            "note": f"Preview file not found: {error.filename}",
            "records_total": 0,
            "records_with_media": 0,
            "records_with_embed_ready_media": 0,
            "records_needing_anatomy_review": 0,
            "records": [],
        }
    except (json.JSONDecodeError, OSError) as error:
        raise HTTPException(status_code=422, detail=f"Could not read preview file: {error}") from error


@router.post("/exercise-library/import-preview", status_code=201)
def import_exercise_preview(
    payload: ExercisePreviewImportRequest,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    preview_path = Path(payload.path) if payload.path else None
    try:
        preview = load_preview(preview_path)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"Preview file not found: {error.filename}") from error
    except (json.JSONDecodeError, OSError) as error:
        raise HTTPException(status_code=422, detail=f"Could not read preview file: {error}") from error

    result = import_preview_records(
        session=session,
        preview=preview,
        limit=payload.limit,
        only_with_media=payload.only_with_media,
        only_embed_ready_media=payload.only_embed_ready_media,
    )
    session.commit()
    return {
        "status": "ok",
        "path": str(preview_path) if preview_path else "",
        **result,
        "records_total": len([record for record in preview.get("records", []) if isinstance(record, dict)]),
    }


@router.get("/exercise-library/{slug}")
def exercise_detail(slug: str, session: Session = Depends(get_session)) -> Exercise:
    row = session.get(ExerciseORM, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Exercise not found.")
    media_rows = session.scalars(
        select(ExerciseMediaORM)
        .where(ExerciseMediaORM.exercise_slug == slug)
        .order_by(ExerciseMediaORM.sort_order.asc(), ExerciseMediaORM.id.asc())
    ).all()
    return serialize_exercise(row, media_rows=list(media_rows))


@router.post("/users/{user_id}/exercise-library", status_code=201)
def create_custom_exercise(user_id: str, payload: CustomExerciseCreate, session: Session = Depends(get_session)) -> Exercise:
    base_slug = slugify_exercise_name(payload.name)
    if not base_slug:
        raise HTTPException(status_code=400, detail="Exercise name cannot be empty.")
    slug = base_slug
    suffix = 1
    while session.get(ExerciseORM, slug) is not None:
        suffix += 1
        slug = f"{base_slug}-custom-{suffix}"

    checked_at = datetime.now().date().isoformat()

    row = ExerciseORM(
        slug=slug,
        name=payload.name,
        category="Custom",
        muscle_group=payload.muscle_group,
        difficulty=payload.difficulty,
        image_hint="custom",
        video_url="",
        media_type="none",
        media_url="",
        youtube_video_id="",
        source_name="GymFlow AI user custom exercise",
        source_url="",
        source_license="User-generated exercise label",
        attribution=f"Created by user '{user_id}' inside the GymFlow AI demo app.",
        checked_at=checked_at,
        primary_muscles_json="[]",
        secondary_muscles_json="[]",
        instructions_json=json.dumps([]),
        cues_json=json.dumps([]),
        mistakes_json=json.dumps([]),
    )
    row.category = payload.category
    apply_custom_exercise_payload(row, payload, slug)
    session.add(row)
    session.commit()
    session.refresh(row)
    return serialize_exercise(row, media_rows=[])


@router.put("/users/{user_id}/exercise-library/{slug}")
def update_custom_exercise(
    user_id: str,
    slug: str,
    payload: CustomExerciseUpdate,
    session: Session = Depends(get_session),
) -> Exercise:
    row = session.get(ExerciseORM, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Exercise not found.")
    if not is_custom_exercise(row):
        raise HTTPException(status_code=403, detail="Only user-created custom exercises can be edited.")
    apply_custom_exercise_payload(row, payload, slug)
    row.checked_at = datetime.now().date().isoformat()
    session.commit()
    session.refresh(row)
    media_rows = session.scalars(
        select(ExerciseMediaORM)
        .where(ExerciseMediaORM.exercise_slug == slug)
        .order_by(ExerciseMediaORM.sort_order.asc(), ExerciseMediaORM.id.asc())
    ).all()
    return serialize_exercise(row, media_rows=list(media_rows))


@router.delete("/users/{user_id}/exercise-library/{slug}")
def delete_custom_exercise(user_id: str, slug: str, session: Session = Depends(get_session)) -> dict[str, object]:
    row = session.get(ExerciseORM, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Exercise not found.")
    if not is_custom_exercise(row):
        raise HTTPException(status_code=403, detail="Only user-created custom exercises can be deleted.")
    session.query(ExerciseMediaORM).filter(ExerciseMediaORM.exercise_slug == slug).delete()
    session.delete(row)
    session.commit()
    return {"deleted": True, "slug": slug}


@router.post("/users/{user_id}/exercise-library/{slug}/media", status_code=201)
def create_exercise_media_reference(
    user_id: str,
    slug: str,
    payload: ExerciseMediaCreate,
    session: Session = Depends(get_session),
) -> ExerciseMedia:
    row = session.get(ExerciseORM, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Exercise not found.")
    media = ExerciseMediaORM(
        exercise_slug=slug,
        media_type=payload.media_type,
        media_url=payload.media_url,
        thumbnail_url=payload.thumbnail_url,
        title=payload.title,
        source_name=payload.source_name,
        source_url=payload.source_url,
        source_license=payload.source_license,
        attribution=payload.attribution,
        checked_at=payload.checked_at or datetime.now().date().isoformat(),
        embed_allowed=1 if payload.embed_allowed else 0,
        download_allowed=1 if payload.download_allowed else 0,
        requires_attribution=1 if payload.requires_attribution else 0,
        sort_order=payload.sort_order,
        license_notes=payload.license_notes,
    )
    session.add(media)
    session.commit()
    session.refresh(media)
    return ExerciseMedia.model_validate(
        {
            "id": media.id,
            "exercise_slug": media.exercise_slug,
            "media_type": media.media_type,
            "media_url": media.media_url,
            "thumbnail_url": media.thumbnail_url,
            "title": media.title,
            "source_name": media.source_name,
            "source_url": media.source_url,
            "source_license": media.source_license,
            "attribution": media.attribution,
            "checked_at": media.checked_at,
            "embed_allowed": bool(media.embed_allowed),
            "download_allowed": bool(media.download_allowed),
            "requires_attribution": bool(media.requires_attribution),
            "sort_order": media.sort_order,
            "license_notes": media.license_notes,
        }
    )


@router.delete("/users/{user_id}/exercise-library/{slug}/media/{media_id}")
def delete_exercise_media_reference(
    user_id: str,
    slug: str,
    media_id: int,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    media = session.get(ExerciseMediaORM, media_id)
    if media is None or media.exercise_slug != slug:
        raise HTTPException(status_code=404, detail="Exercise media not found.")
    session.delete(media)
    session.commit()
    return {"deleted": True, "media_id": media_id, "slug": slug}


@router.get("/users/{user_id}/visits")
def list_visits(user_id: str = "demo", session: Session = Depends(get_session)) -> list[Visit]:
    rows = session.scalars(
        select(VisitORM)
        .where(VisitORM.user_id == user_id)
        .order_by(VisitORM.checked_in_at.desc(), VisitORM.id.desc())
        .limit(100)
    ).all()
    return [Visit.model_validate(row) for row in rows]


@router.post("/users/{user_id}/visits", status_code=201)
def create_visit(user_id: str, payload: VisitCreate, session: Session = Depends(get_session)) -> Visit:
    checked_in_at = payload.checked_in_at or datetime.now().replace(microsecond=0).isoformat()
    row = VisitORM(
        user_id=user_id,
        gym_id=payload.gym_id,
        checked_in_at=checked_in_at,
        source="qr_demo",
        active_people_at_checkin=payload.active_people_at_checkin,
        note=payload.note,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return Visit.model_validate(row)


@router.get("/users/{user_id}/workout-templates")
def list_workout_templates(user_id: str = "demo", session: Session = Depends(get_session)) -> list[WorkoutTemplate]:
    rows = session.scalars(
        select(WorkoutTemplateORM)
        .where(WorkoutTemplateORM.user_id == user_id)
        .order_by(WorkoutTemplateORM.created_at.desc(), WorkoutTemplateORM.id.desc())
    ).all()
    return [serialize_template(row) for row in rows]


@router.post("/users/{user_id}/workout-templates", status_code=201)
def create_workout_template(
    user_id: str,
    payload: WorkoutTemplateCreate,
    session: Session = Depends(get_session),
) -> WorkoutTemplate:
    row = WorkoutTemplateORM(
        user_id=user_id,
        name=payload.name,
        focus=payload.focus,
        exercises_json=json.dumps([item.model_dump() for item in payload.exercises]),
        estimated_minutes=payload.estimated_minutes,
        created_at=datetime.now().replace(microsecond=0).isoformat(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return serialize_template(row)


@router.put("/users/{user_id}/workout-templates/{template_id}")
def update_workout_template(
    user_id: str,
    template_id: int,
    payload: WorkoutTemplateCreate,
    session: Session = Depends(get_session),
) -> WorkoutTemplate:
    template = session.get(WorkoutTemplateORM, template_id)
    if template is None or template.user_id != user_id:
        raise HTTPException(status_code=404, detail="Workout template not found.")
    template.name = payload.name
    template.focus = payload.focus
    template.exercises_json = json.dumps([item.model_dump() for item in payload.exercises])
    template.estimated_minutes = payload.estimated_minutes
    session.commit()
    session.refresh(template)
    return serialize_template(template)


@router.delete("/users/{user_id}/workout-templates/{template_id}")
def delete_workout_template(user_id: str, template_id: int, session: Session = Depends(get_session)) -> dict[str, object]:
    template = session.get(WorkoutTemplateORM, template_id)
    if template is None or template.user_id != user_id:
        raise HTTPException(status_code=404, detail="Workout template not found.")
    session.delete(template)
    session.commit()
    return {"template_id": template_id, "deleted": True}


@router.post("/users/{user_id}/workout-templates/{template_id}/apply", status_code=201)
def apply_workout_template(user_id: str, template_id: int, session: Session = Depends(get_session)) -> dict[str, object]:
    template = session.get(WorkoutTemplateORM, template_id)
    if template is None or template.user_id != user_id:
        raise HTTPException(status_code=404, detail="Workout template not found.")
    performed_at = datetime.now().replace(microsecond=0).isoformat()
    exercises = json.loads(template.exercises_json)
    created = 0
    for exercise in exercises:
        sets = int(exercise["sets"])
        for set_index in range(1, sets + 1):
            session.add(
                WorkoutSetORM(
                    user_id=user_id,
                    exercise=str(exercise["exercise"]),
                    weight_kg=float(exercise["target_weight_kg"]),
                    reps=int(exercise["reps"]),
                    set_index=set_index,
                    performed_at=performed_at,
                    notes=f"Applied from template: {template.name}",
                )
            )
            created += 1
    session.commit()
    return {"template_id": template_id, "created_sets": created, "performed_at": performed_at}


@router.get("/users/{user_id}/achievements")
def user_achievements(user_id: str = "demo", session: Session = Depends(get_session)) -> list[Achievement]:
    workouts = session.scalars(
        select(WorkoutSetORM)
        .where(WorkoutSetORM.user_id == user_id)
        .order_by(WorkoutSetORM.performed_at.asc(), WorkoutSetORM.id.asc())
    ).all()
    visits = session.scalars(
        select(VisitORM)
        .where(VisitORM.user_id == user_id)
        .order_by(VisitORM.checked_in_at.asc(), VisitORM.id.asc())
    ).all()
    templates = session.scalars(select(WorkoutTemplateORM).where(WorkoutTemplateORM.user_id == user_id)).all()

    training_dates = sorted({datetime.fromisoformat(row.performed_at).date() for row in workouts})
    if training_dates:
        latest_date = training_dates[-1]
        weekly_start = latest_date - timedelta(days=6)
        weekly_sessions = len([date for date in training_dates if date >= weekly_start])
    else:
        weekly_sessions = 0

    off_peak_visits = [
        visit
        for visit in visits
        if 10 <= datetime.fromisoformat(visit.checked_in_at).hour < 16
        or visit.active_people_at_checkin <= 45
    ]
    core_lifts = {"barbell bench press", "back squat", "incline dumbbell press", "lat pulldown"}
    core_sets = [row for row in workouts if row.exercise.lower() in core_lifts]
    distinct_exercises = sorted({row.exercise for row in workouts})
    cumulative_volume = 0.0
    volume_unlocked_at = ""
    for row in workouts:
        cumulative_volume += row.weight_kg * row.reps
        if not volume_unlocked_at and cumulative_volume >= 50_000:
            volume_unlocked_at = row.performed_at

    def nth_timestamp(timestamps: list[str], target: int) -> str:
        return timestamps[target - 1] if len(timestamps) >= target else ""

    def training_day_timestamp(target: int) -> str:
        if len(training_dates) < target:
            return ""
        target_day = training_dates[target - 1]
        matching = [row.performed_at for row in workouts if datetime.fromisoformat(row.performed_at).date() == target_day]
        return matching[-1] if matching else ""

    def first_set_at_or_above(exercise: str, weight: float) -> str:
        for row in workouts:
            if row.exercise.lower() == exercise.lower() and row.weight_kg >= weight:
                return row.performed_at
        return ""

    latest_activity = ""
    activity_timestamps = [row.performed_at for row in workouts] + [row.checked_in_at for row in visits]
    if activity_timestamps:
        latest_activity = max(activity_timestamps)

    computed = [
        {
            "id": 1,
            "code": "consistency_builder",
            "title": "Consistency Builder",
            "description": "Complete 4 distinct training days inside the latest rolling week.",
            "progress": float(weekly_sessions),
            "target": 4.0,
            "unlocked_at": training_day_timestamp(4),
        },
        {
            "id": 2,
            "code": "off_peak_hero",
            "title": "Off-Peak Hero",
            "description": "Check in during low-traffic or off-peak windows 5 times.",
            "progress": float(len(off_peak_visits)),
            "target": 5.0,
            "unlocked_at": nth_timestamp([visit.checked_in_at for visit in off_peak_visits], 5),
        },
        {
            "id": 3,
            "code": "strength_master",
            "title": "Strength Master",
            "description": "Log 20 quality working sets for core lifts.",
            "progress": float(len(core_sets)),
            "target": 20.0,
            "unlocked_at": nth_timestamp([row.performed_at for row in core_sets], 20),
        },
        {
            "id": 4,
            "code": "template_operator",
            "title": "Template Operator",
            "description": "Create or use saved workouts so sessions do not require manual re-entry.",
            "progress": float(len(templates)),
            "target": 3.0,
            "unlocked_at": nth_timestamp([row.created_at for row in sorted(templates, key=lambda item: item.created_at)], 3),
        },
        {
            "id": 5,
            "code": "volume_builder",
            "title": "Volume Builder",
            "description": "Accumulate 50,000 kg of logged training volume.",
            "progress": float(cumulative_volume),
            "target": 50_000.0,
            "unlocked_at": volume_unlocked_at,
        },
        {
            "id": 6,
            "code": "bench_milestone",
            "title": "Bench Milestone",
            "description": "Log a Barbell Bench Press set at 100 kg or more.",
            "progress": max([row.weight_kg for row in workouts if row.exercise.lower() == "barbell bench press"] or [0.0]),
            "target": 100.0,
            "unlocked_at": first_set_at_or_above("Barbell Bench Press", 100.0),
        },
        {
            "id": 7,
            "code": "exercise_explorer",
            "title": "Exercise Explorer",
            "description": "Log sets for 6 different exercises.",
            "progress": float(len(distinct_exercises)),
            "target": 6.0,
            "unlocked_at": next((row.performed_at for row in workouts if len({item.exercise for item in workouts if item.performed_at <= row.performed_at}) >= 6), ""),
        },
        {
            "id": 8,
            "code": "set_specialist",
            "title": "Set Specialist",
            "description": "Use advanced set annotations such as myo-reps, partials, or drop sets.",
            "progress": float(len([row for row in workouts if (row.modifiers_json or "{}") != "{}"])),
            "target": 3.0,
            "unlocked_at": nth_timestamp([row.performed_at for row in workouts if (row.modifiers_json or "{}") != "{}"], 3),
        },
        {
            "id": 9,
            "code": "attendance_base",
            "title": "Attendance Base",
            "description": "Track 3 QR check-ins in the member journal.",
            "progress": float(len(visits)),
            "target": 3.0,
            "unlocked_at": nth_timestamp([visit.checked_in_at for visit in visits], 3),
        },
        {
            "id": 10,
            "code": "secret_forecast",
            "title": "Hidden Forecast Badge",
            "description": "Secret requirement. Keep planning low-traffic sessions to reveal it.",
            "progress": 0.0,
            "target": 1.0,
            "unlocked_at": "",
        },
    ]
    return [
        Achievement(
            id=int(item["id"]),
            code=str(item["code"]),
            title=str(item["title"]),
            description=str(item["description"]),
            progress=min(float(item["progress"]), float(item["target"])),
            target=float(item["target"]),
            unlocked_at=str(item["unlocked_at"] or latest_activity if float(item["progress"]) >= float(item["target"]) else ""),
        )
        for item in computed
    ]


@router.get("/users/{user_id}/training-plan")
def training_plan(user_id: str, gym_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    preferences = serialize_preference(get_or_create_preferences(user_id, session))
    templates = list_workout_templates(user_id=user_id, session=session)
    slots = personalized_future_slots(user_id=user_id, gym_id=gym_id, max_results=preferences.weekly_goal_sessions, session=session)
    focus_cycle = ["Upper Strength", "Lower Progression", "Recovery Cardio", "Full Body Technique"]
    sessions: list[dict[str, object]] = []
    for index, slot in enumerate(slots):
        template = templates[index % len(templates)] if templates else None
        sessions.append(
            {
                "day_index": index + 1,
                "scheduled_at": slot["timestamp"],
                "window_label": slot.get("window_label") or format_training_window(datetime.fromisoformat(str(slot["timestamp"]))),
                "expected_people": slot["expected_people"],
                "focus": template.name if template else focus_cycle[index % len(focus_cycle)],
                "estimated_minutes": template.estimated_minutes if template else 55,
                "reason": "Scheduled in a low-traffic slot that matches user preferences.",
            }
        )
    return {
        "user_id": user_id,
        "gym_id": gym_id,
        "weekly_goal_sessions": preferences.weekly_goal_sessions,
        "sessions": sessions,
        "strategy": "Forecast-aware weekly microcycle using personalized low-traffic slots.",
    }


@router.get("/users/{user_id}/scheduled-workouts")
def list_scheduled_workouts(user_id: str = "demo", session: Session = Depends(get_session)) -> list[ScheduledWorkout]:
    rows = session.scalars(
        select(ScheduledWorkoutORM)
        .where(ScheduledWorkoutORM.user_id == user_id)
        .order_by(ScheduledWorkoutORM.scheduled_at.asc(), ScheduledWorkoutORM.id.asc())
    ).all()
    return [ScheduledWorkout.model_validate(row) for row in rows]


@router.post("/users/{user_id}/scheduled-workouts", status_code=201)
def create_scheduled_workout(
    user_id: str,
    payload: ScheduledWorkoutCreate,
    session: Session = Depends(get_session),
) -> ScheduledWorkout:
    row = ScheduledWorkoutORM(
        user_id=user_id,
        gym_id=payload.gym_id,
        template_id=payload.template_id,
        title=payload.title,
        scheduled_at=payload.scheduled_at,
        expected_people=payload.expected_people,
        status="planned",
        notes=payload.notes,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return ScheduledWorkout.model_validate(row)


@router.put("/users/{user_id}/scheduled-workouts/{scheduled_id}")
def update_scheduled_workout(
    user_id: str,
    scheduled_id: int,
    payload: ScheduledWorkoutUpdate,
    session: Session = Depends(get_session),
) -> ScheduledWorkout:
    row = session.get(ScheduledWorkoutORM, scheduled_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Scheduled workout not found.")
    allowed = {"planned", "completed", "skipped"}
    if payload.status not in allowed:
        raise HTTPException(status_code=422, detail=f"status must be one of: {', '.join(sorted(allowed))}")
    row.status = payload.status
    if payload.title is not None:
        row.title = payload.title
    if payload.scheduled_at:
        row.scheduled_at = payload.scheduled_at
    if payload.expected_people is not None:
        row.expected_people = payload.expected_people
    row.notes = payload.notes
    session.commit()
    session.refresh(row)
    return ScheduledWorkout.model_validate(row)


@router.delete("/users/{user_id}/scheduled-workouts/{scheduled_id}")
def delete_scheduled_workout(
    user_id: str,
    scheduled_id: int,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    row = session.get(ScheduledWorkoutORM, scheduled_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Scheduled workout not found.")
    session.delete(row)
    session.commit()
    return {"deleted": True, "scheduled_id": scheduled_id}


@router.post("/users/{user_id}/scheduled-workouts/from-plan", status_code=201)
def schedule_from_plan(user_id: str, gym_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    plan = training_plan(user_id=user_id, gym_id=gym_id, session=session)
    created = 0
    for item in plan["sessions"]:
        session.add(
            ScheduledWorkoutORM(
                user_id=user_id,
                gym_id=gym_id,
                template_id=0,
                title=str(item["focus"]),
                scheduled_at=str(item["scheduled_at"]),
                expected_people=float(item["expected_people"]),
                status="planned",
                notes=str(item["reason"]),
            )
        )
        created += 1
    session.commit()
    return {"created": created, "gym_id": gym_id}


@router.get("/users/{user_id}/activity-dashboard")
def activity_dashboard(user_id: str = "demo", session: Session = Depends(get_session)) -> dict[str, object]:
    visits = list_visits(user_id=user_id, session=session)
    workouts = list_workouts(user_id=user_id, session=session)
    achievements = user_achievements(user_id=user_id, session=session)
    templates = list_workout_templates(user_id=user_id, session=session)
    off_peak_visits = [visit for visit in visits if 10 <= datetime.fromisoformat(visit.checked_in_at).hour < 16]
    unlocked = [item for item in achievements if item.unlocked_at]
    return {
        "user_id": user_id,
        "visits": len(visits),
        "logged_sets": len(workouts),
        "templates": len(templates),
        "achievements_unlocked": len(unlocked),
        "off_peak_visit_share": round(len(off_peak_visits) / len(visits) * 100, 1) if visits else 0,
        "recent_visits": [visit.model_dump() for visit in visits[:5]],
        "recent_workouts": [workout.model_dump() for workout in workouts[:600]],
    }


@router.get("/manager/promotions")
def list_promotions(
    session: Session = Depends(get_session),
    current_user: AuthUser = Depends(require_manager_user),
) -> list[Promotion]:
    rows = session.scalars(select(PromotionORM).order_by(PromotionORM.starts_at.asc(), PromotionORM.id.asc())).all()
    return [Promotion.model_validate(row) for row in rows]


@router.post("/manager/promotions", status_code=201)
def create_promotion(
    payload: PromotionCreate,
    session: Session = Depends(get_session),
    current_user: AuthUser = Depends(require_manager_user),
) -> Promotion:
    copy = payload.notification_copy or (
        f"{payload.title}: train at {payload.starts_at} and get {payload.discount_percent}% off during a quiet slot."
    )
    row = PromotionORM(
        gym_id=payload.gym_id,
        title=payload.title,
        starts_at=payload.starts_at,
        discount_percent=payload.discount_percent,
        expected_people=payload.expected_people,
        status="scheduled",
        notification_copy=copy,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return Promotion.model_validate(row)


@router.get("/manager/notifications")
def manager_notifications(
    session: Session = Depends(get_session),
    current_user: AuthUser = Depends(require_manager_user),
) -> list[dict[str, object]]:
    promotions = list_promotions(session=session)
    return [
        {
            "promotion_id": promotion.id,
            "gym_id": promotion.gym_id,
            "send_at": promotion.starts_at,
            "channel": "in_app_demo",
            "status": promotion.status,
            "copy": promotion.notification_copy,
        }
        for promotion in promotions
    ]


@router.get("/users/{user_id}/workouts")
def list_workouts(user_id: str = "demo", session: Session = Depends(get_session)) -> list[WorkoutSet]:
    rows = session.scalars(
        select(WorkoutSetORM)
        .where(WorkoutSetORM.user_id == user_id)
        .order_by(WorkoutSetORM.performed_at.desc(), WorkoutSetORM.id.desc())
        .limit(800)
    ).all()
    results: list[WorkoutSet] = []
    for row in rows:
        item = WorkoutSet.model_validate(row)
        try:
            item.modifiers = WorkoutSetModifiers.model_validate(json.loads(getattr(row, "modifiers_json", "{}") or "{}"))
        except (ValueError, TypeError):
            item.modifiers = item.modifiers
        results.append(item)
    return results


@router.post("/users/{user_id}/workouts", status_code=201)
def create_workout_set(
    user_id: str,
    payload: WorkoutSetCreate,
    session: Session = Depends(get_session),
) -> WorkoutSet:
    performed_at = payload.performed_at or datetime.now().replace(microsecond=0).isoformat()
    row = WorkoutSetORM(
        user_id=user_id,
        exercise=payload.exercise,
        weight_kg=payload.weight_kg,
        reps=payload.reps,
        set_index=payload.set_index,
        performed_at=performed_at,
        notes=payload.notes,
        modifiers_json=json.dumps(payload.modifiers.model_dump()),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    result = WorkoutSet.model_validate(row)
    result.modifiers = payload.modifiers
    return result


@router.get("/users/{user_id}/progress")
def user_progress(user_id: str = "demo", session: Session = Depends(get_session)) -> dict[str, object]:
    rows = session.scalars(
        select(WorkoutSetORM)
        .where(WorkoutSetORM.user_id == user_id)
        .order_by(WorkoutSetORM.performed_at.asc(), WorkoutSetORM.id.asc())
    ).all()

    by_exercise: dict[str, list[WorkoutSetORM]] = {}
    for row in rows:
        by_exercise.setdefault(row.exercise, []).append(row)

    exercises: list[dict[str, object]] = []
    for exercise, exercise_rows in by_exercise.items():
        volumes = [row.weight_kg * row.reps for row in exercise_rows]
        best_weight = max(row.weight_kg for row in exercise_rows)
        total_volume = sum(volumes)
        exercises.append(
            {
                "exercise": exercise,
                "sets": len(exercise_rows),
                "best_weight_kg": best_weight,
                "total_volume_kg": round(total_volume, 1),
                "last_performed_at": exercise_rows[-1].performed_at,
            }
        )

    return {
        "user_id": user_id,
        "total_sets": len(rows),
        "tracked_exercises": len(exercises),
        "exercises": sorted(exercises, key=lambda item: item["total_volume_kg"], reverse=True),
    }


@router.get("/users/{user_id}/next-session")
def next_session(
    user_id: str = "demo",
    exercise: str = "Barbell Bench Press",
    session: Session = Depends(get_session),
) -> dict[str, object]:
    preferences = serialize_preference(get_or_create_preferences(user_id, session))
    rows = session.scalars(
        select(WorkoutSetORM)
        .where(WorkoutSetORM.user_id == user_id)
        .where(func.lower(WorkoutSetORM.exercise) == exercise.lower())
        .order_by(WorkoutSetORM.performed_at.desc(), WorkoutSetORM.id.desc())
        .limit(6)
    ).all()

    prediction = predict_next_set(
        exercise=exercise,
        history=[
            SetObservation(
                exercise=row.exercise,
                weight_kg=row.weight_kg,
                reps=row.reps,
                set_index=row.set_index,
                performed_at=row.performed_at,
            )
            for row in rows
        ],
        set_index=1,
        preferred_rep_mode=preferences.preferred_rep_mode,
        preferred_rep_min=preferences.preferred_rep_min,
        preferred_rep_max=preferences.preferred_rep_max,
    )
    return {
        "exercise": prediction.exercise,
        "target_weight_kg": round(prediction.target_weight_kg, 1),
        "target_reps": prediction.target_reps,
        "target_reps_min": prediction.target_reps_min,
        "target_reps_max": prediction.target_reps_max,
        "confidence": prediction.confidence,
        "model_version": prediction.model_version,
        "strategy": prediction.strategy,
        "target_kind": prediction.target_kind,
        "reason": prediction.reason,
    }


@router.post("/chat/local")
def chat_local(payload: ChatRequest, session: Session = Depends(get_session)) -> ChatResponse:
    message = payload.message.lower()
    unsafe_terms = ["pain", "injury", "doctor", "medical", "rehab", "heart", "dizzy", "біль", "травм"]
    if any(term in message for term in unsafe_terms):
        return ChatResponse(
            answer=(
                "I cannot diagnose injuries or provide medical treatment advice. "
                "If you feel pain, dizziness, or have a medical limitation, consult a qualified professional. "
                "I can still help adjust non-medical training logistics such as timing, logging, and workload tracking."
            ),
            sources=["Safety guardrail: medical and injury-related questions are out of scope."],
            safety_level="medical_refusal",
        )

    sources = ["GymFlow AI forecast metrics", "User workout history"]
    parts: list[str] = []

    if any(term in message for term in ["sleep", "сон", "recovery", "віднов", "rest better"]):
        parts.append(
            "For better training recovery, keep sleep advice simple: use a consistent sleep and wake time, "
            "avoid hard late-night sessions when they make it difficult to wind down, keep caffeine away from the late day, "
            "make the room dark and cool, and treat the final hour as a low-stimulation routine. "
            "If sleep problems are persistent or severe, speak with a qualified clinician."
        )
        sources.append("General recovery guidance guardrail")

    if payload.gym_id:
        try:
            is_future_slot_request = "tomorrow" in message or "future" in message or "quieter" in message
            slots = (
                preference_matched_future_slots(
                    user_id=payload.user_id,
                    gym_id=payload.gym_id,
                    max_results=1,
                    days=1,
                    session=session,
                )
                if is_future_slot_request
                else recommended_slots(gym_id=payload.gym_id, max_results=1)
            )
            if slots:
                best_slot = slots[0]
                timestamp = datetime.fromisoformat(str(best_slot["timestamp"]))
                window = str(best_slot.get("window_label") or format_training_window(timestamp))
                parts.append(
                    "The best low-traffic slot I see is "
                    f"{window}, with an expected load of "
                    f"{best_slot['expected_people']} people."
                )
                sources.append("Forecast-based slot recommendation")
            elif is_future_slot_request:
                preferences = serialize_preference(get_or_create_preferences(payload.user_id, session))
                parts.append(
                    "I do not see a forecast slot that matches your saved preferences "
                    f"({preferences.preferred_min_hour}:00-{preferences.preferred_max_hour}:00, "
                    f"weekdays {', '.join(str(day) for day in preferences.preferred_weekdays)}, "
                    f"up to {preferences.max_crowd_people:g} people) in that horizon."
                )
                sources.append("User preferences and future forecast filter")
        except HTTPException:
            parts.append("I could not load gym forecast context for this request.")

    if "plan" in message or "week" in message or "schedule" in message:
        if payload.gym_id:
            try:
                plan = training_plan(user_id=payload.user_id, gym_id=payload.gym_id, session=session)
                sessions = plan.get("sessions", [])
                if sessions:
                    preview = "; ".join(
                        f"{item.get('window_label') or format_training_window(datetime.fromisoformat(str(item['scheduled_at'])))} {item['focus']}"
                        for item in sessions[:3]
                    )
                    parts.append(f"I can schedule a forecast-aware week around these sessions: {preview}.")
                    sources.append("Forecast-aware weekly training plan")
            except HTTPException:
                parts.append("I could not build the weekly plan from the current forecast.")

    has_progression_intent = any(re.search(rf"\b{re.escape(term)}\b", message) for term in ["bench", "press", "next set", "target set", "progression"])
    if has_progression_intent:
        next_target = next_session(user_id=payload.user_id, exercise="Barbell Bench Press", session=session)
        parts.append(
            f"For {next_target['exercise']}, target {next_target['target_weight_kg']} kg "
            f"for {next_target['target_reps']} reps next session. {next_target['reason']}"
        )
        sources.append("Progressive overload rule based on logged sets")

    has_exercise_intent = any(
        re.search(rf"\b{re.escape(term)}\b", message)
        for term in ["exercise", "technique", "form", "cue", "mistake", "bench", "press", "squat", "deadlift", "curl", "row", "pulldown"]
    )
    exercise_hits = retrieve_exercise_knowledge(session=session, query=payload.message, limit=1) if has_exercise_intent else []
    if exercise_hits and exercise_hits[0].score > 0:
        exercise = exercise_hits[0].exercise
        setup = exercise.instructions[0] if exercise.instructions else "Use controlled setup and keep the movement within a stable range."
        mistake = exercise.mistakes[0] if exercise.mistakes else "Avoid rushing reps or losing control of the working range."
        parts.append(
            f"For {exercise.name}, focus on: {'; '.join(exercise.cues[:3])}. "
            f"Key setup: {setup} Common mistake to avoid: {mistake}."
        )
        sources.append(f"Exercise library: {exercise.name}")

    if not parts:
        parts.append(
            "I can help explain occupancy forecasts, recommend low-traffic training slots, "
            "turn your logged workout sets into next-session targets, schedule your weekly plan, "
            "and explain exercise technique from the local exercise library."
        )

    return ChatResponse(answer=" ".join(parts), sources=sources, safety_level="safe", actions=suggest_chat_actions(payload, session))


def infer_exercise_for_chat_action(payload: ChatRequest, session: Session) -> str:
    message = payload.message.lower()
    if "bench" in message or "press" in message:
        return "Barbell Bench Press"
    hits = retrieve_exercise_knowledge(session=session, query=payload.message, limit=1)
    if hits and hits[0].score > 0:
        return hits[0].exercise.name
    return "Barbell Bench Press"


def infer_preference_update(message: str) -> dict[str, object] | None:
    lowered = message.lower()
    if not any(term in lowered for term in ["prefer", "preference", "after", "before", "morning", "evening", "crowd"]):
        return None
    update: dict[str, object] = {}
    if "morning" in lowered:
        update.update({"preferred_min_hour": 7, "preferred_max_hour": 12})
    if "evening" in lowered or "after 18" in lowered or "after 6" in lowered:
        update.update({"preferred_min_hour": 18, "preferred_max_hour": 22})
    if "quiet" in lowered or "less crowd" in lowered or "crowd" in lowered:
        update["max_crowd_people"] = 30
    return update or None


def first_planned_reschedule_payload(payload: ChatRequest, session: Session) -> dict[str, object] | None:
    if not payload.gym_id:
        return None
    scheduled = session.scalar(
        select(ScheduledWorkoutORM)
        .where(ScheduledWorkoutORM.user_id == payload.user_id)
        .where(ScheduledWorkoutORM.status == "planned")
        .order_by(ScheduledWorkoutORM.scheduled_at.asc(), ScheduledWorkoutORM.id.asc())
    )
    if scheduled is None:
        return None
    slots = preference_matched_future_slots(user_id=payload.user_id, gym_id=payload.gym_id, max_results=1, days=3, session=session)
    if not slots:
        return None
    slot = slots[0]
    return {
        "scheduled_id": scheduled.id,
        "title": scheduled.title,
        "scheduled_at": slot["timestamp"],
        "expected_people": slot["expected_people"],
        "notes": f"Rescheduled by Coach AI: {slot['reason']}",
    }


def first_template_add_exercise_payload(payload: ChatRequest, session: Session) -> dict[str, object] | None:
    template = session.scalar(
        select(WorkoutTemplateORM)
        .where(WorkoutTemplateORM.user_id == payload.user_id)
        .order_by(WorkoutTemplateORM.created_at.desc(), WorkoutTemplateORM.id.desc())
    )
    if template is None:
        return None
    exercise = infer_exercise_for_chat_action(payload, session)
    target = next_session(user_id=payload.user_id, exercise=exercise, session=session)
    return {
        "template_id": template.id,
        "template_name": template.name,
        "exercise": {
            "exercise": target["exercise"],
            "sets": 3,
            "reps": target["target_reps"],
            "target_weight_kg": target["target_weight_kg"],
            "rest_seconds": 120,
        },
    }


def suggest_chat_actions(payload: ChatRequest, session: Session) -> list[ChatToolAction]:
    message = payload.message.lower()
    actions: list[ChatToolAction] = []
    add_to_existing_template_intent = "template" in message and any(term in message for term in ["add", "append", "include"])
    notification_intent = any(term in message for term in ["notification", "message draft", "push draft", "notify members"])
    manager_intent = any(term in message for term in ["promotion", "акція", "discount", "manager campaign", "push"])
    manager_intent = manager_intent or notification_intent
    if payload.gym_id and not manager_intent and any(term in message for term in ["plan", "week", "schedule"]):
        actions.append(
            ChatToolAction(
                type="schedule_week",
                label="Schedule forecast week",
                description="Create planned workouts from the current forecast-aware weekly plan.",
                payload={"gym_id": payload.gym_id},
            )
        )
    if not manager_intent and any(term in message for term in ["reschedule", "move", "перенеси"]):
        reschedule_payload = first_planned_reschedule_payload(payload, session)
        if reschedule_payload:
            actions.append(
                ChatToolAction(
                    type="reschedule_workout",
                    label="Move planned workout",
                    description="Move the nearest planned workout into a quieter forecast slot.",
                    payload=reschedule_payload,
                )
            )
    if any(term in message for term in ["log", "target", "set", "bench", "press"]):
        exercise = infer_exercise_for_chat_action(payload, session)
        target = next_session(user_id=payload.user_id, exercise=exercise, session=session)
        actions.append(
            ChatToolAction(
                type="log_target_set",
                label=f"Log {target['exercise']} target set",
                description=f"{target['target_weight_kg']} kg x {target['target_reps']} from the next-session rule.",
                payload={
                    "exercise": target["exercise"],
                    "weight_kg": target["target_weight_kg"],
                    "reps": target["target_reps"],
                    "set_index": 1,
                },
            )
        )
    if not manager_intent and add_to_existing_template_intent:
        add_payload = first_template_add_exercise_payload(payload, session)
        if add_payload:
            exercise_payload = add_payload["exercise"]
            actions.append(
                ChatToolAction(
                    type="add_exercise_to_template",
                    label=f"Add {exercise_payload['exercise']} to template",
                    description=f"Append this movement to {add_payload['template_name']}.",
                    payload=add_payload,
                )
            )
    if not add_to_existing_template_intent and any(term in message for term in ["template", "шаблон", "push day", "pull day", "leg day"]):
        exercise = infer_exercise_for_chat_action(payload, session)
        target = next_session(user_id=payload.user_id, exercise=exercise, session=session)
        actions.append(
            ChatToolAction(
                type="create_workout_template",
                label="Create workout template",
                description=f"Create a focused template around {target['exercise']}.",
                payload={
                    "name": f"{target['exercise']} Focus",
                    "focus": "Hypertrophy",
                    "estimated_minutes": 60,
                    "exercises": [
                        {
                            "exercise": target["exercise"],
                            "sets": 3,
                            "reps": target["target_reps"],
                            "target_weight_kg": target["target_weight_kg"],
                            "rest_seconds": 120,
                        }
                    ],
                },
            )
        )
    preference_payload = infer_preference_update(message)
    if preference_payload:
        actions.append(
            ChatToolAction(
                type="update_preferences",
                label="Update training preferences",
                description="Apply the preference change and refresh personalized recommendations.",
                payload=preference_payload,
            )
        )
    if payload.gym_id and notification_intent:
        slots = preference_matched_future_slots(user_id=payload.user_id, gym_id=payload.gym_id, max_results=1, days=3, session=session)
        if slots:
            slot = slots[0]
            actions.append(
                ChatToolAction(
                    type="manager_notification_draft",
                    label="Draft member notification",
                    description="Create an in-app demo notification draft for the quiet forecast slot.",
                    payload={
                        "gym_id": payload.gym_id,
                        "title": "Quiet-hour member notification",
                        "starts_at": slot["timestamp"],
                        "discount_percent": 5,
                        "expected_people": slot["expected_people"],
                        "notification_copy": "Your preferred gym is quiet soon. Book this slot if you want a calmer session.",
                    },
                )
            )
    elif payload.gym_id and manager_intent:
        slots = preference_matched_future_slots(user_id=payload.user_id, gym_id=payload.gym_id, max_results=1, days=3, session=session)
        if slots:
            slot = slots[0]
            actions.append(
                ChatToolAction(
                    type="manager_create_promotion",
                    label="Create off-peak promotion",
                    description="Draft a manager campaign for the quiet forecast slot.",
                    payload={
                        "gym_id": payload.gym_id,
                        "title": "Quiet-hour training boost",
                        "starts_at": slot["timestamp"],
                        "discount_percent": 10,
                        "expected_people": slot["expected_people"],
                        "notification_copy": "Train in a quieter slot today and get 10% off selected extras.",
                    },
                )
            )
    return actions[:3]


def serialize_chat_action(raw: object) -> ChatToolAction | None:
    try:
        return ChatToolAction.model_validate(raw)
    except (TypeError, ValueError):
        return None


def serialize_chat_citation(raw: object) -> ChatCitation | None:
    try:
        return ChatCitation.model_validate(raw)
    except (TypeError, ValueError):
        return None


def serialize_chat_message(row: ChatMessageORM) -> ChatMessageRecord:
    try:
        raw_actions = json.loads(row.actions_json or "[]")
    except json.JSONDecodeError:
        raw_actions = []
    actions = [action for item in raw_actions if (action := serialize_chat_action(item)) is not None]
    try:
        raw_citations = json.loads(getattr(row, "citations_json", "[]") or "[]")
    except json.JSONDecodeError:
        raw_citations = []
    citations = [citation for item in raw_citations if (citation := serialize_chat_citation(item)) is not None]
    return ChatMessageRecord(
        id=row.id,
        role=row.role,
        text=row.text,
        actions=actions,
        citations=citations,
        created_at=row.created_at,
    )


def serialize_chat_session(row: ChatSessionORM, session: Session) -> ChatSessionRecord:
    messages = session.scalars(
        select(ChatMessageORM)
        .where(ChatMessageORM.session_id == row.id)
        .order_by(ChatMessageORM.created_at.asc(), ChatMessageORM.id.asc())
    ).all()
    return ChatSessionRecord(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        pinned=bool(row.pinned),
        created_at=row.created_at,
        updated_at=row.updated_at,
        messages=[serialize_chat_message(message) for message in messages],
    )


def serialize_chat_tool_action(row: ChatToolActionORM) -> ChatToolActionTrace:
    try:
        payload = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    try:
        result = json.loads(row.result_json or "{}")
    except json.JSONDecodeError:
        result = {}
    return ChatToolActionTrace(
        id=row.id,
        session_id=row.session_id,
        user_id=row.user_id,
        action_type=row.action_type,
        label=row.label,
        payload=payload,
        status=row.status,
        created_at=row.created_at,
        executed_at=row.executed_at,
        result=result,
    )


@router.get("/users/{user_id}/chat-sessions")
def list_chat_sessions(user_id: str = "demo", session: Session = Depends(get_session)) -> list[ChatSessionRecord]:
    rows = session.scalars(
        select(ChatSessionORM)
        .where(ChatSessionORM.user_id == user_id)
        .order_by(ChatSessionORM.pinned.desc(), ChatSessionORM.updated_at.desc())
    ).all()
    return [serialize_chat_session(row, session) for row in rows]


@router.post("/users/{user_id}/chat-sessions", status_code=201)
def create_chat_session(user_id: str, payload: ChatSessionCreate, session: Session = Depends(get_session)) -> ChatSessionRecord:
    now = datetime.now().replace(microsecond=0).isoformat()
    row = ChatSessionORM(
        id=f"chat-{secrets.token_urlsafe(12)}",
        user_id=user_id,
        title=payload.title,
        pinned=0,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.add(
        ChatMessageORM(
            session_id=row.id,
            user_id=user_id,
            role="assistant",
            text="Ready.",
            actions_json="[]",
            citations_json="[]",
            created_at=now,
        )
    )
    session.commit()
    return serialize_chat_session(row, session)


@router.put("/users/{user_id}/chat-sessions/{chat_id}")
def update_chat_session(
    user_id: str,
    chat_id: str,
    payload: ChatSessionUpdate,
    session: Session = Depends(get_session),
) -> ChatSessionRecord:
    row = session.get(ChatSessionORM, chat_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    if payload.title is not None:
        row.title = payload.title
    if payload.pinned is not None:
        row.pinned = int(payload.pinned)
    row.updated_at = datetime.now().replace(microsecond=0).isoformat()
    session.commit()
    session.refresh(row)
    return serialize_chat_session(row, session)


@router.delete("/users/{user_id}/chat-sessions/{chat_id}")
def delete_chat_session(user_id: str, chat_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    row = session.get(ChatSessionORM, chat_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    message_rows = session.scalars(select(ChatMessageORM).where(ChatMessageORM.session_id == chat_id)).all()
    action_rows = session.scalars(select(ChatToolActionORM).where(ChatToolActionORM.session_id == chat_id)).all()
    for message in message_rows:
        session.delete(message)
    for action in action_rows:
        session.delete(action)
    session.delete(row)
    session.commit()
    return {"deleted": True, "chat_id": chat_id}


@router.post("/users/{user_id}/chat-sessions/{chat_id}/messages", status_code=201)
def create_chat_message(
    user_id: str,
    chat_id: str,
    payload: ChatMessageCreate,
    session: Session = Depends(get_session),
) -> ChatMessageRecord:
    chat = session.get(ChatSessionORM, chat_id)
    if chat is None or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    now = datetime.now().replace(microsecond=0).isoformat()
    row = ChatMessageORM(
        session_id=chat_id,
        user_id=user_id,
        role=payload.role,
        text=payload.text,
        actions_json=json.dumps([action.model_dump() for action in payload.actions]),
        citations_json=json.dumps([citation.model_dump() for citation in payload.citations]),
        created_at=now,
    )
    chat.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return serialize_chat_message(row)


@router.get("/users/{user_id}/chat-tool-actions")
def list_chat_tool_actions(user_id: str = "demo", session: Session = Depends(get_session)) -> list[ChatToolActionTrace]:
    rows = session.scalars(
        select(ChatToolActionORM)
        .where(ChatToolActionORM.user_id == user_id)
        .order_by(ChatToolActionORM.created_at.desc(), ChatToolActionORM.id.desc())
        .limit(50)
    ).all()
    return [serialize_chat_tool_action(row) for row in rows]


@router.post("/users/{user_id}/chat-tool-actions", status_code=201)
def create_chat_tool_action_trace(
    user_id: str,
    payload: ChatToolActionTraceCreate,
    session: Session = Depends(get_session),
) -> ChatToolActionTrace:
    chat = session.get(ChatSessionORM, payload.session_id)
    if chat is None or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    now = datetime.now().replace(microsecond=0).isoformat()
    row = ChatToolActionORM(
        session_id=payload.session_id,
        user_id=user_id,
        action_type=payload.action.type,
        label=payload.action.label,
        payload_json=json.dumps(payload.action.payload),
        status=payload.status,
        created_at=now,
        executed_at="" if payload.status == "suggested" else now,
        result_json="{}",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return serialize_chat_tool_action(row)


@router.put("/users/{user_id}/chat-tool-actions/{trace_id}")
def update_chat_tool_action_trace(
    user_id: str,
    trace_id: int,
    payload: ChatToolActionTraceUpdate,
    session: Session = Depends(get_session),
) -> ChatToolActionTrace:
    row = session.get(ChatToolActionORM, trace_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat tool action not found.")
    row.status = payload.status
    row.result_json = json.dumps(payload.result)
    row.executed_at = datetime.now().replace(microsecond=0).isoformat()
    session.commit()
    session.refresh(row)
    return serialize_chat_tool_action(row)


def citation_from_rag_hit(hit: object) -> ChatCitation:
    return ChatCitation(
        chunk_id=hit.chunk.chunk_id,
        title=hit.chunk.title,
        source_type=hit.chunk.source_type,
        score=hit.score,
        matched_terms=list(hit.matched_terms),
        source_url=hit.chunk.source_url,
        license=hit.chunk.license,
        preview=hit.chunk.text[:320],
    )


def build_rag_context(payload: ChatRequest, session: Session) -> tuple[str, list[str], list[ChatCitation]]:
    sources = ["GymFlow AI forecast metrics", "User workout history"]
    citations: list[ChatCitation] = []
    context_lines: list[str] = [
        f"User id: {payload.user_id}",
        f"Gym id: {payload.gym_id or 'not provided'}",
        f"User message: {payload.message}",
    ]

    if payload.gym_id:
        try:
            preferences = serialize_preference(get_or_create_preferences(payload.user_id, session))
            context_lines.append(
                "Saved training preferences: "
                f"preferred_hours={preferences.preferred_min_hour}:00-{preferences.preferred_max_hour}:00; "
                f"preferred_weekdays={preferences.preferred_weekdays}; "
                f"max_crowd_people={preferences.max_crowd_people:g}."
            )
            slots = preference_matched_future_slots(user_id=payload.user_id, gym_id=payload.gym_id, max_results=3, days=3, session=session)
            if slots:
                context_lines.append("Preference-matched low-traffic slots:")
                for slot in slots:
                    window = slot.get("window_label") or format_training_window(datetime.fromisoformat(str(slot["timestamp"])))
                    context_lines.append(f"- {window}: expected_people={slot['expected_people']}; reason={slot['reason']}")
                sources.append("Preference-matched forecast slot recommendation")
            else:
                context_lines.append("No low-traffic forecast slots match the saved preferences in the requested horizon.")
                sources.append("User preferences and future forecast filter")
        except HTTPException:
            context_lines.append("Forecast context unavailable for the selected gym.")

        try:
            plan = training_plan(user_id=payload.user_id, gym_id=payload.gym_id, session=session)
            sessions = plan.get("sessions", [])
            if sessions:
                context_lines.append("Forecast-aware weekly training plan:")
                for item in sessions[:4]:
                    window = item.get("window_label") or format_training_window(datetime.fromisoformat(str(item["scheduled_at"])))
                    context_lines.append(
                        f"- {window}: {item['focus']}, expected_people={item['expected_people']}, "
                        f"estimated_minutes={item['estimated_minutes']}, reason={item['reason']}"
                    )
                sources.append("Forecast-aware weekly training plan")
        except HTTPException:
            context_lines.append("Training plan unavailable for the selected gym.")

    recent_workouts = session.scalars(
        select(WorkoutSetORM)
        .where(WorkoutSetORM.user_id == payload.user_id)
        .order_by(WorkoutSetORM.performed_at.desc(), WorkoutSetORM.id.desc())
        .limit(8)
    ).all()
    if recent_workouts:
        context_lines.append("Recent logged workout sets:")
        for row in recent_workouts:
            context_lines.append(
                f"- {row.performed_at}: {row.exercise}, set {row.set_index}, {row.weight_kg} kg x {row.reps}, notes={row.notes}"
            )

    next_target = next_session(user_id=payload.user_id, exercise="Barbell Bench Press", session=session)
    context_lines.append(
        f"Bench press next-session rule output: {next_target['target_weight_kg']} kg x "
        f"{next_target['target_reps']} reps. Reason: {next_target['reason']}"
    )
    sources.append("Progressive overload rule based on logged sets")

    rag_hits = retrieve_rag_context(
        session=session,
        query=payload.message,
        user_id=payload.user_id,
        gym_id=payload.gym_id,
        limit=6,
    )
    if rag_hits:
        context_lines.append("Retrieved RAG chunks:")
        for hit in rag_hits:
            context_lines.append(format_rag_context(hit))
            sources.append(f"RAG source: {hit.chunk.source_type} / {hit.chunk.title}")
            citations.append(citation_from_rag_hit(hit))

    return "\n".join(context_lines), sorted(set(sources)), citations


@router.get("/rag/search")
def rag_search(
    q: str,
    user_id: str = "demo",
    gym_id: str | None = None,
    max_results: int = 6,
    session: Session = Depends(get_session),
    current_user: AuthUser = Depends(require_manager_user),
) -> list[dict[str, object]]:
    hits = retrieve_rag_context(
        session=session,
        query=q,
        user_id=user_id,
        gym_id=gym_id,
        limit=max_results,
    )
    return [
        {
            "chunk_id": hit.chunk.chunk_id,
            "title": hit.chunk.title,
            "source_type": hit.chunk.source_type,
            "score": hit.score,
            "matched_terms": list(hit.matched_terms),
            "source_url": hit.chunk.source_url,
            "license": hit.chunk.license,
            "metadata": hit.chunk.metadata or {},
            "preview": hit.chunk.text[:500],
        }
        for hit in hits
    ]


@router.get("/rag/evaluation-summary")
def rag_evaluation_summary(current_user: AuthUser = Depends(require_manager_user)) -> dict[str, object]:
    path = ROOT / "ml" / "reports" / "rag_retrieval_eval.json"
    if not path.exists():
        return {
            "status": "missing",
            "retrieval_method": "BM25-style lexical retrieval over GymFlow chunks",
            "note": "Run make rag-eval to generate the current non-vector RAG evaluation artifact.",
        }
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="RAG evaluation artifact is not valid JSON.")
    summary = report.get("summary", report)
    if not isinstance(summary, dict):
        raise HTTPException(status_code=500, detail="RAG evaluation summary is not a JSON object.")
    return {
        **summary,
        "rows": report.get("rows", []),
        "status": "ok",
        "artifact": str(path.relative_to(ROOT)),
    }


@router.get("/research/exercise-media-coverage")
def exercise_media_coverage_summary(current_user: AuthUser = Depends(require_manager_user)) -> dict[str, object]:
    path = ROOT / "ml" / "reports" / "exercise_media_coverage.json"
    if not path.exists():
        return {
            "status": "missing",
            "note": "Run make media-coverage to create the exercise media coverage artifact.",
            "artifact": str(path.relative_to(ROOT)),
        }
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Exercise media coverage artifact is not valid JSON.")
    summary = report.get("summary", report)
    if not isinstance(summary, dict):
        raise HTTPException(status_code=500, detail="Exercise media coverage summary is not a JSON object.")
    return {
        **summary,
        "missing_sample": list(report.get("missing", []))[:12],
        "artifact": str(path.relative_to(ROOT)),
    }


@router.get("/research/fine-tuning-readiness")
def fine_tuning_readiness_summary(current_user: AuthUser = Depends(require_manager_user)) -> dict[str, object]:
    path = ROOT / "ml" / "reports" / "fine_tuning_readiness.json"
    if not path.exists():
        return {
            "status": "missing",
            "note": "Run make finetune-dataset to create the fine-tuning dataset candidate artifact.",
            "artifact": str(path.relative_to(ROOT)),
            "fine_tuning_executed": False,
        }
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Fine-tuning readiness artifact is not valid JSON.")
    return {
        **report,
        "artifact": str(path.relative_to(ROOT)),
        "fine_tuning_executed": False,
    }


@router.get("/chat/provider-status")
def chat_provider_status() -> dict[str, object]:
    return get_ai_provider_status().__dict__


@router.post("/chat")
def chat(payload: ChatRequest, session: Session = Depends(get_session)) -> ChatResponse:
    message = payload.message.lower()
    unsafe_terms = ["pain", "injury", "doctor", "medical", "rehab", "heart", "dizzy", "біль", "травм"]
    if any(term in message for term in unsafe_terms):
        return ChatResponse(
            answer=(
                "I cannot diagnose injuries or provide medical treatment advice. "
                "If you feel pain, dizziness, or have a medical limitation, consult a qualified professional. "
                "I can still help adjust non-medical training logistics such as timing, logging, and workload tracking."
            ),
            sources=["Safety guardrail: medical and injury-related questions are out of scope."],
            safety_level="medical_refusal",
        )

    fallback = chat_local(payload=payload, session=session)
    context, sources, citations = build_rag_context(payload=payload, session=session)
    system_prompt = (
        "You are GymFlow AI Coach, a source-grounded fitness and gym-occupancy assistant. "
        "Use only the provided context for exercise facts, workout history, and occupancy forecasts. "
        "You may also answer basic recovery, sleep hygiene, hydration, and nutrition questions when framed as general "
        "training support, while clearly avoiding diagnosis, treatment, supplements-as-medicine, or medical claims. "
        "For hypertrophy guidance, anchor recommendations around progressive overload, training close to failure "
        "when appropriate, clean controlled technique, and lengthened-position control. "
        "Do not present every movement as equally useful for hypertrophy: cardio, planks, mobility, or very low-effort "
        "sets can support general fitness, but they are not the main overload signal. "
        "Do not diagnose injuries or provide medical treatment. "
        "When useful, explain uncertainty and mention that exercise media is third-party or locally seeded. "
        "When discussing gym timing, speak in practical training windows such as 11:00-12:30, not exact minute-level timestamps. "
        "When recommending training times, only recommend slots listed as preference-matched in the retrieved context. "
        "If the context says no slots match the saved preferences, say that directly instead of suggesting a different time. "
        "Keep answers practical, concise, and structured for a gym app user."
    )
    user_prompt = (
        "Answer the user's message using the retrieved GymFlow context below.\n\n"
        f"Retrieved context:\n{context}\n\n"
        f"User message:\n{payload.message}"
    )
    try:
        answer, model = generate_with_configured_provider(system_prompt=system_prompt, user_prompt=user_prompt)
        return ChatResponse(
            answer=answer,
            sources=[f"AI provider: Gemini ({model})", *sources],
            safety_level="safe",
            actions=suggest_chat_actions(payload, session),
            citations=citations,
        )
    except AIProviderError:
        return ChatResponse(
            answer=fallback.answer,
            sources=["AI fallback: deterministic local assistant", *fallback.sources],
            safety_level=fallback.safety_level,
            actions=fallback.actions,
            citations=citations,
        )
