from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.api.app.main import app


def main() -> None:
    with TestClient(app) as client:
        run_smoke(client)


def run_smoke(client: TestClient) -> None:
    health = client.get("/health")
    health.raise_for_status()

    login = client.post(
        "/auth/login",
        json={"email": "member@gymflow.ai", "password": "demo"},
    )
    login.raise_for_status()

    summary = client.get("/summary")
    summary.raise_for_status()

    gyms = client.get("/gyms")
    gyms.raise_for_status()
    gym_rows = gyms.json()
    if not gym_rows:
        raise RuntimeError("Expected at least one gym")

    metrics = client.get("/models/ml-metrics")
    metrics.raise_for_status()
    metric_rows = metrics.json()
    if not metric_rows:
        raise RuntimeError("Expected at least one ML metric row")

    first_gym_id = gym_rows[0]["gym_id"]
    forecast = client.get(f"/gyms/{first_gym_id}/forecast")
    forecast.raise_for_status()

    future_forecast = client.get(f"/gyms/{first_gym_id}/forecast/future")
    future_forecast.raise_for_status()

    slots = client.get(f"/recommendations/slots?gym_id={first_gym_id}")
    slots.raise_for_status()

    future_slots = client.get(f"/recommendations/future-slots?gym_id={first_gym_id}")
    future_slots.raise_for_status()

    preferences = client.get("/users/demo/preferences")
    preferences.raise_for_status()

    personalized_slots = client.get(f"/users/demo/recommendations/future-slots?gym_id={first_gym_id}")
    personalized_slots.raise_for_status()

    gamification = client.get("/users/demo/gamification")
    gamification.raise_for_status()

    visits = client.get("/users/demo/visits")
    visits.raise_for_status()

    templates = client.get("/users/demo/workout-templates")
    templates.raise_for_status()

    achievements = client.get("/users/demo/achievements")
    achievements.raise_for_status()

    exercises = client.get("/exercise-library")
    exercises.raise_for_status()
    exercise_rows = exercises.json()
    if not exercise_rows or "source_name" not in exercise_rows[0]:
        raise RuntimeError("Expected exercise source metadata")

    training_plan = client.get(f"/users/demo/training-plan?gym_id={first_gym_id}")
    training_plan.raise_for_status()

    scheduled_workouts = client.get("/users/demo/scheduled-workouts")
    scheduled_workouts.raise_for_status()

    activity_dashboard = client.get("/users/demo/activity-dashboard")
    activity_dashboard.raise_for_status()

    manager_overview = client.get("/manager/overview")
    manager_overview.raise_for_status()

    manager_locations = client.get("/manager/locations")
    manager_locations.raise_for_status()
    if not manager_locations.json():
        raise RuntimeError("Expected at least one manager location row")

    manager_campaigns = client.get("/manager/campaigns")
    manager_campaigns.raise_for_status()

    manager_promotions = client.get("/manager/promotions")
    manager_promotions.raise_for_status()

    manager_notifications = client.get("/manager/notifications")
    manager_notifications.raise_for_status()

    progress = client.get("/users/demo/progress")
    progress.raise_for_status()

    next_session = client.get("/users/demo/next-session?exercise=Barbell%20Bench%20Press")
    next_session.raise_for_status()

    chat = client.post(
        "/chat",
        json={
            "user_id": "demo",
            "gym_id": first_gym_id,
            "message": "When should I train and what should I do for bench press next?",
        },
    )
    chat.raise_for_status()

    chat_local = client.post(
        "/chat/local",
        json={
            "user_id": "demo",
            "gym_id": first_gym_id,
            "message": "When should I train and what should I do for bench press next?",
        },
    )
    chat_local.raise_for_status()

    provider_status = client.get("/chat/provider-status")
    provider_status.raise_for_status()

    print(
        {
            "health": health.json(),
            "auth_user": login.json()["user"]["user_id"],
            "rows": summary.json()["rows"],
            "gyms": len(gym_rows),
            "best_model": metric_rows[0]["model"],
            "forecast_points": len(forecast.json()),
            "future_forecast_points": len(future_forecast.json()),
            "recommended_slots": len(slots.json()),
            "future_recommended_slots": len(future_slots.json()),
            "personalized_slots": len(personalized_slots.json()),
            "weekly_sessions": gamification.json()["weekly_sessions"],
            "consistency_score": gamification.json()["consistency_score"],
            "visits": len(visits.json()),
            "templates": len(templates.json()),
            "achievements": len(achievements.json()),
            "exercises": len(exercise_rows),
            "plan_sessions": len(training_plan.json()["sessions"]),
            "scheduled_workouts": len(scheduled_workouts.json()),
            "activity_visits": activity_dashboard.json()["visits"],
            "manager_gyms": manager_overview.json()["gyms"],
            "manager_locations": len(manager_locations.json()),
            "manager_campaigns": len(manager_campaigns.json()),
            "manager_promotions": len(manager_promotions.json()),
            "manager_notifications": len(manager_notifications.json()),
            "logged_sets": progress.json()["total_sets"],
            "next_target": next_session.json()["target_weight_kg"],
            "chat_safety": chat.json()["safety_level"],
            "chat_local_safety": chat_local.json()["safety_level"],
            "chat_provider": provider_status.json()["provider"],
        }
    )


if __name__ == "__main__":
    main()
