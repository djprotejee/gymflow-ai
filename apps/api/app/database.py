from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
import json

from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from .anatomy import resolve_anatomy_regions, validate_anatomy_assignment
from .config import get_database_url
from .models import (
    AchievementORM,
    Base,
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
    VisitORM,
    WorkoutSetORM,
    WorkoutTemplateORM,
)


DATABASE_URL = get_database_url()
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def build_demo_workout_history_records() -> list[dict[str, object]]:
    """Create deterministic demo set history for profile charts and exercise drilldowns."""
    plans = [
        (
            "Upper Strength",
            [("Barbell Bench Press", 82.5, 1.25), ("Incline Dumbbell Press", 30.0, 0.5), ("Lat Pulldown", 60.0, 0.75)],
        ),
        (
            "Lower Progression",
            [("Back Squat", 100.0, 1.5), ("Romanian Deadlift", 82.5, 1.0), ("Leg Press", 150.0, 2.5)],
        ),
        (
            "Pull Accessories",
            [("Barbell Curl", 32.5, 0.5), ("Cable Seated Row", 62.5, 0.75), ("Cable Tricep Pushdown", 40.0, 0.5)],
        ),
    ]
    start = datetime(2026, 1, 6, 18, 0, 0)
    records: list[dict[str, object]] = []
    for week in range(20):
        for session_index, (session_name, exercises) in enumerate(plans):
            session_start = start + timedelta(days=week * 7 + session_index * 2, hours=session_index % 2)
            for exercise_index, (exercise, base_weight, weekly_step) in enumerate(exercises):
                for set_index in range(1, 4):
                    performed_at = session_start + timedelta(minutes=exercise_index * 12 + set_index * 4)
                    weight = base_weight + week * weekly_step + (set_index - 1) * 2.5
                    reps = max(6, 12 - set_index - (week % 4 == 3))
                    modifiers = {}
                    if exercise == "Barbell Bench Press" and set_index == 3 and week in {4, 9, 14, 19}:
                        modifiers = {"myo_reps": True, "myo_reps_matching": week >= 14}
                    if exercise == "Lat Pulldown" and set_index == 2 and week in {6, 12, 18}:
                        modifiers = {"lengthened_partials": True}
                    if exercise == "Leg Press" and set_index == 3 and week in {7, 15}:
                        modifiers = {"drop_set": True}
                    records.append(
                        {
                            "user_id": "demo",
                            "exercise": exercise,
                            "weight_kg": round(weight, 1),
                            "reps": reps,
                            "set_index": set_index,
                            "performed_at": performed_at.isoformat(),
                            "notes": f"Demo multi-month history: {session_name}",
                            "modifiers_json": json.dumps(modifiers),
                        }
                    )
    return records

# Keep older local demo databases usable until Alembic migrations are introduced.
EXERCISE_LIBRARY_EXTRA_COLUMNS = {
    "media_type": "VARCHAR(40) DEFAULT '' NOT NULL",
    "media_url": "VARCHAR(500) DEFAULT '' NOT NULL",
    "youtube_video_id": "VARCHAR(80) DEFAULT '' NOT NULL",
    "source_name": "VARCHAR(160) DEFAULT '' NOT NULL",
    "source_url": "VARCHAR(500) DEFAULT '' NOT NULL",
    "source_license": "VARCHAR(180) DEFAULT '' NOT NULL",
    "attribution": "VARCHAR(500) DEFAULT '' NOT NULL",
    "checked_at": "VARCHAR(40) DEFAULT '' NOT NULL",
    "primary_muscles_json": "VARCHAR(2000) DEFAULT '[]' NOT NULL",
    "secondary_muscles_json": "VARCHAR(2000) DEFAULT '[]' NOT NULL",
}

# Keep older local demo databases usable until Alembic migrations are introduced.
WORKOUT_SETS_EXTRA_COLUMNS = {
    "modifiers_json": "VARCHAR(1200) DEFAULT '{}' NOT NULL",
}

# Keep older local demo databases usable until Alembic migrations are introduced.
CHAT_MESSAGES_EXTRA_COLUMNS = {
    "citations_json": "VARCHAR(4000) DEFAULT '[]' NOT NULL",
}


def primary_media_record_from_exercise(item: dict[str, object]) -> dict[str, object] | None:
    media_type = str(item.get("media_type", "")).strip()
    media_url = str(item.get("media_url", "")).strip()
    video_url = str(item.get("video_url", "")).strip()
    youtube_video_id = str(item.get("youtube_video_id", "")).strip()

    if media_type == "youtube" and youtube_video_id:
        return {
            "exercise_slug": str(item["slug"]),
            "media_type": "youtube",
            "media_url": f"https://www.youtube.com/watch?v={youtube_video_id}",
            "thumbnail_url": f"https://i.ytimg.com/vi/{youtube_video_id}/hqdefault.jpg",
            "title": f"{item['name']} technique video",
            "source_name": str(item["source_name"]),
            "source_url": str(item["source_url"]) or f"https://www.youtube.com/watch?v={youtube_video_id}",
            "source_license": str(item["source_license"]),
            "attribution": str(item["attribution"]),
            "checked_at": str(item["checked_at"]),
            "embed_allowed": 1,
            "download_allowed": 0,
            "requires_attribution": 1,
            "sort_order": 0,
            "license_notes": "Use only the official embedded player; do not download or rehost.",
        }

    if media_url:
        return {
            "exercise_slug": str(item["slug"]),
            "media_type": media_type or "external_image",
            "media_url": media_url,
            "thumbnail_url": media_url,
            "title": f"{item['name']} media reference",
            "source_name": str(item["source_name"]),
            "source_url": str(item["source_url"]) or media_url,
            "source_license": str(item["source_license"]),
            "attribution": str(item["attribution"]),
            "checked_at": str(item["checked_at"]),
            "embed_allowed": 0,
            "download_allowed": 0,
            "requires_attribution": 1,
            "sort_order": 0,
            "license_notes": "Review source terms before embedding or mirroring external media.",
        }

    if video_url:
        return {
            "exercise_slug": str(item["slug"]),
            "media_type": "link",
            "media_url": video_url,
            "thumbnail_url": "",
            "title": f"{item['name']} reference link",
            "source_name": str(item["source_name"]),
            "source_url": str(item["source_url"]) or video_url,
            "source_license": str(item["source_license"]),
            "attribution": str(item["attribution"]),
            "checked_at": str(item["checked_at"]),
            "embed_allowed": 0,
            "download_allowed": 0,
            "requires_attribution": 1,
            "sort_order": 0,
            "license_notes": "Reference link only; media rights must be checked separately.",
        }

    return None


def exercise_media_seed_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for item in exercise_seed_records():
        record = primary_media_record_from_exercise(item)
        if record is not None:
            records.append(record)
    return records


