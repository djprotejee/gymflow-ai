from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.api.app.anatomy import VALID_ANATOMY_REGION_IDS, allows_empty_primary_muscles
from apps.api.app.main import app
from gymflow_core.business_hours import is_business_open


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_business_hours() -> None:
    cases = [
        ("2026-05-20 06:59:00", False),
        ("2026-05-20 07:00:00", True),
        ("2026-05-20 21:59:00", True),
        ("2026-05-20 22:00:00", False),
        ("2026-05-23 08:59:00", False),
        ("2026-05-23 09:00:00", True),
        ("2026-05-23 17:59:00", True),
        ("2026-05-23 18:00:00", False),
    ]
    for value, expected in cases:
        actual = is_business_open(datetime.fromisoformat(value))
        assert_true(actual == expected, f"Business-hours mismatch for {value}: expected {expected}, got {actual}")


def test_forecast_and_recommendations(client: TestClient) -> dict[str, int]:
    gyms_response = client.get("/gyms")
    gyms_response.raise_for_status()
    gyms = gyms_response.json()
    assert_true(bool(gyms), "Expected at least one gym")
    gym_id = gyms[0]["gym_id"]

    future_response = client.get(f"/gyms/{gym_id}/forecast/future?days=7")
    future_response.raise_for_status()
    future_rows = future_response.json()
    assert_true(bool(future_rows), "Expected future forecast rows")
    for row in future_rows[:60]:
        prediction = float(row["prediction"])
        low = float(row.get("prediction_interval_low", prediction))
        high = float(row.get("prediction_interval_high", prediction))
        assert_true(low <= prediction <= high, "Prediction must be inside the uncertainty interval")

    recommendation_response = client.get(f"/recommendations/future-slots?gym_id={gym_id}&days=7&max_results=5")
    recommendation_response.raise_for_status()
    recommendations = recommendation_response.json()
    assert_true(bool(recommendations), "Expected future recommendations")
    for row in recommendations:
        timestamp = datetime.fromisoformat(row["timestamp"])
        assert_true(is_business_open(timestamp), f"Recommendation outside opening hours: {row['timestamp']}")

    return {"gyms": len(gyms), "future_rows_checked": min(60, len(future_rows)), "recommendations": len(recommendations)}


def test_preferences_and_gamification(client: TestClient, gym_id: str) -> dict[str, float | int]:
    payload = {
        "preferred_min_hour": 10,
        "preferred_max_hour": 18,
        "max_crowd_people": 90,
        "weekly_goal_sessions": 4,
        "preferred_weekdays": [0, 1, 2, 3, 4, 5, 6],
        "off_peak_bonus_enabled": True,
    }
    update_response = client.put("/users/demo/preferences", json=payload)
    update_response.raise_for_status()
    preferences = update_response.json()
    assert_true(preferences["preferred_min_hour"] == 10, "Preference update did not persist min hour")
    assert_true(preferences["preferred_max_hour"] == 18, "Preference update did not persist max hour")

    personalized_response = client.get(f"/users/demo/recommendations/future-slots?gym_id={gym_id}&days=7&max_results=5")
    personalized_response.raise_for_status()
    personalized = personalized_response.json()
    assert_true(bool(personalized), "Expected personalized recommendations")
    for row in personalized:
        timestamp = datetime.fromisoformat(row["timestamp"])
        hour_value = timestamp.hour + timestamp.minute / 60
        assert_true(10 <= hour_value < 18, f"Personalized slot outside preference window: {row['timestamp']}")
        assert_true(float(row["expected_people"]) <= 90, "Personalized slot exceeds crowd tolerance")

    gamification_response = client.get("/users/demo/gamification")
    gamification_response.raise_for_status()
    gamification = gamification_response.json()
    assert_true(0 <= float(gamification["consistency_score"]) <= 100, "Consistency score out of range")
    assert_true(int(gamification["weekly_sessions"]) >= 0, "Weekly sessions must be non-negative")
    return {
        "personalized_slots": len(personalized),
        "weekly_sessions": int(gamification["weekly_sessions"]),
        "consistency_score": float(gamification["consistency_score"]),
    }


