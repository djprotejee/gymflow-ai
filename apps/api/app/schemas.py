from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkoutSetModifiers(BaseModel):
    myo_reps: bool = False
    myo_reps_matching: bool = False
    unilateral: bool = False
    drop_set: bool = False
    lengthened_partials: bool = False


class WorkoutSetCreate(BaseModel):
    exercise: str = Field(min_length=2, max_length=120)
    weight_kg: float = Field(ge=0)
    reps: int = Field(ge=1, le=100)
    set_index: int = Field(ge=1, le=20)
    performed_at: str | None = None
    notes: str = ""
    modifiers: WorkoutSetModifiers = Field(default_factory=WorkoutSetModifiers)


class WorkoutSet(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    exercise: str
    weight_kg: float
    reps: int
    set_index: int
    performed_at: str
    notes: str
    modifiers: WorkoutSetModifiers = Field(default_factory=WorkoutSetModifiers)


class WorkoutTemplateExercise(BaseModel):
    exercise: str = Field(min_length=2, max_length=120)
    sets: int = Field(ge=1, le=10)
    reps: int = Field(ge=1, le=100)
    target_weight_kg: float = Field(ge=0)
    rest_seconds: int = Field(default=90, ge=15, le=600)


class WorkoutTemplateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    focus: str = Field(min_length=2, max_length=80)
    exercises: list[WorkoutTemplateExercise] = Field(min_length=1, max_length=20)
    estimated_minutes: int = Field(default=60, ge=10, le=240)


class WorkoutTemplate(WorkoutTemplateCreate):
    id: int
    user_id: str
    created_at: str


class VisitCreate(BaseModel):
    gym_id: str = Field(min_length=2, max_length=80)
    checked_in_at: str | None = None
    active_people_at_checkin: float = Field(default=0, ge=0)
    note: str = Field(default="", max_length=300)


class Visit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    gym_id: str
    checked_in_at: str
    source: str
    active_people_at_checkin: float
    note: str


class Achievement(BaseModel):
    id: int
    code: str
    title: str
    description: str
    progress: float
    target: float
    unlocked_at: str


class PromotionCreate(BaseModel):
    gym_id: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=160)
    starts_at: str
    discount_percent: int = Field(default=10, ge=1, le=90)
    expected_people: float = Field(default=0, ge=0)
    notification_copy: str = Field(default="", max_length=400)


class Promotion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    gym_id: str
    title: str
    starts_at: str
    discount_percent: int
    expected_people: float
    status: str
    notification_copy: str


class RecommendationEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    recommendation_type: str
    context_key: str
    title: str
    detail: str
    status: str
    score: float
    expected_people: float
    created_at: str
    acted_at: str
    metadata_json: str


class RecommendationEventUpdate(BaseModel):
    status: str = Field(pattern="^(suggested|accepted|dismissed|applied)$")


class ExerciseMedia(BaseModel):
    id: int
    exercise_slug: str
    media_type: str
    media_url: str
    thumbnail_url: str
    title: str
    source_name: str
    source_url: str
    source_license: str
    attribution: str
    checked_at: str
    embed_allowed: bool
    download_allowed: bool
    requires_attribution: bool
    sort_order: int
    license_notes: str


class ExerciseMediaCreate(BaseModel):
    media_type: str = Field(min_length=2, max_length=40)
    media_url: str = Field(default="", max_length=500)
    thumbnail_url: str = Field(default="", max_length=500)
    title: str = Field(default="", max_length=160)
    source_name: str = Field(min_length=2, max_length=160)
    source_url: str = Field(default="", max_length=500)
    source_license: str = Field(default="", max_length=180)
    attribution: str = Field(default="", max_length=500)
    checked_at: str = Field(default="", max_length=40)
    embed_allowed: bool = True
    download_allowed: bool = False
    requires_attribution: bool = True
    sort_order: int = Field(default=0, ge=0, le=999)
    license_notes: str = Field(default="", max_length=500)


class Exercise(BaseModel):
    slug: str
    name: str
    category: str
    muscle_group: str
    difficulty: str
    image_hint: str
    video_url: str
    media_type: str
    media_url: str
    youtube_video_id: str
    source_name: str
    source_url: str
    source_license: str
    attribution: str
    checked_at: str
    primary_muscles: list[str]
    secondary_muscles: list[str]
    instructions: list[str]
    cues: list[str]
    mistakes: list[str]
    media_gallery: list[ExerciseMedia] = Field(default_factory=list)


class CustomExerciseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(default="Custom", min_length=2, max_length=80)
    muscle_group: str = Field(min_length=2, max_length=80)
    difficulty: str = Field(default="Custom", min_length=2, max_length=40)
    primary_muscles: list[str] = Field(default_factory=list, max_length=24)
    secondary_muscles: list[str] = Field(default_factory=list, max_length=24)
    allow_empty_primary: bool = False


