from __future__ import annotations

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class WorkoutSetORM(Base):
    __tablename__ = "workout_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    exercise: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    set_index: Mapped[int] = mapped_column(Integer, nullable=False)
    performed_at: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    notes: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # JSON payload for advanced set annotations (myo-reps, unilateral, drop sets, etc.).
    modifiers_json: Mapped[str] = mapped_column(String(1200), nullable=False, default="{}")


class UserPreferenceORM(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    preferred_min_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=11)
    preferred_max_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=16)
    max_crowd_people: Mapped[float] = mapped_column(Float, nullable=False, default=45.0)
    weekly_goal_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    preferred_weekdays: Mapped[str] = mapped_column(String(40), nullable=False, default="0,2,4")
    off_peak_bonus_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    preferred_gym_id: Mapped[str] = mapped_column(String(80), nullable=False, default="gym_008")
    preferred_rep_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="auto")
    preferred_rep_min: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    preferred_rep_max: Mapped[int] = mapped_column(Integer, nullable=False, default=10)


class UserAccountORM(Base):
    __tablename__ = "user_accounts"

    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="member")
    password_demo: Mapped[str] = mapped_column(String(120), nullable=False)


class UserSessionORM(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    expires_at: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    revoked_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")


class VisitORM(Base):
    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    gym_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    checked_in_at: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="qr_demo")
    active_people_at_checkin: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    note: Mapped[str] = mapped_column(String(300), nullable=False, default="")


class WorkoutTemplateORM(Base):
    __tablename__ = "workout_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    focus: Mapped[str] = mapped_column(String(80), nullable=False)
    exercises_json: Mapped[str] = mapped_column(String(4000), nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    created_at: Mapped[str] = mapped_column(String(40), index=True, nullable=False)


class AchievementORM(Base):
    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    target: Mapped[float] = mapped_column(Float, nullable=False, default=100)
    unlocked_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")


class PromotionORM(Base):
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gym_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    starts_at: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    discount_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    expected_people: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    notification_copy: Mapped[str] = mapped_column(String(400), nullable=False, default="")


class RecommendationEventORM(Base):
    __tablename__ = "recommendation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    recommendation_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    context_key: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    detail: Mapped[str] = mapped_column(String(600), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False, default="suggested")
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    expected_people: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    acted_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    metadata_json: Mapped[str] = mapped_column(String(1600), nullable=False, default="{}")


class ChatSessionORM(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    pinned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), index=True, nullable=False)


class ChatMessageORM(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(String(4000), nullable=False)
    actions_json: Mapped[str] = mapped_column(String(4000), nullable=False, default="[]")
    citations_json: Mapped[str] = mapped_column(String(4000), nullable=False, default="[]")
    created_at: Mapped[str] = mapped_column(String(40), index=True, nullable=False)


class ChatToolActionORM(Base):
    __tablename__ = "chat_tool_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    action_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_json: Mapped[str] = mapped_column(String(2000), nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False, default="suggested")
    created_at: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    executed_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    result_json: Mapped[str] = mapped_column(String(2000), nullable=False, default="{}")


class ExerciseORM(Base):
    __tablename__ = "exercise_library"

    slug: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    muscle_group: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(40), nullable=False)
    image_hint: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    video_url: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    media_type: Mapped[str] = mapped_column(String(40), nullable=False, default="link")
    media_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    youtube_video_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    source_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    source_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    source_license: Mapped[str] = mapped_column(String(180), nullable=False, default="")
    attribution: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    checked_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    primary_muscles_json: Mapped[str] = mapped_column(String(2000), nullable=False, default="[]")
    secondary_muscles_json: Mapped[str] = mapped_column(String(2000), nullable=False, default="[]")
    instructions_json: Mapped[str] = mapped_column(String(2000), nullable=False)
    cues_json: Mapped[str] = mapped_column(String(1200), nullable=False)
    mistakes_json: Mapped[str] = mapped_column(String(1200), nullable=False)


class ExerciseMediaORM(Base):
    __tablename__ = "exercise_media_gallery"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exercise_slug: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    media_type: Mapped[str] = mapped_column(String(40), nullable=False, default="link")
    media_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    thumbnail_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    source_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    source_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    source_license: Mapped[str] = mapped_column(String(180), nullable=False, default="")
    attribution: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    checked_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    embed_allowed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    download_allowed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requires_attribution: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    license_notes: Mapped[str] = mapped_column(String(500), nullable=False, default="")


class ScheduledWorkoutORM(Base):
    __tablename__ = "scheduled_workouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    gym_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    template_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    scheduled_at: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    expected_people: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="planned")
    notes: Mapped[str] = mapped_column(String(500), nullable=False, default="")