def test_manager_endpoints(client: TestClient) -> dict[str, int]:
    overview_response = client.get("/manager/overview")
    overview_response.raise_for_status()
    overview = overview_response.json()
    assert_true(int(overview["gyms"]) > 0, "Manager overview must include gyms")

    locations_response = client.get("/manager/locations")
    locations_response.raise_for_status()
    locations = locations_response.json()
    assert_true(bool(locations), "Manager locations must not be empty")

    campaigns_response = client.get("/manager/campaigns")
    campaigns_response.raise_for_status()
    campaigns = campaigns_response.json()
    assert_true(bool(campaigns), "Manager campaigns must not be empty")

    promotions_response = client.get("/manager/promotions")
    promotions_response.raise_for_status()
    promotions = promotions_response.json()
    assert_true(bool(promotions), "Manager promotions must not be empty")

    notifications_response = client.get("/manager/notifications")
    notifications_response.raise_for_status()
    notifications = notifications_response.json()
    assert_true(bool(notifications), "Manager notifications must not be empty")
    return {
        "manager_locations": len(locations),
        "manager_campaigns": len(campaigns),
        "manager_promotions": len(promotions),
        "manager_notifications": len(notifications),
    }


def test_product_cabinet(client: TestClient, gym_id: str) -> dict[str, int]:
    visits_response = client.get("/users/demo/visits")
    visits_response.raise_for_status()
    visits = visits_response.json()
    assert_true(bool(visits), "Expected demo visits")

    templates_response = client.get("/users/demo/workout-templates")
    templates_response.raise_for_status()
    templates = templates_response.json()
    assert_true(bool(templates), "Expected demo workout templates")

    achievements_response = client.get("/users/demo/achievements")
    achievements_response.raise_for_status()
    achievements = achievements_response.json()
    assert_true(bool(achievements), "Expected demo achievements")

    exercises_response = client.get("/exercise-library")
    exercises_response.raise_for_status()
    exercises = exercises_response.json()
    assert_true(bool(exercises), "Expected exercise library")
    triceps = next((item for item in exercises if item["slug"] == "cable-triceps-pushdown"), None)
    assert_true(triceps is not None, "Expected cable triceps pushdown exercise seed")
    assert_true(triceps["source_name"], "Exercise seed must include source metadata")
    assert_true(triceps["media_type"] == "youtube", "Cable triceps pushdown should expose embedded YouTube media")
    assert_true(triceps["youtube_video_id"] == "6Fzep104f0s", "Cable triceps pushdown YouTube video id mismatch")
    assert_true(bool(triceps["primary_muscles"]), "Expected explicit primary muscle regions")
    assert_true("triceps-long-left" in triceps["primary_muscles"], "Expected triceps anatomy mapping for cable pushdown")
    assert_true(bool(triceps["media_gallery"]), "Expected exercise media gallery records")
    assert_true(triceps["media_gallery"][0]["requires_attribution"], "Media gallery records must preserve attribution flags")

    plan_response = client.get(f"/users/demo/training-plan?gym_id={gym_id}")
    plan_response.raise_for_status()
    plan = plan_response.json()
    assert_true(bool(plan["sessions"]), "Expected forecast-aware training plan sessions")

    scheduled_response = client.get("/users/demo/scheduled-workouts")
    scheduled_response.raise_for_status()
    scheduled = scheduled_response.json()
    assert_true(bool(scheduled), "Expected scheduled workouts")

    activity_response = client.get("/users/demo/activity-dashboard")
    activity_response.raise_for_status()
    activity = activity_response.json()
    assert_true(int(activity["visits"]) >= len(visits), "Activity dashboard visit count mismatch")
    return {
        "visits": len(visits),
        "templates": len(templates),
        "achievements": len(achievements),
        "exercises": len(exercises),
        "plan_sessions": len(plan["sessions"]),
        "scheduled_workouts": len(scheduled),
    }