class CustomExerciseUpdate(BaseModel):
    category: str = Field(default="Custom", min_length=2, max_length=80)
    muscle_group: str = Field(min_length=2, max_length=80)
    difficulty: str = Field(default="Custom", min_length=2, max_length=40)
    primary_muscles: list[str] = Field(default_factory=list, max_length=24)
    secondary_muscles: list[str] = Field(default_factory=list, max_length=24)
    allow_empty_primary: bool = False
    instructions: list[str] = Field(default_factory=list, max_length=12)
    cues: list[str] = Field(default_factory=list, max_length=12)
    mistakes: list[str] = Field(default_factory=list, max_length=12)


class ExercisePreviewImportRequest(BaseModel):
    path: str | None = None
    limit: int = Field(default=0, ge=0, le=1000)
    only_with_media: bool = True
    only_embed_ready_media: bool = True


class ScheduledWorkoutCreate(BaseModel):
    gym_id: str = Field(min_length=2, max_length=80)
    template_id: int = Field(default=0, ge=0)
    title: str = Field(min_length=2, max_length=160)
    scheduled_at: str
    expected_people: float = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=500)


class ScheduledWorkoutUpdate(BaseModel):
    status: str = Field(default="planned", max_length=40)
    title: str | None = Field(default=None, min_length=2, max_length=160)
    scheduled_at: str | None = None
    expected_people: float | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=500)


class ScheduledWorkout(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    gym_id: str
    template_id: int
    title: str
    scheduled_at: str
    expected_people: float
    status: str
    notes: str


class UserPreferenceUpdate(BaseModel):
    preferred_min_hour: int = Field(default=11, ge=0, le=23)
    preferred_max_hour: int = Field(default=16, ge=1, le=24)
    max_crowd_people: float = Field(default=45, ge=0, le=300)
    weekly_goal_sessions: int = Field(default=4, ge=1, le=14)
    preferred_weekdays: list[int] = Field(default_factory=lambda: [0, 2, 4])
    off_peak_bonus_enabled: bool = True
    preferred_gym_id: str = Field(default="gym_008", min_length=2, max_length=80)
    preferred_rep_mode: str = Field(default="auto", pattern="^(auto|custom|pr)$")
    preferred_rep_min: int = Field(default=8, ge=1, le=30)
    preferred_rep_max: int = Field(default=10, ge=1, le=30)


class UserPreference(BaseModel):
    user_id: str
    preferred_min_hour: int
    preferred_max_hour: int
    max_crowd_people: float
    weekly_goal_sessions: int
    preferred_weekdays: list[int]
    off_peak_bonus_enabled: bool
    preferred_gym_id: str
    preferred_rep_mode: str
    preferred_rep_min: int
    preferred_rep_max: int


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=3, max_length=120)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=8, max_length=120)
    display_name: str = Field(min_length=2, max_length=120)


class AuthUser(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: str


class LoginResponse(BaseModel):
    token: str
    user: AuthUser


class ChatRequest(BaseModel):
    user_id: str = "demo"
    gym_id: str | None = None
    message: str = Field(min_length=1, max_length=1000)


class ChatToolAction(BaseModel):
    type: str = Field(min_length=2, max_length=80)
    label: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)


class ChatCitation(BaseModel):
    chunk_id: str = Field(min_length=2, max_length=180)
    title: str = Field(min_length=1, max_length=180)
    source_type: str = Field(min_length=2, max_length=80)
    score: float = 0
    matched_terms: list[str] = Field(default_factory=list)
    source_url: str = ""
    license: str = ""
    preview: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    safety_level: str
    actions: list[ChatToolAction] = Field(default_factory=list)
    citations: list[ChatCitation] = Field(default_factory=list)


class ChatMessageRecord(BaseModel):
    id: int
    role: str
    text: str
    actions: list[ChatToolAction] = Field(default_factory=list)
    citations: list[ChatCitation] = Field(default_factory=list)
    created_at: str


class ChatSessionRecord(BaseModel):
    id: str
    user_id: str
    title: str
    pinned: bool = False
    created_at: str
    updated_at: str
    messages: list[ChatMessageRecord] = Field(default_factory=list)


class ChatSessionCreate(BaseModel):
    title: str = Field(default="Training chat", min_length=2, max_length=160)


class ChatSessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=160)
    pinned: bool | None = None


class ChatMessageCreate(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(min_length=1, max_length=4000)
    actions: list[ChatToolAction] = Field(default_factory=list)
    citations: list[ChatCitation] = Field(default_factory=list)


class ChatToolActionTrace(BaseModel):
    id: int
    session_id: str
    user_id: str
    action_type: str
    label: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: str
    executed_at: str
    result: dict[str, Any] = Field(default_factory=dict)


class ChatToolActionTraceCreate(BaseModel):
    session_id: str
    action: ChatToolAction
    status: str = Field(default="suggested", max_length=40)


class ChatToolActionTraceUpdate(BaseModel):
    status: str = Field(max_length=40)
    result: dict[str, Any] = Field(default_factory=dict)