def exercise_seed_records() -> list[dict[str, object]]:
    records = [
        {
            "slug": "barbell-bench-press",
            "name": "Barbell Bench Press",
            "category": "Strength",
            "muscle_group": "Chest",
            "difficulty": "Intermediate",
            "image_hint": "bench-press",
            "video_url": "https://www.youtube.com/results?search_query=barbell+bench+press+proper+form",
            "media_type": "link",
            "media_url": "",
            "youtube_video_id": "",
            "source_name": "GymFlow AI local seed",
            "source_url": "",
            "source_license": "Project-authored demo technique notes",
            "attribution": "Demo educational notes written for the GymFlow AI prototype.",
            "checked_at": "2026-05-24",
            "instructions": [
                "Set shoulder blades down and back before unracking.",
                "Lower the bar under control to the lower chest.",
                "Press up while keeping feet planted and wrists stacked.",
            ],
            "cues": ["Chest up", "Elbows under the bar", "Controlled touch"],
            "mistakes": ["Bouncing the bar", "Losing upper-back tightness", "Flaring elbows too early"],
        },
        {
            "slug": "cable-triceps-pushdown",
            "name": "Cable Triceps Pushdown",
            "category": "Hypertrophy",
            "muscle_group": "Arms",
            "difficulty": "Beginner",
            "image_hint": "triceps-pushdown",
            "video_url": "https://www.youtube.com/watch?v=6Fzep104f0s",
            "media_type": "youtube",
            "media_url": "",
            "youtube_video_id": "6Fzep104f0s",
            "source_name": "Renaissance Periodization YouTube",
            "source_url": "https://www.youtube.com/watch?v=6Fzep104f0s",
            "source_license": "YouTube embedded player, third-party content",
            "attribution": "Video by Renaissance Periodization on YouTube; embedded only if the YouTube player allows it.",
            "checked_at": "2026-05-24",
            "instructions": [
                "Set the cable high and keep upper arms close to the torso.",
                "Extend the elbows down without turning the movement into a shoulder press.",
                "Control the return until the triceps are stretched while the shoulders stay stable.",
            ],
            "cues": ["Elbows pinned", "Full lockout", "Slow return"],
            "mistakes": ["Letting elbows drift forward", "Using body momentum", "Stopping short of elbow extension"],
        },
        {
            "slug": "back-squat",
            "name": "Back Squat",
            "category": "Strength",
            "muscle_group": "Legs",
            "difficulty": "Intermediate",
            "image_hint": "squat",
            "video_url": "https://www.youtube.com/results?search_query=back+squat+proper+form",
            "media_type": "link",
            "media_url": "",
            "youtube_video_id": "",
            "source_name": "GymFlow AI local seed",
            "source_url": "",
            "source_license": "Project-authored demo technique notes",
            "attribution": "Demo educational notes written for the GymFlow AI prototype.",
            "checked_at": "2026-05-24",
            "instructions": [
                "Brace before descent and keep the bar over mid-foot.",
                "Sit between the hips while maintaining knee tracking.",
                "Drive up with a stable torso and even foot pressure.",
            ],
            "cues": ["Brace first", "Knees track toes", "Drive through mid-foot"],
            "mistakes": ["Collapsing knees", "Relaxing at the bottom", "Good-morning the ascent"],
        },
        {
            "slug": "lat-pulldown",
            "name": "Lat Pulldown",
            "category": "Hypertrophy",
            "muscle_group": "Back",
            "difficulty": "Beginner",
            "image_hint": "lat-pulldown",
            "video_url": "https://www.youtube.com/results?search_query=lat+pulldown+proper+form",
            "media_type": "link",
            "media_url": "",
            "youtube_video_id": "",
            "source_name": "GymFlow AI local seed",
            "source_url": "",
            "source_license": "Project-authored demo technique notes",
            "attribution": "Demo educational notes written for the GymFlow AI prototype.",
            "checked_at": "2026-05-24",
            "instructions": [
                "Start with shoulders elevated and arms extended.",
                "Pull elbows down toward the ribs without leaning far back.",
                "Return slowly until the lats are stretched.",
            ],
            "cues": ["Elbows to pockets", "Ribs down", "Slow stretch"],
            "mistakes": ["Turning it into a row", "Using momentum", "Cutting range short"],
        },
        {
            "slug": "incline-dumbbell-press",
            "name": "Incline Dumbbell Press",
            "category": "Hypertrophy",
            "muscle_group": "Chest",
            "difficulty": "Intermediate",
            "image_hint": "incline-press",
            "video_url": "https://www.youtube.com/results?search_query=incline+dumbbell+press+proper+form",
            "media_type": "link",
            "media_url": "",
            "youtube_video_id": "",
            "source_name": "GymFlow AI local seed",
            "source_url": "",
            "source_license": "Project-authored demo technique notes",
            "attribution": "Demo educational notes written for the GymFlow AI prototype.",
            "checked_at": "2026-05-24",
            "instructions": [
                "Set the bench to a moderate incline.",
                "Lower dumbbells with elbows slightly tucked.",
                "Press up and in without crashing the dumbbells together.",
            ],
            "cues": ["Stable shoulder blades", "Smooth arc", "Control the bottom"],
            "mistakes": ["Too steep incline", "Shrugging shoulders", "Bouncing out of the bottom"],
        },
        {
            "slug": "romanian-deadlift",
            "name": "Romanian Deadlift",
            "category": "Strength",
            "muscle_group": "Hamstrings",
            "difficulty": "Intermediate",
            "image_hint": "hinge",
            "video_url": "https://www.youtube.com/results?search_query=romanian+deadlift+proper+form",
            "media_type": "link",
            "media_url": "",
            "youtube_video_id": "",
            "source_name": "GymFlow AI local seed",
            "source_url": "",
            "source_license": "Project-authored demo technique notes",
            "attribution": "Demo educational notes written for the GymFlow AI prototype.",
            "checked_at": "2026-05-24",
            "instructions": [
                "Start tall with the load close to the thighs.",
                "Hinge at the hips while keeping the spine braced and the bar close.",
                "Stop when hamstrings are strongly stretched, then drive hips forward.",
            ],
            "cues": ["Hips back", "Bar close", "Soft knees"],
            "mistakes": ["Squatting the movement", "Rounding under fatigue", "Letting the bar drift forward"],
        },
        {
            "slug": "leg-press",
            "name": "Leg Press",
            "category": "Hypertrophy",
            "muscle_group": "Legs",
            "difficulty": "Beginner",
            "image_hint": "leg-press",
            "video_url": "https://www.youtube.com/results?search_query=leg+press+proper+form",
            "media_type": "link",
            "media_url": "",
            "youtube_video_id": "",
            "source_name": "GymFlow AI local seed",
            "source_url": "",
            "source_license": "Project-authored demo technique notes",
            "attribution": "Demo educational notes written for the GymFlow AI prototype.",
            "checked_at": "2026-05-24",
            "instructions": [
                "Set foot position so knees track comfortably over toes.",
                "Lower under control without the pelvis lifting from the pad.",
                "Press through the platform without locking knees aggressively.",
            ],
            "cues": ["Full control", "Knees track", "Keep hips down"],
            "mistakes": ["Cutting depth too short", "Letting hips tuck hard", "Bouncing at the bottom"],
        },
        {
            "slug": "seated-cable-row",
            "name": "Seated Cable Row",
            "category": "Hypertrophy",
            "muscle_group": "Back",
            "difficulty": "Beginner",
            "image_hint": "cable-row",
            "video_url": "https://www.youtube.com/results?search_query=seated+cable+row+proper+form",
            "media_type": "link",
            "media_url": "",
            "youtube_video_id": "",
            "source_name": "GymFlow AI local seed",
            "source_url": "",
            "source_license": "Project-authored demo technique notes",
            "attribution": "Demo educational notes written for the GymFlow AI prototype.",
            "checked_at": "2026-05-24",
            "instructions": [
                "Start with a tall torso and stretched upper back.",
                "Pull elbows back while keeping ribs controlled.",
                "Pause briefly, then return until the back is stretched.",
            ],
            "cues": ["Tall chest", "Elbows back", "Stretch forward"],
            "mistakes": ["Excessive torso swing", "Shrugging into the neck", "Stopping before a full stretch"],
        },
        {
            "slug": "overhead-press",
            "name": "Overhead Press",
            "category": "Strength",
            "muscle_group": "Shoulders",
            "difficulty": "Intermediate",
            "image_hint": "overhead-press",
            "video_url": "https://www.youtube.com/results?search_query=overhead+press+proper+form",
            "media_type": "link",
            "media_url": "",
            "youtube_video_id": "",
            "source_name": "GymFlow AI local seed",
            "source_url": "",
            "source_license": "Project-authored demo technique notes",
            "attribution": "Demo educational notes written for the GymFlow AI prototype.",
            "checked_at": "2026-05-24",
            "instructions": [
                "Set the bar at upper chest with stacked wrists.",
                "Brace and press overhead while keeping the bar close.",
                "Lock out with shoulders elevated and ribs controlled.",
            ],
            "cues": ["Brace ribs", "Bar close", "Head through"],
            "mistakes": ["Overarching the lower back", "Pressing around the face", "Soft lockout"],
        },
        {
            "slug": "dumbbell-lateral-raise",
            "name": "Dumbbell Lateral Raise",
            "category": "Hypertrophy",
            "muscle_group": "Shoulders",
            "difficulty": "Beginner",
            "image_hint": "lateral-raise",
            "video_url": "https://www.youtube.com/results?search_query=dumbbell+lateral+raise+proper+form",
            "media_type": "link",
            "media_url": "",
            "youtube_video_id": "",
            "source_name": "GymFlow AI local seed",
            "source_url": "",
            "source_license": "Project-authored demo technique notes",
            "attribution": "Demo educational notes written for the GymFlow AI prototype.",
            "checked_at": "2026-05-24",
            "instructions": [
                "Start with dumbbells at the sides and a slight elbow bend.",
                "Raise arms out to the side under control.",
                "Lower slowly while keeping tension on the side delts.",
            ],
            "cues": ["Lead with elbows", "Soft wrists", "Slow negative"],
            "mistakes": ["Swinging the torso", "Turning it into a front raise", "Going too heavy to control"],
        },
        {
            "slug": "ez-bar-curl",
            "name": "EZ-Bar Curl",
            "category": "Hypertrophy",
            "muscle_group": "Arms",
            "difficulty": "Beginner",
            "image_hint": "curl",
            "video_url": "https://www.youtube.com/results?search_query=ez+bar+curl+proper+form",
            "media_type": "link",
            "media_url": "",
            "youtube_video_id": "",
            "source_name": "GymFlow AI local seed",
            "source_url": "",
            "source_license": "Project-authored demo technique notes",
            "attribution": "Demo educational notes written for the GymFlow AI prototype.",
            "checked_at": "2026-05-24",
            "instructions": [
                "Stand tall with elbows near the torso.",
                "Curl without letting shoulders roll forward.",
                "Lower until elbows are extended and biceps are stretched.",
            ],
            "cues": ["Elbows still", "Full stretch", "No hip swing"],
            "mistakes": ["Using momentum", "Shortening the bottom", "Letting elbows drift far forward"],
        },
        {
            "slug": "plank",
            "name": "Plank",
            "category": "Core",
            "muscle_group": "Core",
            "difficulty": "Beginner",
            "image_hint": "plank",
            "video_url": "https://www.youtube.com/results?search_query=plank+proper+form",
            "media_type": "link",
            "media_url": "",
            "youtube_video_id": "",
            "source_name": "GymFlow AI local seed",
            "source_url": "",
            "source_license": "Project-authored demo technique notes",
            "attribution": "Demo educational notes written for the GymFlow AI prototype.",
            "checked_at": "2026-05-24",
            "instructions": [
                "Set elbows under shoulders and brace the torso.",
                "Keep hips level without sagging or piking.",
                "Breathe steadily while maintaining position.",
            ],
            "cues": ["Ribs down", "Squeeze glutes", "Long spine"],
            "mistakes": ["Hips sagging", "Holding breath", "Neck craned upward"],
        },
    ]
    records.extend(additional_exercise_seed_records())
    records.extend(generated_variation_exercise_seed_records())
    for item in records:
        primary_muscles, secondary_muscles = resolve_anatomy_regions(str(item["slug"]), str(item["muscle_group"]))
        item["primary_muscles"] = primary_muscles
        item["secondary_muscles"] = secondary_muscles
        # Validate the seed contract here so broken anatomy ids fail before they silently reach the API or UI.
        validate_anatomy_assignment(str(item["slug"]), primary_muscles, secondary_muscles)
    return records


# Local exercise notes are project-authored; imported media must pass source review.
def local_exercise(
    slug: str,
    name: str,
    category: str,
    muscle_group: str,
    difficulty: str,
    image_hint: str,
    instructions: list[str],
    cues: list[str],
    mistakes: list[str],
) -> dict[str, object]:
    return {
        "slug": slug,
        "name": name,
        "category": category,
        "muscle_group": muscle_group,
        "difficulty": difficulty,
        "image_hint": image_hint,
        "video_url": f"https://www.youtube.com/results?search_query={name.lower().replace(' ', '+')}+proper+form",
        "media_type": "link",
        "media_url": "",
        "youtube_video_id": "",
        "source_name": "GymFlow AI local seed",
        "source_url": "",
        "source_license": "Project-authored demo technique notes",
        "attribution": "Demo educational notes written for the GymFlow AI prototype.",
        "checked_at": "2026-05-24",
        "instructions": instructions,
        "cues": cues,
        "mistakes": mistakes,
    }