def test_exercise_anatomy_contract(client: TestClient) -> dict[str, int]:
    exercises_response = client.get("/exercise-library")
    exercises_response.raise_for_status()
    exercises = exercises_response.json()
    assert_true(bool(exercises), "Expected exercise library for anatomy contract check")

    overrides_expected = {
        "bulgarian-split-squat": "glutes-left",
        "face-pull": "deltoid-rear-left",
        "hanging-leg-raise": "hip-flexors-left",
        "rowing-machine": "lats-mid-left",
    }
    for exercise in exercises:
        primary = list(exercise.get("primary_muscles") or [])
        secondary = list(exercise.get("secondary_muscles") or [])
        allow_empty_primary = allows_empty_primary_muscles(
            str(exercise.get("muscle_group") or ""),
            str(exercise.get("category") or ""),
        )
        assert_true(bool(primary) or allow_empty_primary, f"Exercise '{exercise['slug']}' is missing primary anatomy regions")
        invalid = sorted({item for item in [*primary, *secondary] if item not in VALID_ANATOMY_REGION_IDS})
        assert_true(not invalid, f"Exercise '{exercise['slug']}' has unsupported anatomy regions: {invalid}")

    for slug, required_region in overrides_expected.items():
        row = next((item for item in exercises if item["slug"] == slug), None)
        assert_true(row is not None, f"Expected exercise '{slug}' in anatomy contract check")
        assert_true(
            required_region in row["primary_muscles"] or required_region in row["secondary_muscles"],
            f"Exercise '{slug}' should include anatomy region '{required_region}'",
        )

    isolation_rows = {
        "cable-bayesian-curl": [],
        "leg-extension": [],
        "cable-fly": [],
    }
    for slug, expected_secondary in isolation_rows.items():
        row = next((item for item in exercises if item["slug"] == slug), None)
        assert_true(row is not None, f"Expected exercise '{slug}' in isolation anatomy check")
        assert_true(
            row["secondary_muscles"] == expected_secondary,
            f"Exercise '{slug}' should use secondary anatomy {expected_secondary}, got {row['secondary_muscles']}",
        )

    return {"validated_anatomy_exercises": len(exercises)}


def test_custom_exercise_and_preview_contract(client: TestClient) -> dict[str, int]:
    anatomy_response = client.get("/exercise-library/anatomy-regions")
    anatomy_response.raise_for_status()
    anatomy_groups = anatomy_response.json()
    assert_true(bool(anatomy_groups), "Expected anatomy region catalog")
    assert_true(any(group["group"] == "Arms" for group in anatomy_groups), "Expected Arms anatomy group")

    custom_response = client.post(
        "/users/demo/exercise-library",
        json={
            "name": "Regression Bayesian Curl",
            "category": "Accessory",
            "muscle_group": "Arms",
            "difficulty": "Beginner",
            "primary_muscles": ["biceps-left", "biceps-right"],
            "secondary_muscles": [],
            "allow_empty_primary": False,
        },
    )
    custom_response.raise_for_status()
    custom = custom_response.json()
    assert_true(custom["primary_muscles"] == ["biceps-left", "biceps-right"], "Custom exercise primary anatomy mismatch")
    assert_true(custom["secondary_muscles"] == [], "Custom exercise should allow empty secondary anatomy")
    custom_slug = str(custom["slug"])

    custom_update_response = client.put(
        f"/users/demo/exercise-library/{custom_slug}",
        json={
            "category": "Accessory",
            "muscle_group": "Arms",
            "difficulty": "Intermediate",
            "primary_muscles": ["biceps-left", "biceps-right"],
            "secondary_muscles": ["forearm-left", "forearm-right"],
            "allow_empty_primary": False,
            "instructions": ["Start stretched.", "Curl without swinging."],
            "cues": ["Control the elbow"],
            "mistakes": ["Turning it into a row"],
        },
    )
    custom_update_response.raise_for_status()
    custom_updated = custom_update_response.json()
    assert_true(custom_updated["secondary_muscles"] == ["forearm-left", "forearm-right"], "Custom exercise update should persist secondary anatomy")
    assert_true(custom_updated["instructions"][0] == "Start stretched.", "Custom exercise update should persist instructions")

    conditioning_response = client.post(
        "/users/demo/exercise-library",
        json={
            "name": "Regression Tempo Run",
            "category": "Cardio",
            "muscle_group": "Conditioning",
            "difficulty": "Beginner",
            "primary_muscles": [],
            "secondary_muscles": [],
            "allow_empty_primary": True,
        },
    )
    conditioning_response.raise_for_status()
    conditioning = conditioning_response.json()
    assert_true(conditioning["primary_muscles"] == [], "Conditioning exercise should allow empty primary anatomy")

    media_create_response = client.post(
        f"/users/demo/exercise-library/{custom_slug}/media",
        json={
            "media_type": "external_image",
            "media_url": "https://example.invalid/biceps.gif",
            "thumbnail_url": "https://example.invalid/biceps-thumb.jpg",
            "title": "Regression curl GIF",
            "source_name": "Regression fixture",
            "source_url": "https://example.invalid/source",
            "source_license": "Fixture only",
            "attribution": "Fixture attribution",
            "checked_at": "2026-05-24",
            "embed_allowed": True,
            "download_allowed": False,
            "requires_attribution": True,
            "sort_order": 0,
            "license_notes": "Fixture note",
        },
    )
    media_create_response.raise_for_status()
    created_media = media_create_response.json()
    assert_true(created_media["source_name"] == "Regression fixture", "Exercise media create should persist source name")

    media_delete_response = client.delete(f"/users/demo/exercise-library/{custom_slug}/media/{created_media['id']}")
    media_delete_response.raise_for_status()
    media_deleted = media_delete_response.json()
    assert_true(bool(media_deleted["deleted"]), "Exercise media delete should confirm deletion")

    preview_response = client.get("/exercise-library/import-preview")
    preview_response.raise_for_status()
    preview = preview_response.json()
    assert_true("status" in preview, "Preview route must return status")

    sample_preview_path = str(ROOT / "data" / "external" / "exercise_import_preview.sample.json")
    sample_summary_response = client.get(f"/exercise-library/import-preview?path={sample_preview_path}")
    sample_summary_response.raise_for_status()
    sample_summary = sample_summary_response.json()
    assert_true(int(sample_summary["records_total"]) >= 1, "Expected at least one sample preview record")

    import_response = client.post(
        "/exercise-library/import-preview",
        json={
            "path": sample_preview_path,
            "limit": 1,
            "only_with_media": True,
            "only_embed_ready_media": False,
        },
    )
    import_response.raise_for_status()
    imported = import_response.json()
    assert_true(int(imported["imported_records"]) == 1, "Expected the sample preview import to import one record")
    return {
        "anatomy_groups": len(anatomy_groups),
        "preview_records": int(sample_summary["records_total"]),
        "preview_imported": int(imported["imported_records"]),
    }