def slugify_seed_name(value: str) -> str:
    return (
        value.lower()
        .replace("&", "and")
        .replace("/", " ")
        .replace("  ", " ")
        .strip()
        .replace(" ", "-")
    )


def generated_variation_exercise_seed_records() -> list[dict[str, object]]:
    variations = [
        ("Smith Machine Incline Bench Press", "Strength", "Chest", "Intermediate", "smith-incline-press"),
        ("Smith Machine Close-Grip Bench Press", "Strength", "Arms", "Intermediate", "smith-close-grip-bench"),
        ("Smith Machine Romanian Deadlift", "Strength", "Hamstrings", "Intermediate", "smith-rdl"),
        ("Smith Machine Hip Thrust", "Hypertrophy", "Glutes", "Beginner", "smith-hip-thrust"),
        ("Smith Machine Split Squat", "Hypertrophy", "Legs", "Intermediate", "smith-split-squat"),
        ("Smith Machine Calf Raise", "Hypertrophy", "Calves", "Beginner", "smith-calf-raise"),
        ("Smith Machine Upright Row", "Accessory", "Shoulders", "Beginner", "smith-upright-row"),
        ("Dumbbell Bench Press", "Strength", "Chest", "Intermediate", "dumbbell-bench"),
        ("Dumbbell Fly", "Hypertrophy", "Chest", "Beginner", "dumbbell-fly"),
        ("Dumbbell Pullover", "Accessory", "Back", "Intermediate", "dumbbell-pullover"),
        ("Dumbbell Goblet Lunge", "Hypertrophy", "Legs", "Beginner", "goblet-lunge"),
        ("Dumbbell Step-Up", "Hypertrophy", "Legs", "Beginner", "dumbbell-step-up"),
        ("Dumbbell Romanian Deadlift", "Strength", "Hamstrings", "Beginner", "dumbbell-rdl"),
        ("Dumbbell Hip Thrust", "Hypertrophy", "Glutes", "Beginner", "dumbbell-hip-thrust"),
        ("Dumbbell Seated Lateral Raise", "Accessory", "Shoulders", "Beginner", "seated-lateral-raise"),
        ("Dumbbell Front Raise", "Accessory", "Shoulders", "Beginner", "front-raise"),
        ("Dumbbell Shrug", "Accessory", "Back", "Beginner", "dumbbell-shrug"),
        ("Dumbbell Concentration Curl", "Accessory", "Arms", "Beginner", "concentration-curl"),
        ("Dumbbell Incline Curl", "Accessory", "Arms", "Beginner", "incline-curl"),
        ("Dumbbell Kickback", "Accessory", "Arms", "Beginner", "kickback"),
        ("Barbell Row", "Strength", "Back", "Intermediate", "barbell-row"),
        ("Pendlay Row", "Strength", "Back", "Advanced", "pendlay-row"),
        ("T-Bar Row", "Strength", "Back", "Intermediate", "tbar-row"),
        ("Barbell Hip Thrust", "Strength", "Glutes", "Intermediate", "barbell-hip-thrust"),
        ("Barbell Good Morning", "Strength", "Hamstrings", "Advanced", "good-morning"),
        ("Barbell Reverse Lunge", "Strength", "Legs", "Intermediate", "barbell-reverse-lunge"),
        ("Barbell Calf Raise", "Hypertrophy", "Calves", "Beginner", "barbell-calf-raise"),
        ("Barbell Drag Curl", "Accessory", "Arms", "Intermediate", "drag-curl"),
        ("Barbell Skull Crusher", "Accessory", "Arms", "Intermediate", "barbell-skull-crusher"),
        ("Cable Crossover", "Hypertrophy", "Chest", "Beginner", "cable-crossover"),
        ("Low Cable Fly", "Hypertrophy", "Chest", "Beginner", "low-cable-fly"),
        ("Single-Arm Cable Row", "Hypertrophy", "Back", "Beginner", "single-arm-cable-row"),
        ("Straight-Arm Pulldown", "Hypertrophy", "Back", "Beginner", "straight-arm-pulldown"),
        ("Cable Rear Delt Row", "Accessory", "Shoulders", "Beginner", "rear-delt-cable-row"),
        ("Cable Lateral Raise", "Accessory", "Shoulders", "Beginner", "cable-lateral-raise"),
        ("Cable Y Raise", "Accessory", "Shoulders", "Intermediate", "cable-y-raise"),
        ("Cable Bayesian Curl", "Accessory", "Arms", "Intermediate", "bayesian-curl"),
        ("Cable Hammer Curl", "Accessory", "Arms", "Beginner", "cable-hammer-curl"),
        ("Cable Overhead Curl", "Accessory", "Arms", "Beginner", "overhead-cable-curl"),
        ("Cable Rope Overhead Triceps Extension", "Accessory", "Arms", "Beginner", "rope-overhead-extension"),
        ("Cable Triceps Kickback", "Accessory", "Arms", "Beginner", "cable-kickback"),
        ("Machine Incline Chest Press", "Hypertrophy", "Chest", "Beginner", "machine-incline-press"),
        ("Machine Decline Chest Press", "Hypertrophy", "Chest", "Beginner", "machine-decline-press"),
        ("Machine Assisted Dip", "Hypertrophy", "Chest", "Beginner", "assisted-dip"),
        ("Machine Pullover", "Hypertrophy", "Back", "Beginner", "machine-pullover"),
        ("Machine High Row", "Hypertrophy", "Back", "Beginner", "machine-high-row"),
        ("Machine Low Row", "Hypertrophy", "Back", "Beginner", "machine-low-row"),
        ("Machine Lat Pulldown", "Hypertrophy", "Back", "Beginner", "machine-lat-pulldown"),
        ("Machine Reverse Fly", "Accessory", "Shoulders", "Beginner", "machine-reverse-fly"),
        ("Machine Lateral Raise", "Accessory", "Shoulders", "Beginner", "machine-lateral-raise"),
        ("Machine Preacher Curl", "Accessory", "Arms", "Beginner", "machine-preacher-curl"),
        ("Machine Triceps Extension", "Accessory", "Arms", "Beginner", "machine-triceps-extension"),
        ("Machine Dip", "Hypertrophy", "Arms", "Beginner", "machine-dip"),
        ("Belt Squat", "Strength", "Legs", "Intermediate", "belt-squat"),
        ("Pendulum Squat", "Hypertrophy", "Legs", "Intermediate", "pendulum-squat"),
        ("V-Squat Machine", "Hypertrophy", "Legs", "Beginner", "v-squat"),
        ("Horizontal Leg Press", "Hypertrophy", "Legs", "Beginner", "horizontal-leg-press"),
        ("Single-Leg Leg Press", "Hypertrophy", "Legs", "Intermediate", "single-leg-press"),
        ("Single-Leg Extension", "Hypertrophy", "Legs", "Beginner", "single-leg-extension"),
        ("Nordic Hamstring Curl", "Strength", "Hamstrings", "Advanced", "nordic-curl"),
        ("Glute Ham Raise", "Strength", "Hamstrings", "Advanced", "glute-ham-raise"),
        ("Cable Pull-Through", "Hypertrophy", "Glutes", "Beginner", "cable-pull-through"),
        ("Hip Abduction Machine", "Accessory", "Glutes", "Beginner", "hip-abduction"),
        ("Hip Adduction Machine", "Accessory", "Legs", "Beginner", "hip-adduction"),
        ("Seated Calf Raise", "Hypertrophy", "Calves", "Beginner", "seated-calf-raise"),
        ("Donkey Calf Raise", "Hypertrophy", "Calves", "Beginner", "donkey-calf-raise"),
        ("Standing Cable Crunch", "Core", "Core", "Beginner", "standing-cable-crunch"),
        ("Decline Sit-Up", "Core", "Core", "Beginner", "decline-situp"),
        ("Reverse Crunch", "Core", "Core", "Beginner", "reverse-crunch"),
        ("Dead Bug", "Core", "Core", "Beginner", "dead-bug"),
        ("Bird Dog", "Core", "Core", "Beginner", "bird-dog"),
        ("Farmer Carry", "Conditioning", "Core", "Beginner", "farmer-carry"),
        ("Sled Push", "Conditioning", "Conditioning", "Intermediate", "sled-push"),
        ("Sled Pull", "Conditioning", "Conditioning", "Intermediate", "sled-pull"),
        ("Battle Rope Wave", "Conditioning", "Conditioning", "Beginner", "battle-rope"),
        ("Kettlebell Swing", "Conditioning", "Glutes", "Intermediate", "kettlebell-swing"),
        ("Kettlebell Goblet Squat", "Hypertrophy", "Legs", "Beginner", "kettlebell-goblet-squat"),
        ("Kettlebell Clean", "Strength", "Shoulders", "Intermediate", "kettlebell-clean"),
        ("Kettlebell Snatch", "Strength", "Shoulders", "Advanced", "kettlebell-snatch"),
        ("Assisted Dip", "Hypertrophy", "Chest", "Beginner", "assisted-dip-bodyweight"),
        ("Parallel Bar Dip", "Strength", "Chest", "Intermediate", "parallel-bar-dip"),
        ("Chin-Up", "Strength", "Back", "Intermediate", "chin-up"),
        ("Neutral-Grip Pull-Up", "Strength", "Back", "Intermediate", "neutral-grip-pull-up"),
        ("Inverted Row", "Hypertrophy", "Back", "Beginner", "inverted-row"),
        ("Pike Push-Up", "Strength", "Shoulders", "Intermediate", "pike-pushup"),
        ("Diamond Push-Up", "Hypertrophy", "Arms", "Intermediate", "diamond-pushup"),
    ]
    variations.extend(
        [
            ("Smith Machine Flat Bench Press", "Strength", "Chest", "Intermediate", "smith-flat-bench"),
            ("Smith Machine Decline Bench Press", "Strength", "Chest", "Intermediate", "smith-decline-bench"),
            ("Smith Machine Shoulder Press", "Strength", "Shoulders", "Intermediate", "smith-shoulder-press"),
            ("Smith Machine Front Squat", "Strength", "Legs", "Intermediate", "smith-front-squat"),
            ("Smith Machine Box Squat", "Strength", "Legs", "Intermediate", "smith-box-squat"),
            ("Smith Machine Good Morning", "Strength", "Hamstrings", "Intermediate", "smith-good-morning"),
            ("Smith Machine Bent-Over Row", "Strength", "Back", "Intermediate", "smith-bent-row"),
            ("Smith Machine Reverse Lunge", "Hypertrophy", "Legs", "Intermediate", "smith-reverse-lunge"),
            ("Smith Machine Glute Bridge", "Hypertrophy", "Glutes", "Beginner", "smith-glute-bridge"),
            ("Smith Machine JM Press", "Accessory", "Arms", "Advanced", "smith-jm-press"),
            ("Dumbbell Incline Bench Press", "Strength", "Chest", "Intermediate", "dumbbell-incline-bench"),
            ("Dumbbell Decline Bench Press", "Strength", "Chest", "Intermediate", "dumbbell-decline-bench"),
            ("Dumbbell Neutral-Grip Bench Press", "Hypertrophy", "Chest", "Intermediate", "dumbbell-neutral-bench"),
            ("Dumbbell Chest Supported Row", "Hypertrophy", "Back", "Beginner", "dumbbell-chest-supported-row"),
            ("Dumbbell Seal Row", "Hypertrophy", "Back", "Intermediate", "dumbbell-seal-row"),
            ("Dumbbell Single-Arm Lat Row", "Hypertrophy", "Back", "Beginner", "dumbbell-single-arm-lat-row"),
            ("Dumbbell Bulgarian Split Squat", "Hypertrophy", "Legs", "Intermediate", "dumbbell-bulgarian-split-squat"),
            ("Dumbbell Walking Lunge", "Hypertrophy", "Legs", "Beginner", "dumbbell-walking-lunge"),
            ("Dumbbell Split Squat", "Hypertrophy", "Legs", "Beginner", "dumbbell-split-squat"),
            ("Dumbbell Stiff-Leg Deadlift", "Strength", "Hamstrings", "Intermediate", "dumbbell-stiff-leg-deadlift"),
            ("Dumbbell Glute Bridge", "Hypertrophy", "Glutes", "Beginner", "dumbbell-glute-bridge"),
            ("Dumbbell Rear Delt Fly", "Accessory", "Shoulders", "Beginner", "dumbbell-rear-delt-fly"),
            ("Dumbbell Zottman Curl", "Accessory", "Arms", "Beginner", "dumbbell-zottman-curl"),
            ("Dumbbell Spider Curl", "Accessory", "Arms", "Beginner", "dumbbell-spider-curl"),
            ("Barbell Incline Bench Press", "Strength", "Chest", "Intermediate", "barbell-incline-bench"),
            ("Barbell Overhead Press", "Strength", "Shoulders", "Intermediate", "barbell-overhead-press"),
            ("Barbell Front Rack Lunge", "Strength", "Legs", "Intermediate", "barbell-front-rack-lunge"),
            ("Barbell Deficit Romanian Deadlift", "Strength", "Hamstrings", "Advanced", "barbell-deficit-rdl"),
            ("Barbell High-Bar Squat", "Strength", "Legs", "Intermediate", "barbell-high-bar-squat"),
            ("Barbell Box Squat", "Strength", "Legs", "Intermediate", "barbell-box-squat"),
            ("Barbell Zercher Squat", "Strength", "Legs", "Advanced", "barbell-zercher-squat"),
            ("Barbell Seal Row", "Strength", "Back", "Intermediate", "barbell-seal-row"),
            ("Barbell JM Press", "Accessory", "Arms", "Advanced", "barbell-jm-press"),
            ("Barbell Landmine Squat", "Strength", "Legs", "Intermediate", "barbell-landmine-squat"),
            ("Cable Chest Press", "Hypertrophy", "Chest", "Beginner", "cable-chest-press"),
            ("Single-Arm Cable Chest Press", "Hypertrophy", "Chest", "Beginner", "single-arm-cable-chest-press"),
            ("Cable Face-Away Curl", "Accessory", "Arms", "Beginner", "cable-face-away-curl"),
            ("Cable High Curl", "Accessory", "Arms", "Beginner", "cable-high-curl"),
            ("Cable Front Raise", "Accessory", "Shoulders", "Beginner", "cable-front-raise"),
            ("Cable Upright Row", "Accessory", "Shoulders", "Beginner", "cable-upright-row"),
            ("Cable Wood Chop", "Core", "Core", "Beginner", "cable-wood-chop"),
            ("Cable Reverse Crunch", "Core", "Core", "Beginner", "cable-reverse-crunch"),
            ("Cable Hip Abduction", "Accessory", "Glutes", "Beginner", "cable-hip-abduction"),
            ("Cable Hip Adduction", "Accessory", "Legs", "Beginner", "cable-hip-adduction"),
            ("Cable Lat Prayer", "Hypertrophy", "Back", "Beginner", "cable-lat-prayer"),
            ("Cable Lean-Away Lateral Raise", "Accessory", "Shoulders", "Beginner", "cable-lean-away-lateral-raise"),
            ("Machine Chest Fly", "Hypertrophy", "Chest", "Beginner", "machine-chest-fly"),
            ("Machine Seated Row", "Hypertrophy", "Back", "Beginner", "machine-seated-row"),
            ("Machine Shoulder Press", "Strength", "Shoulders", "Beginner", "machine-shoulder-press"),
            ("Hack Squat Machine", "Strength", "Legs", "Intermediate", "hack-squat-machine"),
            ("Seated Leg Curl", "Hypertrophy", "Hamstrings", "Beginner", "seated-leg-curl"),
            ("Machine Glute Drive", "Hypertrophy", "Glutes", "Beginner", "machine-glute-drive"),
            ("Machine Ab Crunch", "Core", "Core", "Beginner", "machine-ab-crunch"),
            ("Adductor Machine", "Accessory", "Legs", "Beginner", "adductor-machine"),
            ("Abductor Machine", "Accessory", "Glutes", "Beginner", "abductor-machine"),
            ("Machine Seated Dip", "Hypertrophy", "Arms", "Beginner", "machine-seated-dip"),
            ("Machine Shrug", "Accessory", "Back", "Beginner", "machine-shrug"),
            ("Machine Pulldown Pullover", "Hypertrophy", "Back", "Beginner", "machine-pulldown-pullover"),
            ("Bodyweight Burpee", "Conditioning", "Conditioning", "Beginner", "bodyweight-burpee"),
            ("Mountain Climber", "Conditioning", "Conditioning", "Beginner", "mountain-climber"),
            ("Jump Squat", "Conditioning", "Legs", "Intermediate", "jump-squat"),
            ("Box Jump", "Conditioning", "Legs", "Intermediate", "box-jump"),
            ("Hollow Body Hold", "Core", "Core", "Beginner", "hollow-body-hold"),
            ("Hanging Knee Raise", "Core", "Core", "Beginner", "hanging-knee-raise"),
            ("Toes to Bar", "Core", "Core", "Advanced", "toes-to-bar"),
            ("Walking Plank", "Core", "Core", "Intermediate", "walking-plank"),
            ("Hand-Release Push-Up", "Hypertrophy", "Chest", "Beginner", "hand-release-pushup"),
            ("Decline Push-Up", "Hypertrophy", "Chest", "Beginner", "decline-pushup"),
            ("Bench Dip", "Hypertrophy", "Arms", "Beginner", "bench-dip"),
            ("Wall Sit", "Accessory", "Legs", "Beginner", "wall-sit"),
            ("Skater Jump", "Conditioning", "Legs", "Beginner", "skater-jump"),
            ("Kettlebell Suitcase Carry", "Conditioning", "Core", "Beginner", "kettlebell-suitcase-carry"),
            ("Kettlebell Front Rack Carry", "Conditioning", "Core", "Intermediate", "kettlebell-front-rack-carry"),
            ("Kettlebell Push Press", "Strength", "Shoulders", "Intermediate", "kettlebell-push-press"),
            ("Kettlebell Romanian Deadlift", "Strength", "Hamstrings", "Beginner", "kettlebell-romanian-deadlift"),
            ("Kettlebell High Pull", "Conditioning", "Shoulders", "Intermediate", "kettlebell-high-pull"),
            ("Kettlebell Reverse Lunge", "Hypertrophy", "Legs", "Beginner", "kettlebell-reverse-lunge"),
            ("Kettlebell Split Squat", "Hypertrophy", "Legs", "Beginner", "kettlebell-split-squat"),
            ("Kettlebell Single-Leg Deadlift", "Strength", "Hamstrings", "Intermediate", "kettlebell-single-leg-deadlift"),
            ("Kettlebell Dead Clean", "Strength", "Shoulders", "Intermediate", "kettlebell-dead-clean"),
            ("EZ-Bar Reverse Curl", "Accessory", "Arms", "Beginner", "ez-bar-reverse-curl"),
            ("EZ-Bar Spider Curl", "Accessory", "Arms", "Beginner", "ez-bar-spider-curl"),
            ("EZ-Bar Close-Grip Curl", "Accessory", "Arms", "Beginner", "ez-bar-close-grip-curl"),
            ("Landmine Press", "Strength", "Shoulders", "Intermediate", "landmine-press"),
            ("Landmine Row", "Strength", "Back", "Intermediate", "landmine-row"),
            ("Landmine Reverse Lunge", "Strength", "Legs", "Intermediate", "landmine-reverse-lunge"),
            ("Landmine Rotation", "Core", "Core", "Intermediate", "landmine-rotation"),
            ("Ski Erg Sprint", "Conditioning", "Conditioning", "Intermediate", "ski-erg-sprint"),
            ("Row Erg Sprint", "Conditioning", "Conditioning", "Intermediate", "row-erg-sprint"),
            ("Assault Bike Sprint", "Conditioning", "Conditioning", "Intermediate", "assault-bike-sprint"),
            ("Treadmill Sprint", "Conditioning", "Conditioning", "Intermediate", "treadmill-sprint"),
            ("Stair Climber", "Conditioning", "Conditioning", "Beginner", "stair-climber"),
            ("Smith Machine Bench Pull", "Strength", "Back", "Intermediate", "smith-bench-pull"),
            ("Smith Machine Sumo Squat", "Strength", "Legs", "Intermediate", "smith-sumo-squat"),
            ("Smith Machine Shrug", "Accessory", "Back", "Beginner", "smith-shrug"),
            ("Dumbbell Squeeze Press", "Hypertrophy", "Chest", "Beginner", "dumbbell-squeeze-press"),
            ("Dumbbell Reverse Fly", "Accessory", "Shoulders", "Beginner", "dumbbell-reverse-fly"),
            ("Dumbbell Pullover Bridge", "Accessory", "Chest", "Intermediate", "dumbbell-pullover-bridge"),
            ("Dumbbell Reverse Curl", "Accessory", "Arms", "Beginner", "dumbbell-reverse-curl"),
            ("Barbell Sumo Deadlift", "Strength", "Glutes", "Advanced", "barbell-sumo-deadlift"),
            ("Barbell Split Squat", "Strength", "Legs", "Intermediate", "barbell-split-squat"),
            ("Barbell Hack Squat", "Strength", "Legs", "Advanced", "barbell-hack-squat"),
            ("Barbell Floor Press", "Strength", "Chest", "Intermediate", "barbell-floor-press"),
            ("Cable Press-Around", "Hypertrophy", "Chest", "Beginner", "cable-press-around"),
            ("Cable Single-Arm Pulldown", "Hypertrophy", "Back", "Beginner", "cable-single-arm-pulldown"),
            ("Cable Seated Row", "Hypertrophy", "Back", "Beginner", "cable-seated-row"),
            ("Cable Drag Curl", "Accessory", "Arms", "Intermediate", "cable-drag-curl"),
            ("Cable JM Press", "Accessory", "Arms", "Advanced", "cable-jm-press"),
            ("Cable Skull Crusher", "Accessory", "Arms", "Beginner", "cable-skull-crusher"),
            ("Cable Lying Leg Curl", "Hypertrophy", "Hamstrings", "Intermediate", "cable-lying-leg-curl"),
            ("Cable Kneeling Crunch", "Core", "Core", "Beginner", "cable-kneeling-crunch"),
            ("Machine Iso-Lateral Chest Press", "Hypertrophy", "Chest", "Beginner", "machine-iso-lateral-chest-press"),
            ("Machine Incline Fly", "Hypertrophy", "Chest", "Beginner", "machine-incline-fly"),
            ("Machine T-Bar Row", "Hypertrophy", "Back", "Beginner", "machine-tbar-row"),
            ("Machine Hack Calf Raise", "Hypertrophy", "Calves", "Beginner", "machine-hack-calf-raise"),
            ("Machine Sissy Squat", "Hypertrophy", "Legs", "Intermediate", "machine-sissy-squat"),
            ("Machine Standing Leg Curl", "Hypertrophy", "Hamstrings", "Beginner", "machine-standing-leg-curl"),
            ("Machine Hip Thrust", "Hypertrophy", "Glutes", "Beginner", "machine-hip-thrust"),
            ("Bodyweight Walking Lunge", "Conditioning", "Legs", "Beginner", "bodyweight-walking-lunge"),
            ("Bodyweight Split Squat", "Hypertrophy", "Legs", "Beginner", "bodyweight-split-squat"),
            ("Bodyweight Glute Bridge", "Hypertrophy", "Glutes", "Beginner", "bodyweight-glute-bridge"),
            ("Bodyweight Reverse Hyper", "Accessory", "Glutes", "Beginner", "bodyweight-reverse-hyper"),
            ("Bodyweight Triceps Extension", "Accessory", "Arms", "Intermediate", "bodyweight-triceps-extension"),
            ("Bodyweight Chin-Up Hold", "Accessory", "Back", "Intermediate", "bodyweight-chinup-hold"),
            ("Kettlebell Thruster", "Conditioning", "Conditioning", "Intermediate", "kettlebell-thruster"),
            ("Kettlebell Lateral Lunge", "Hypertrophy", "Legs", "Intermediate", "kettlebell-lateral-lunge"),
            ("Kettlebell Halo", "Accessory", "Shoulders", "Beginner", "kettlebell-halo"),
            ("Landmine Hack Squat", "Strength", "Legs", "Intermediate", "landmine-hack-squat"),
            ("Landmine Single-Arm Row", "Strength", "Back", "Intermediate", "landmine-single-arm-row"),
            ("Landmine Push Press", "Strength", "Shoulders", "Intermediate", "landmine-push-press"),
            ("Prowler Sprint", "Conditioning", "Conditioning", "Intermediate", "prowler-sprint"),
            ("Sandbag Carry", "Conditioning", "Core", "Intermediate", "sandbag-carry"),
            ("Med Ball Slam", "Conditioning", "Conditioning", "Beginner", "med-ball-slam"),
            ("Jump Rope", "Conditioning", "Conditioning", "Beginner", "jump-rope"),
        ]
    )

    records: list[dict[str, object]] = []
    for name, category, muscle_group, difficulty, image_hint in variations:
        records.append(
            local_exercise(
                slugify_seed_name(name),
                name,
                category,
                muscle_group,
                difficulty,
                image_hint,
                [
                    f"Set up for {name.lower()} with stable joints and controlled range.",
                    "Move through the working range without bouncing or rushing the rep.",
                    "Finish the set when technique or target effort starts to break down.",
                ],
                ["Stable setup", "Controlled range", "Quality reps"],
                ["Using momentum", "Cutting range short", "Losing position under fatigue"],
            )
        )
    return records