def test_chat_provider_fallback(client: TestClient, gym_id: str) -> dict[str, str]:
    provider_response = client.get("/chat/provider-status")
    provider_response.raise_for_status()
    provider = provider_response.json()
    assert_true("provider" in provider, "Expected provider status")

    chat_response = client.post(
        "/chat",
        json={
            "user_id": "demo",
            "gym_id": gym_id,
            "message": "Build a weekly plan and explain bench press next target.",
        },
    )
    chat_response.raise_for_status()
    chat_payload = chat_response.json()
    assert_true(chat_payload["safety_level"] == "safe", "Expected safe chat response")
    assert_true(bool(chat_payload["answer"]), "Expected non-empty chat response")
    assert_true(bool(chat_payload["sources"]), "Expected chat sources")

    local_response = client.post(
        "/chat/local",
        json={
            "user_id": "demo",
            "gym_id": gym_id,
            "message": "Explain cable triceps pushdown technique.",
        },
    )
    local_response.raise_for_status()
    local_payload = local_response.json()
    assert_true(local_payload["safety_level"] == "safe", "Expected safe local chat response")
    assert_true(
        any("Cable Triceps Pushdown" in source for source in local_payload["sources"]),
        "Expected local chat to retrieve the matching exercise-library record",
    )
    return {"chat_provider": str(provider["provider"]), "chat_local": local_payload["safety_level"]}


def test_auth(client: TestClient) -> dict[str, str]:
    member_login = client.post("/auth/login", json={"email": "member@gymflow.ai", "password": "demo"})
    member_login.raise_for_status()
    member_payload = member_login.json()
    assert_true(member_payload["user"]["role"] == "member", "Member login returned wrong role")
    member_token = member_payload["token"]

    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {member_token}"})
    me_response.raise_for_status()
    me_payload = me_response.json()
    assert_true(me_payload["user_id"] == "demo", "Bearer /auth/me did not resolve the member session")

    unauthorized_manager = client.get("/manager/overview", headers={"Authorization": f"Bearer {member_token}"})
    assert_true(unauthorized_manager.status_code == 403, "Member token must not access manager overview")

    manager_login = client.post("/auth/login", json={"email": "manager@gymflow.ai", "password": "manager"})
    manager_login.raise_for_status()
    manager_payload = manager_login.json()
    assert_true(manager_payload["user"]["role"] == "manager", "Manager login returned wrong role")
    manager_response = client.get("/manager/overview", headers={"Authorization": f"Bearer {manager_payload['token']}"})
    manager_response.raise_for_status()

    unique_email = f"regression-{datetime.utcnow().timestamp()}@gymflow.ai"
    register_response = client.post(
        "/auth/register",
        json={"email": unique_email, "password": "strong-demo-pass", "display_name": "Regression Member"},
    )
    register_response.raise_for_status()
    register_payload = register_response.json()
    assert_true(register_payload["user"]["role"] == "member", "Registered users must receive member role")

    logout_response = client.post("/auth/logout", headers={"Authorization": f"Bearer {register_payload['token']}"})
    logout_response.raise_for_status()
    revoked_response = client.get("/auth/me", headers={"Authorization": f"Bearer {register_payload['token']}"})
    assert_true(revoked_response.status_code == 401, "Logout must revoke the registered session token")
    return {"auth_member": member_payload["user"]["user_id"], "auth_manager": manager_payload["user"]["user_id"]}


def main() -> None:
    with TestClient(app) as client:
        health = client.get("/health")
        health.raise_for_status()
        test_business_hours()
        auth_summary = test_auth(client)

        gyms = client.get("/gyms").json()
        gym_id = gyms[0]["gym_id"]
        forecast_summary = test_forecast_and_recommendations(client)
        preference_summary = test_preferences_and_gamification(client, gym_id)
        product_summary = test_product_cabinet(client, gym_id)
        anatomy_summary = test_exercise_anatomy_contract(client)
        custom_preview_summary = test_custom_exercise_and_preview_contract(client)
        chat_summary = test_chat_provider_fallback(client, gym_id)
        manager_summary = test_manager_endpoints(client)

        print(
            json.dumps(
                {
                    "status": "ok",
                    **auth_summary,
                    **forecast_summary,
                    **preference_summary,
                    **product_summary,
                    **anatomy_summary,
                    **custom_preview_summary,
                    **chat_summary,
                    **manager_summary,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