def additional_exercise_seed_records() -> list[dict[str, object]]:
    return [
        local_exercise(
            "deadlift",
            "Deadlift",
            "Strength",
            "Back",
            "Advanced",
            "deadlift",
            [
                "Set the bar over mid-foot and brace before pulling.",
                "Push the floor away while keeping the bar close.",
                "Lock out by standing tall without leaning back excessively.",
            ],
            ["Brace hard", "Bar close", "Push the floor"],
            ["Yanking the bar", "Rounding early", "Overextending at lockout"],
        ),
        local_exercise(
            "front-squat",
            "Front Squat",
            "Strength",
            "Legs",
            "Intermediate",
            "front-squat",
            [
                "Set the bar high on the shoulders with elbows lifted.",
                "Squat between the hips while keeping the torso tall.",
                "Drive up with knees tracking and elbows high.",
            ],
            ["Elbows high", "Tall torso", "Knees forward"],
            ["Dropping elbows", "Losing brace", "Rushing the descent"],
        ),
        local_exercise(
            "bulgarian-split-squat",
            "Bulgarian Split Squat",
            "Hypertrophy",
            "Legs",
            "Intermediate",
            "split-squat",
            [
                "Place the rear foot on a stable bench.",
                "Lower under control until the front leg is loaded deeply.",
                "Drive through the front foot without bouncing.",
            ],
            ["Front foot pressure", "Slow lower", "Stable hips"],
            ["Pushing off the rear leg", "Short range", "Knee collapsing inward"],
        ),
        local_exercise(
            "walking-lunge",
            "Walking Lunge",
            "Hypertrophy",
            "Legs",
            "Beginner",
            "lunge",
            [
                "Step forward with a controlled stride.",
                "Lower until both legs share tension.",
                "Stand through the front leg and repeat smoothly.",
            ],
            ["Control each step", "Tall torso", "Push through front foot"],
            ["Rushing steps", "Wobbling hips", "Letting knees cave"],
        ),
        local_exercise(
            "lying-leg-curl",
            "Lying Leg Curl",
            "Hypertrophy",
            "Hamstrings",
            "Beginner",
            "leg-curl",
            [
                "Set the pad just above the heel.",
                "Curl under control while hips stay down.",
                "Lower slowly until the hamstrings are stretched.",
            ],
            ["Hips down", "Curl smoothly", "Full stretch"],
            ["Lifting hips", "Kicking the pad", "Cutting range short"],
        ),
        local_exercise(
            "standing-calf-raise",
            "Standing Calf Raise",
            "Hypertrophy",
            "Calves",
            "Beginner",
            "calf-raise",
            [
                "Set shoulders or hands against the machine support.",
                "Rise as high as possible through the big toe side.",
                "Lower slowly into a deep calf stretch.",
            ],
            ["Full stretch", "Tall raise", "Pause at top"],
            ["Bouncing", "Half reps", "Rolling ankles outward"],
        ),
        local_exercise(
            "hip-thrust",
            "Hip Thrust",
            "Hypertrophy",
            "Glutes",
            "Intermediate",
            "hip-thrust",
            [
                "Set upper back against a bench and brace the torso.",
                "Drive hips up until the torso and thighs align.",
                "Lower under control while keeping shins stable.",
            ],
            ["Ribs down", "Squeeze glutes", "Controlled lower"],
            ["Overarching", "Feet too far away", "Bouncing off the floor"],
        ),
        local_exercise(
            "pull-up",
            "Pull-Up",
            "Strength",
            "Back",
            "Intermediate",
            "pull-up",
            [
                "Start from a controlled hang.",
                "Pull elbows down until the chin clears the bar.",
                "Lower under control to a full stretch.",
            ],
            ["Elbows down", "Chest up", "Full hang"],
            ["Kipping unintentionally", "Short range", "Shrugging into the neck"],
        ),
        local_exercise(
            "chest-supported-row",
            "Chest Supported Row",
            "Hypertrophy",
            "Back",
            "Beginner",
            "row",
            [
                "Set the chest firmly against the pad.",
                "Pull elbows back without lifting the torso.",
                "Return until the upper back is stretched.",
            ],
            ["Chest pinned", "Elbows back", "Stretch forward"],
            ["Lifting off the pad", "Shrugging", "Jerking the handles"],
        ),
        local_exercise(
            "single-arm-dumbbell-row",
            "Single-Arm Dumbbell Row",
            "Hypertrophy",
            "Back",
            "Beginner",
            "dumbbell-row",
            [
                "Support the torso with one hand or knee.",
                "Row the dumbbell toward the hip.",
                "Lower until the lat is stretched without twisting hard.",
            ],
            ["Pull to hip", "Stable torso", "Deep stretch"],
            ["Torso rotation", "Curling the weight", "Stopping short"],
        ),
        local_exercise(
            "machine-chest-press",
            "Machine Chest Press",
            "Hypertrophy",
            "Chest",
            "Beginner",
            "machine-press",
            [
                "Set seat height so handles align around mid-chest.",
                "Press forward while shoulder blades stay stable.",
                "Return slowly into a comfortable chest stretch.",
            ],
            ["Chest tall", "Smooth press", "Controlled stretch"],
            ["Seat too low", "Shrugging", "Bouncing the stack"],
        ),
        local_exercise(
            "cable-fly",
            "Cable Fly",
            "Hypertrophy",
            "Chest",
            "Beginner",
            "cable-fly",
            [
                "Set cables around chest height.",
                "Bring hands together in a wide arc.",
                "Return until the chest is stretched while elbows stay soft.",
            ],
            ["Wide arc", "Soft elbows", "Chest stretch"],
            ["Pressing instead of flying", "Too much elbow bend", "Overstretching shoulders"],
        ),
        local_exercise(
            "push-up",
            "Push-Up",
            "Strength",
            "Chest",
            "Beginner",
            "push-up",
            [
                "Set hands under or slightly outside shoulders.",
                "Lower with a braced torso.",
                "Press up while keeping the body line stable.",
            ],
            ["Body line", "Chest to floor", "Elbows controlled"],
            ["Sagging hips", "Flaring elbows hard", "Short range"],
        ),
        local_exercise(
            "dumbbell-shoulder-press",
            "Dumbbell Shoulder Press",
            "Strength",
            "Shoulders",
            "Intermediate",
            "shoulder-press",
            [
                "Set dumbbells at shoulder level.",
                "Press up while ribs stay controlled.",
                "Lower to a comfortable shoulder stretch.",
            ],
            ["Ribs down", "Press vertical", "Control bottom"],
            ["Overarching", "Crashing dumbbells", "Uneven press"],
        ),
        local_exercise(
            "face-pull",
            "Face Pull",
            "Accessory",
            "Shoulders",
            "Beginner",
            "face-pull",
            [
                "Set the cable around face height.",
                "Pull toward the face with elbows high.",
                "Control the return until shoulders are stretched.",
            ],
            ["Elbows high", "Pull apart", "Slow return"],
            ["Turning it into a row", "Shrugging", "Using too much weight"],
        ),
        local_exercise(
            "rear-delt-fly",
            "Rear Delt Fly",
            "Hypertrophy",
            "Shoulders",
            "Beginner",
            "rear-delt",
            [
                "Set a slight hinge or use a machine pad.",
                "Move arms outward without shrugging.",
                "Lower slowly while keeping rear delts loaded.",
            ],
            ["Reach wide", "No shrug", "Slow negative"],
            ["Using traps", "Swinging", "Too much elbow bend"],
        ),
        local_exercise(
            "skull-crusher",
            "Skull Crusher",
            "Hypertrophy",
            "Arms",
            "Intermediate",
            "skull-crusher",
            [
                "Set upper arms slightly back from vertical.",
                "Lower the weight by bending elbows.",
                "Extend elbows without letting shoulders take over.",
            ],
            ["Elbows steady", "Deep stretch", "Smooth lockout"],
            ["Flaring elbows", "Moving shoulders too much", "Rushing the bottom"],
        ),
        local_exercise(
            "overhead-cable-triceps-extension",
            "Overhead Cable Triceps Extension",
            "Hypertrophy",
            "Arms",
            "Beginner",
            "overhead-triceps",
            [
                "Face away from the cable with elbows pointed forward.",
                "Let the triceps stretch overhead.",
                "Extend elbows while keeping upper arms stable.",
            ],
            ["Stretch long head", "Elbows forward", "Full extension"],
            ["Arching hard", "Elbows drifting wide", "Partial range"],
        ),
        local_exercise(
            "hammer-curl",
            "Hammer Curl",
            "Hypertrophy",
            "Arms",
            "Beginner",
            "hammer-curl",
            [
                "Hold dumbbells with neutral grip.",
                "Curl while keeping elbows near the torso.",
                "Lower until elbows are extended.",
            ],
            ["Neutral wrist", "Elbows still", "Controlled lower"],
            ["Swinging", "Short bottom", "Curling across the body unintentionally"],
        ),
        local_exercise(
            "preacher-curl",
            "Preacher Curl",
            "Hypertrophy",
            "Arms",
            "Beginner",
            "preacher-curl",
            [
                "Set the upper arms on the pad.",
                "Curl without lifting elbows from the support.",
                "Lower into a controlled biceps stretch.",
            ],
            ["Pad support", "Full lower", "Smooth curl"],
            ["Lifting elbows", "Bouncing bottom", "Going too heavy"],
        ),
        local_exercise(
            "hanging-leg-raise",
            "Hanging Leg Raise",
            "Core",
            "Core",
            "Intermediate",
            "leg-raise",
            [
                "Hang from a bar with shoulders controlled.",
                "Raise legs by curling the pelvis upward.",
                "Lower slowly without swinging.",
            ],
            ["Curl pelvis", "No swing", "Slow lower"],
            ["Using momentum", "Only flexing hips", "Losing shoulder position"],
        ),
        local_exercise(
            "cable-crunch",
            "Cable Crunch",
            "Core",
            "Core",
            "Beginner",
            "cable-crunch",
            [
                "Kneel under a high cable with rope near the head.",
                "Crunch by flexing the spine, not by pulling with arms.",
                "Return under control to a stretched position.",
            ],
            ["Ribs to pelvis", "Arms fixed", "Controlled stretch"],
            ["Hip hinge only", "Pulling with arms", "Rushing reps"],
        ),
        local_exercise(
            "pallof-press",
            "Pallof Press",
            "Core",
            "Core",
            "Beginner",
            "pallof",
            [
                "Stand sideways to the cable.",
                "Press the handle forward without rotating.",
                "Pause, then return with control.",
            ],
            ["Resist rotation", "Brace", "Slow press"],
            ["Twisting toward cable", "Leaning away", "Rushing the pause"],
        ),
        local_exercise(
            "treadmill-incline-walk",
            "Treadmill Incline Walk",
            "Cardio",
            "Conditioning",
            "Beginner",
            "treadmill",
            [
                "Choose an incline and pace that allow steady breathing.",
                "Walk tall without hanging heavily on the handles.",
                "Progress duration or incline gradually.",
            ],
            ["Tall posture", "Steady pace", "Gradual progression"],
            ["Holding handles hard", "Starting too fast", "Ignoring fatigue"],
        ),
        local_exercise(
            "stationary-bike",
            "Stationary Bike",
            "Cardio",
            "Conditioning",
            "Beginner",
            "bike",
            [
                "Set seat height so knees stay slightly bent at the bottom.",
                "Keep cadence smooth and resistance controlled.",
                "Increase duration or intervals based on the plan.",
            ],
            ["Smooth cadence", "Stable hips", "Controlled effort"],
            ["Seat too low", "Bouncing hips", "Resistance too high too soon"],
        ),
        local_exercise(
            "rowing-machine",
            "Rowing Machine",
            "Cardio",
            "Conditioning",
            "Intermediate",
            "rower",
            [
                "Drive with legs first, then swing the torso, then pull arms.",
                "Return arms, torso, then legs in sequence.",
                "Keep strokes smooth and repeatable.",
            ],
            ["Legs-body-arms", "Smooth recovery", "Tall finish"],
            ["Pulling arms first", "Rushing recovery", "Rounding heavily"],
        ),
        local_exercise(
            "elliptical",
            "Elliptical",
            "Cardio",
            "Conditioning",
            "Beginner",
            "elliptical",
            [
                "Set resistance to a sustainable effort.",
                "Keep posture tall and stride smooth.",
                "Use handles only as much as the workout goal requires.",
            ],
            ["Smooth stride", "Tall posture", "Even effort"],
            ["Leaning on handles", "Choppy cadence", "Resistance too high"],
        ),
        local_exercise(
            "goblet-squat",
            "Goblet Squat",
            "Strength",
            "Legs",
            "Beginner",
            "goblet-squat",
            [
                "Hold the dumbbell close to the chest.",
                "Squat between the hips with a braced torso.",
                "Stand up while keeping knees tracking.",
            ],
            ["Weight close", "Brace", "Knees track"],
            ["Letting weight drift", "Collapsing knees", "Relaxing bottom"],
        ),
        local_exercise(
            "sumo-deadlift",
            "Sumo Deadlift",
            "Strength",
            "Legs",
            "Advanced",
            "sumo-deadlift",
            [
                "Set a wide stance with shins close to the bar.",
                "Brace and push knees out before pulling.",
                "Stand tall while keeping the bar close.",
            ],
            ["Knees out", "Bar close", "Push floor"],
            ["Hips shooting up", "Knees caving", "Starting too far from bar"],
        ),
        local_exercise(
            "incline-machine-press",
            "Incline Machine Press",
            "Hypertrophy",
            "Chest",
            "Beginner",
            "incline-machine",
            [
                "Set seat so handles align with upper chest.",
                "Press smoothly without shrugging.",
                "Return into a controlled upper-chest stretch.",
            ],
            ["Upper chest line", "No shrug", "Slow return"],
            ["Seat mismatch", "Bouncing stack", "Losing shoulder position"],
        ),
        local_exercise(
            "pec-deck",
            "Pec Deck",
            "Hypertrophy",
            "Chest",
            "Beginner",
            "pec-deck",
            [
                "Set handles so the chest starts stretched but comfortable.",
                "Bring arms together without changing elbow angle much.",
                "Return slowly to the stretched position.",
            ],
            ["Chest stretch", "Arc together", "Controlled return"],
            ["Shoulder discomfort ignored", "Pressing instead of flying", "Fast negatives"],
        ),
        local_exercise(
            "assisted-pull-up",
            "Assisted Pull-Up",
            "Strength",
            "Back",
            "Beginner",
            "assisted-pull-up",
            [
                "Set assistance so full range is possible.",
                "Pull elbows down and chest toward the handles.",
                "Lower under control to a full stretch.",
            ],
            ["Full range", "Elbows down", "Controlled lower"],
            ["Too little assistance", "Short reps", "Swinging"],
        ),
        local_exercise(
            "machine-row",
            "Machine Row",
            "Hypertrophy",
            "Back",
            "Beginner",
            "machine-row",
            [
                "Set chest pad and handles to fit the torso.",
                "Pull handles while keeping chest supported.",
                "Return to a full stretch without losing control.",
            ],
            ["Chest supported", "Elbows back", "Full stretch"],
            ["Lifting chest", "Rushing reps", "Shrugging"],
        ),
        local_exercise(
            "arnold-press",
            "Arnold Press",
            "Hypertrophy",
            "Shoulders",
            "Intermediate",
            "arnold-press",
            [
                "Start with dumbbells in front of the shoulders.",
                "Rotate and press overhead smoothly.",
                "Lower along the same path under control.",
            ],
            ["Smooth rotation", "Ribs down", "Controlled lower"],
            ["Too much load", "Overarching", "Rushing rotation"],
        ),
        local_exercise(
            "upright-row",
            "Upright Row",
            "Accessory",
            "Shoulders",
            "Intermediate",
            "upright-row",
            [
                "Use a comfortable grip width.",
                "Pull elbows up only through a pain-free range.",
                "Lower slowly with control.",
            ],
            ["Comfortable range", "Elbows lead", "Slow lower"],
            ["Forcing painful height", "Shrugging hard", "Jerking the bar"],
        ),
        local_exercise(
            "rope-cable-curl",
            "Rope Cable Curl",
            "Hypertrophy",
            "Arms",
            "Beginner",
            "rope-curl",
            [
                "Set the cable low with a rope attachment.",
                "Curl while elbows stay near the torso.",
                "Separate rope ends slightly near the top if comfortable.",
            ],
            ["Elbows still", "Full curl", "Slow lower"],
            ["Leaning back", "Partial bottom", "Shoulders rolling"],
        ),
        local_exercise(
            "close-grip-bench-press",
            "Close-Grip Bench Press",
            "Strength",
            "Arms",
            "Intermediate",
            "close-grip-bench",
            [
                "Use a grip just narrower than regular bench press.",
                "Lower to lower chest while elbows stay controlled.",
                "Press up without losing upper-back tightness.",
            ],
            ["Tight upper back", "Elbows controlled", "Press strong"],
            ["Grip too narrow", "Wrists bending", "Bouncing"],
        ),
        local_exercise(
            "ab-wheel-rollout",
            "Ab Wheel Rollout",
            "Core",
            "Core",
            "Advanced",
            "ab-wheel",
            [
                "Start from knees with ribs tucked.",
                "Roll forward only as far as control allows.",
                "Pull back by bracing the abs, not by hips only.",
            ],
            ["Ribs down", "Control range", "Brace back"],
            ["Lower-back sag", "Rolling too far", "Hip-only pullback"],
        ),
        local_exercise(
            "side-plank",
            "Side Plank",
            "Core",
            "Core",
            "Beginner",
            "side-plank",
            [
                "Set elbow under shoulder.",
                "Lift hips until the body forms a straight line.",
                "Hold while breathing and keeping hips stacked.",
            ],
            ["Hips high", "Stacked body", "Steady breathing"],
            ["Dropping hips", "Rolling forward", "Shrugging shoulder"],
        ),
        local_exercise(
            "smith-machine-bench-press",
            "Smith Machine Bench Press",
            "Strength",
            "Chest",
            "Beginner",
            "smith-bench",
            [
                "Set the bench so the bar tracks to mid chest.",
                "Keep shoulders pinned and feet planted.",
                "Press through a full range without bouncing.",
            ],
            ["Shoulders pinned", "Full range", "Steady tempo"],
            ["Bench too far forward", "Bouncing reps", "Letting wrists fold back"],
        ),
        local_exercise(
            "smith-machine-squat",
            "Smith Machine Squat",
            "Hypertrophy",
            "Legs",
            "Beginner",
            "smith-squat",
            [
                "Set feet to allow comfortable depth and knee tracking.",
                "Brace and descend under control.",
                "Drive up while keeping even foot pressure.",
            ],
            ["Brace first", "Knees track", "Control depth"],
            ["Feet too far forward", "Cutting depth short", "Relaxing at the bottom"],
        ),
        local_exercise(
            "leg-extension",
            "Leg Extension",
            "Hypertrophy",
            "Legs",
            "Beginner",
            "leg-extension",
            [
                "Align the knee with the machine pivot.",
                "Extend smoothly without kicking.",
                "Lower under control until quads are stretched.",
            ],
            ["Smooth extension", "Control lowering", "Full stretch"],
            ["Kicking the stack", "Partial range", "Letting hips lift off the seat"],
        ),
        local_exercise(
            "seated-leg-curl",
            "Seated Leg Curl",
            "Hypertrophy",
            "Hamstrings",
            "Beginner",
            "seated-leg-curl",
            [
                "Set the back pad so hips stay stable.",
                "Curl while keeping the torso braced.",
                "Return slowly into a full hamstring stretch.",
            ],
            ["Hips stable", "Full curl", "Slow return"],
            ["Leaning back", "Shortening the stretch", "Jerking the weight"],
        ),
        local_exercise(
            "hack-squat-machine",
            "Hack Squat Machine",
            "Hypertrophy",
            "Legs",
            "Intermediate",
            "hack-squat",
            [
                "Set feet to allow depth with knee comfort.",
                "Lower until quads are loaded and hips stay under you.",
                "Drive up without locking out aggressively.",
            ],
            ["Deep control", "Even pressure", "Drive through mid-foot"],
            ["Cutting depth", "Knees collapsing", "Bouncing the bottom"],
        ),
        local_exercise(
            "machine-shoulder-press",
            "Machine Shoulder Press",
            "Hypertrophy",
            "Shoulders",
            "Beginner",
            "machine-shoulder-press",
            [
                "Set seat height so handles start near ear level.",
                "Press up without shrugging hard.",
                "Lower under control to a comfortable stretch.",
            ],
            ["No hard shrug", "Smooth press", "Control down"],
            ["Flaring elbows too wide", "Short range", "Bouncing off the bottom"],
        ),
        local_exercise(
            "smith-machine-overhead-press",
            "Smith Machine Overhead Press",
            "Strength",
            "Shoulders",
            "Beginner",
            "smith-press",
            [
                "Set the bench slightly upright or stand if preferred.",
                "Keep ribs down and press the bar overhead.",
                "Lower with control until upper arms are near parallel.",
            ],
            ["Ribs down", "Press straight", "Control lowering"],
            ["Overarching back", "Cutting range", "Shrugging into the top"],
        ),
        local_exercise(
            "cable-lat-prayer-pulldown",
            "Cable Lat Prayer Pulldown",
            "Hypertrophy",
            "Back",
            "Intermediate",
            "lat-prayer",
            [
                "Set a high cable with a rope or straight bar.",
                "Hinge slightly and pull elbows down toward pockets.",
                "Return slowly into a full lat stretch.",
            ],
            ["Elbows down", "Lat stretch", "Slow return"],
            ["Turning it into a row", "Using momentum", "Cutting stretch short"],
        ),
    ]


def ensure_exercise_library_columns() -> None:
    inspector = inspect(engine)
    if "exercise_library" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("exercise_library")}
    missing = [
        (column_name, column_definition)
        for column_name, column_definition in EXERCISE_LIBRARY_EXTRA_COLUMNS.items()
        if column_name not in existing_columns
    ]
    if not missing:
        return
    with engine.begin() as connection:
        for column_name, column_definition in missing:
            connection.execute(text(f"ALTER TABLE exercise_library ADD COLUMN {column_name} {column_definition}"))


def ensure_workout_set_columns() -> None:
    inspector = inspect(engine)
    if "workout_sets" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("workout_sets")}
    missing = [
        (column_name, column_definition)
        for column_name, column_definition in WORKOUT_SETS_EXTRA_COLUMNS.items()
        if column_name not in existing_columns
    ]
    if not missing:
        return
    with engine.begin() as connection:
        for column_name, column_definition in missing:
            connection.execute(text(f"ALTER TABLE workout_sets ADD COLUMN {column_name} {column_definition}"))


def ensure_chat_message_columns() -> None:
    inspector = inspect(engine)
    if "chat_messages" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("chat_messages")}
    missing = [
        (column_name, column_definition)
        for column_name, column_definition in CHAT_MESSAGES_EXTRA_COLUMNS.items()
        if column_name not in existing_columns
    ]
    if not missing:
        return
    with engine.begin() as connection:
        for column_name, column_definition in missing:
            connection.execute(text(f"ALTER TABLE chat_messages ADD COLUMN {column_name} {column_definition}"))


def ensure_user_preference_columns() -> None:
    inspector = inspect(engine)
    if "user_preferences" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("user_preferences")}
    missing: list[tuple[str, str]] = []
    if "preferred_gym_id" not in existing_columns:
        missing.append(("preferred_gym_id", "VARCHAR(80) NOT NULL DEFAULT 'gym_008'"))
    if "preferred_rep_mode" not in existing_columns:
        missing.append(("preferred_rep_mode", "VARCHAR(40) NOT NULL DEFAULT 'auto'"))
    if "preferred_rep_min" not in existing_columns:
        missing.append(("preferred_rep_min", "INTEGER NOT NULL DEFAULT 8"))
    if "preferred_rep_max" not in existing_columns:
        missing.append(("preferred_rep_max", "INTEGER NOT NULL DEFAULT 10"))
    if not missing:
        return
    with engine.begin() as connection:
        for column_name, column_definition in missing:
            connection.execute(text(f"ALTER TABLE user_preferences ADD COLUMN {column_name} {column_definition}"))


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def init_database() -> None:
    # Seed a reproducible demo baseline; local use can add more rows later.
    Base.metadata.create_all(bind=engine)
    ensure_exercise_library_columns()
    ensure_workout_set_columns()
    ensure_chat_message_columns()
    ensure_user_preference_columns()
    with SessionLocal() as session:
        if session.get(UserAccountORM, "demo") is None:
            session.add(
                UserAccountORM(
                    user_id="demo",
                    email="member@gymflow.ai",
                    display_name="Demo Member",
                    role="member",
                    password_demo="demo",
                )
            )
        if session.get(UserAccountORM, "manager") is None:
            session.add(
                UserAccountORM(
                    user_id="manager",
                    email="manager@gymflow.ai",
                    display_name="Network Manager",
                    role="manager",
                    password_demo="manager",
                )
            )
        if session.get(ChatSessionORM, "demo-coach-chat") is None:
            now = "2026-05-25T12:00:00"
            session.add(
                ChatSessionORM(
                    id="demo-coach-chat",
                    user_id="demo",
                    title="Training chat",
                    pinned=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                ChatMessageORM(
                    session_id="demo-coach-chat",
                    user_id="demo",
                    role="assistant",
                    text="Ready.",
                    actions_json="[]",
                    created_at=now,
                )
            )

        preference = session.get(UserPreferenceORM, "demo")
        if preference is None:
            session.add(
                UserPreferenceORM(
                    user_id="demo",
                    preferred_min_hour=11,
                    preferred_max_hour=16,
                    max_crowd_people=45.0,
                    weekly_goal_sessions=4,
                    preferred_weekdays="0,2,4",
                    off_peak_bonus_enabled=1,
                    preferred_gym_id="gym_008",
                    preferred_rep_mode="auto",
                    preferred_rep_min=8,
                    preferred_rep_max=10,
                )
            )
        elif not preference.preferred_gym_id:
            preference.preferred_gym_id = "gym_008"
        else:
            if not preference.preferred_rep_mode:
                preference.preferred_rep_mode = "auto"
            if not preference.preferred_rep_min:
                preference.preferred_rep_min = 8
            if not preference.preferred_rep_max:
                preference.preferred_rep_max = 10

        visit_count = session.scalar(select(func.count()).select_from(VisitORM).where(VisitORM.user_id == "demo"))
        if not visit_count:
            session.add_all(
                [
                    VisitORM(
                        user_id="demo",
                        gym_id="gym_008",
                        checked_in_at="2026-05-20T18:02:00",
                        source="qr_demo",
                        active_people_at_checkin=78,
                        note="Evening strength session",
                    ),
                    VisitORM(
                        user_id="demo",
                        gym_id="gym_008",
                        checked_in_at="2026-05-21T17:32:00",
                        source="qr_demo",
                        active_people_at_checkin=64,
                        note="Lower body day",
                    ),
                    VisitORM(
                        user_id="demo",
                        gym_id="gym_003",
                        checked_in_at="2026-05-22T13:08:00",
                        source="qr_demo",
                        active_people_at_checkin=31,
                        note="Off-peak pull session",
                    ),
                ]
            )

        template_count = session.scalar(
            select(func.count()).select_from(WorkoutTemplateORM).where(WorkoutTemplateORM.user_id == "demo")
        )
        if not template_count:
            session.add_all(
                [
                    WorkoutTemplateORM(
                        user_id="demo",
                        name="Upper Strength",
                        focus="Strength",
                        exercises_json=json.dumps(
                            [
                                {"exercise": "Barbell Bench Press", "sets": 3, "reps": 8, "target_weight_kg": 105, "rest_seconds": 150},
                                {"exercise": "Lat Pulldown", "sets": 3, "reps": 10, "target_weight_kg": 75, "rest_seconds": 90},
                                {"exercise": "Incline Dumbbell Press", "sets": 3, "reps": 10, "target_weight_kg": 32, "rest_seconds": 90},
                            ]
                        ),
                        estimated_minutes=58,
                        created_at="2026-05-20T12:00:00",
                    ),
                    WorkoutTemplateORM(
                        user_id="demo",
                        name="Lower Progression",
                        focus="Hypertrophy",
                        exercises_json=json.dumps(
                            [
                                {"exercise": "Back Squat", "sets": 4, "reps": 7, "target_weight_kg": 125, "rest_seconds": 180},
                                {"exercise": "Romanian Deadlift", "sets": 3, "reps": 8, "target_weight_kg": 100, "rest_seconds": 150},
                                {"exercise": "Leg Press", "sets": 3, "reps": 12, "target_weight_kg": 180, "rest_seconds": 120},
                            ]
                        ),
                        estimated_minutes=65,
                        created_at="2026-05-21T12:00:00",
                    ),
                ]
            )

        achievement_count = session.scalar(
            select(func.count()).select_from(AchievementORM).where(AchievementORM.user_id == "demo")
        )
        if not achievement_count:
            session.add_all(
                [
                    AchievementORM(
                        user_id="demo",
                        code="consistency_builder",
                        title="Consistency Builder",
                        description="Complete 4 training sessions in a rolling week.",
                        progress=3,
                        target=4,
                        unlocked_at="",
                    ),
                    AchievementORM(
                        user_id="demo",
                        code="off_peak_hero",
                        title="Off-Peak Hero",
                        description="Train during low-traffic windows 5 times.",
                        progress=2,
                        target=5,
                        unlocked_at="",
                    ),
                    AchievementORM(
                        user_id="demo",
                        code="strength_master",
                        title="Strength Master",
                        description="Reach 10 quality working sets for core lifts.",
                        progress=8,
                        target=10,
                        unlocked_at="",
                    ),
                ]
            )

        promotion_count = session.scalar(select(func.count()).select_from(PromotionORM))
        if not promotion_count:
            session.add_all(
                [
                    PromotionORM(
                        gym_id="gym_008",
                        title="Lunch Lift Bonus",
                        starts_at="2026-05-27T12:00:00",
                        discount_percent=15,
                        expected_people=28,
                        status="scheduled",
                        notification_copy="Lunch window is quiet today. Book 12:00-13:00 and get a 15% off-peak bonus.",
                    ),
                    PromotionORM(
                        gym_id="gym_003",
                        title="Calm Morning Pass",
                        starts_at="2026-05-28T10:00:00",
                        discount_percent=10,
                        expected_people=24,
                        status="draft",
                        notification_copy="Your preferred gym is calm this morning. Train before the rush and collect bonus points.",
                    ),
                ]
            )

        for item in exercise_seed_records():
            row = session.get(ExerciseORM, str(item["slug"]))
            if row is None:
                session.add(
                    ExerciseORM(
                        slug=str(item["slug"]),
                        name=str(item["name"]),
                        category=str(item["category"]),
                        muscle_group=str(item["muscle_group"]),
                        difficulty=str(item["difficulty"]),
                        image_hint=str(item["image_hint"]),
                        video_url=str(item["video_url"]),
                        media_type=str(item["media_type"]),
                        media_url=str(item["media_url"]),
                        youtube_video_id=str(item["youtube_video_id"]),
                        source_name=str(item["source_name"]),
                        source_url=str(item["source_url"]),
                        source_license=str(item["source_license"]),
                        attribution=str(item["attribution"]),
                        checked_at=str(item["checked_at"]),
                        primary_muscles_json=json.dumps(item["primary_muscles"]),
                        secondary_muscles_json=json.dumps(item["secondary_muscles"]),
                        instructions_json=json.dumps(item["instructions"]),
                        cues_json=json.dumps(item["cues"]),
                        mistakes_json=json.dumps(item["mistakes"]),
                    )
                )
                continue
            row.video_url = str(item["video_url"])
            row.media_type = str(item["media_type"])
            row.media_url = str(item["media_url"])
            row.youtube_video_id = str(item["youtube_video_id"])
            row.source_name = str(item["source_name"])
            row.source_url = str(item["source_url"])
            row.source_license = str(item["source_license"])
            row.attribution = str(item["attribution"])
            row.checked_at = str(item["checked_at"])
            row.primary_muscles_json = json.dumps(item["primary_muscles"])
            row.secondary_muscles_json = json.dumps(item["secondary_muscles"])

        for item in exercise_media_seed_records():
            existing_media = session.scalars(
                select(ExerciseMediaORM)
                .where(ExerciseMediaORM.exercise_slug == str(item["exercise_slug"]))
                .where(ExerciseMediaORM.media_url == str(item["media_url"]))
                .where(ExerciseMediaORM.media_type == str(item["media_type"]))
            ).first()
            if existing_media is None:
                session.add(
                    ExerciseMediaORM(
                        exercise_slug=str(item["exercise_slug"]),
                        media_type=str(item["media_type"]),
                        media_url=str(item["media_url"]),
                        thumbnail_url=str(item["thumbnail_url"]),
                        title=str(item["title"]),
                        source_name=str(item["source_name"]),
                        source_url=str(item["source_url"]),
                        source_license=str(item["source_license"]),
                        attribution=str(item["attribution"]),
                        checked_at=str(item["checked_at"]),
                        embed_allowed=int(item["embed_allowed"]),
                        download_allowed=int(item["download_allowed"]),
                        requires_attribution=int(item["requires_attribution"]),
                        sort_order=int(item["sort_order"]),
                        license_notes=str(item["license_notes"]),
                    )
                )
                continue
            existing_media.thumbnail_url = str(item["thumbnail_url"])
            existing_media.title = str(item["title"])
            existing_media.source_name = str(item["source_name"])
            existing_media.source_url = str(item["source_url"])
            existing_media.source_license = str(item["source_license"])
            existing_media.attribution = str(item["attribution"])
            existing_media.checked_at = str(item["checked_at"])
            existing_media.embed_allowed = int(item["embed_allowed"])
            existing_media.download_allowed = int(item["download_allowed"])
            existing_media.requires_attribution = int(item["requires_attribution"])
            existing_media.sort_order = int(item["sort_order"])
            existing_media.license_notes = str(item["license_notes"])

        scheduled_count = session.scalar(
            select(func.count()).select_from(ScheduledWorkoutORM).where(ScheduledWorkoutORM.user_id == "demo")
        )
        if not scheduled_count:
            session.add_all(
                [
                    ScheduledWorkoutORM(
                        user_id="demo",
                        gym_id="gym_008",
                        template_id=1,
                        title="Upper Strength",
                        scheduled_at="2026-05-27T12:00:00",
                        expected_people=28,
                        status="planned",
                        notes="Forecast-aware lunch training slot.",
                    ),
                    ScheduledWorkoutORM(
                        user_id="demo",
                        gym_id="gym_003",
                        template_id=2,
                        title="Lower Progression",
                        scheduled_at="2026-05-29T11:00:00",
                        expected_people=34,
                        status="planned",
                        notes="Keep volume moderate and avoid evening peak.",
                    ),
                ]
            )

        existing = session.scalar(
            select(func.count()).select_from(WorkoutSetORM).where(WorkoutSetORM.user_id == "demo")
        )
        if existing:
            session.commit()
            return

        session.add_all([WorkoutSetORM(**record) for record in build_demo_workout_history_records()])
        session.commit()
