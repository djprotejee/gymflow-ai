// Shared frontend contracts mirror the FastAPI response schemas used by the demo app.
export type View = "overview" | "planner" | "workouts" | "coach" | "profile" | "manager" | "research";

export type AuthUser = {
  user_id: string;
  email: string;
  display_name: string;
  role: "member" | "manager" | string;
};

export type Summary = {
  rows: number;
  gyms: number;
  min_timestamp: string;
  max_timestamp: string;
  avg_active_people: number;
};

export type Gym = {
  gym_id: string;
  city: string;
  address: string;
};

export type MetricRow = {
  model: string;
  scope: string;
  train_rows: number;
  test_rows: number;
  mae: number;
  rmse: number;
  wape: number;
};

export type ForecastPoint = {
  timestamp: string;
  actual: number;
  prediction: number;
};

export type FutureForecastPoint = {
  timestamp: string;
  prediction: number;
  prediction_interval_low: number;
  prediction_interval_high: number;
  model: string;
  is_weekend: number;
  is_public_holiday_ua: number;
};

export type SlotRecommendation = {
  timestamp: string;
  window_label?: string;
  expected_people: number;
  score: number;
  reason: string;
};

export type ProgressSummary = {
  total_sets: number;
  tracked_exercises: number;
  exercises: Array<{
    exercise: string;
    sets: number;
    best_weight_kg: number;
    total_volume_kg: number;
  }>;
};

export type NextSession = {
  exercise: string;
  target_weight_kg: number;
  target_reps: number;
  target_reps_min?: number;
  target_reps_max?: number;
  confidence?: number;
  model_version?: string;
  strategy?: string;
  target_kind?: "working" | "warmup" | "top";
  reason: string;
};

export type ChatResponse = {
  answer: string;
  sources: string[];
  safety_level: string;
  actions?: ChatToolAction[];
  citations?: ChatCitation[];
};

export type ChatToolAction = {
  type: string;
  label: string;
  description: string;
  payload: Record<string, unknown>;
};

export type ChatCitation = {
  chunk_id: string;
  title: string;
  source_type: string;
  score: number;
  matched_terms: string[];
  source_url: string;
  license: string;
  preview: string;
};

export type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  actions?: ChatToolAction[];
  citations?: ChatCitation[];
};

export type ChatSession = {
  id: string;
  user_id?: string;
  title: string;
  pinned: boolean;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
};

export type ChatSessionRecord = {
  id: string;
  user_id: string;
  title: string;
  pinned: boolean;
  created_at: string;
  updated_at: string;
  messages: Array<{
    id: number;
    role: "user" | "assistant";
    text: string;
    actions?: ChatToolAction[];
    citations?: ChatCitation[];
    created_at: string;
  }>;
};

export type ChatToolActionTrace = {
  id: number;
  session_id: string;
  user_id: string;
  action_type: string;
  label: string;
  payload: Record<string, unknown>;
  status: string;
  created_at: string;
  executed_at: string;
  result: Record<string, unknown>;
};

export type ActiveWorkout = {
  mode: "template" | "custom";
  title: string;
  templateId?: number;
  exercises: WorkoutTemplateExercise[];
  startedAt: string;
};

export type UserPreference = {
  user_id: string;
  preferred_min_hour: number;
  preferred_max_hour: number;
  max_crowd_people: number;
  weekly_goal_sessions: number;
  preferred_weekdays: number[];
  off_peak_bonus_enabled: boolean;
  preferred_gym_id: string;
  preferred_rep_mode: "auto" | "custom" | "pr";
  preferred_rep_min: number;
  preferred_rep_max: number;
};

export type GamificationSummary = {
  weekly_goal_sessions: number;
  weekly_sessions: number;
  current_streak_days: number;
  consistency_score: number;
  off_peak_bonus_points: number;
  level: string;
  next_action: string;
};

export type Visit = {
  id: number;
  gym_id: string;
  checked_in_at: string;
  source: string;
  active_people_at_checkin: number;
  note: string;
};

export type WorkoutSetModifierState = {
  myo_reps: boolean;
  myo_reps_matching: boolean;
  unilateral: boolean;
  drop_set: boolean;
  lengthened_partials: boolean;
};

export type ActiveWorkoutSetRow = {
  id: string;
  set_number: number;
  weight_kg: number;
  reps: number;
  left_reps?: number;
  right_reps?: number;
  target_weight_kg?: number;
  target_reps?: number;
  target_reps_min?: number;
  target_reps_max?: number;
  target_kind?: "working" | "warmup" | "top";
  prediction_reason?: string;
  rest_before_seconds?: number;
  completed_at?: string;
  completed?: boolean;
  modifiers?: WorkoutSetModifierState;
};

export type WorkoutTemplateExercise = {
  exercise: string;
  sets: number;
  reps: number;
  target_weight_kg: number;
  rest_seconds: number;
  unilateral?: boolean;
  left_reps?: number;
  right_reps?: number;
  expanded?: boolean;
  set_modifiers?: WorkoutSetModifierState;
  set_rows?: ActiveWorkoutSetRow[];
};

export type WorkoutTemplate = {
  id: number;
  user_id: string;
  name: string;
  focus: string;
  exercises: WorkoutTemplateExercise[];
  estimated_minutes: number;
  created_at: string;
};

export type Achievement = {
  id: number;
  code: string;
  title: string;
  description: string;
  progress: number;
  target: number;
  unlocked_at: string;
};

export type TrainingPlan = {
  user_id: string;
  gym_id: string;
  weekly_goal_sessions: number;
  strategy: string;
  sessions: Array<{
    day_index: number;
    scheduled_at: string;
    window_label?: string;
    expected_people: number;
    focus: string;
    estimated_minutes: number;
    reason: string;
  }>;
};

export type ActivityDashboard = {
  visits: number;
  logged_sets: number;
  templates: number;
  achievements_unlocked: number;
  off_peak_visit_share: number;
  recent_visits: Visit[];
  recent_workouts: WorkoutSet[];
};

export type WorkoutSet = {
  id: number;
  user_id: string;
  exercise: string;
  weight_kg: number;
  reps: number;
  set_index: number;
  performed_at: string;
  notes: string;
  modifiers?: {
    myo_reps: boolean;
    myo_reps_matching: boolean;
    unilateral: boolean;
    drop_set: boolean;
    lengthened_partials: boolean;
  };
};

export type Promotion = {
  id: number;
  gym_id: string;
  title: string;
  starts_at: string;
  discount_percent: number;
  expected_people: number;
  status: string;
  notification_copy: string;
};

export type RecommendationEvent = {
  id: number;
  user_id: string;
  recommendation_type: string;
  context_key: string;
  title: string;
  detail: string;
  status: "suggested" | "accepted" | "dismissed" | "applied" | string;
  score: number;
  expected_people: number;
  created_at: string;
  acted_at: string;
  metadata_json: string;
};

export type ManagerNotification = {
  promotion_id: number;
  gym_id: string;
  send_at: string;
  channel: string;
  status: string;
  copy: string;
};

export type ExerciseMedia = {
  id: number;
  exercise_slug: string;
  media_type: string;
  media_url: string;
  thumbnail_url: string;
  title: string;
  source_name: string;
  source_url: string;
  source_license: string;
  attribution: string;
  checked_at: string;
  embed_allowed: boolean;
  download_allowed: boolean;
  requires_attribution: boolean;
  sort_order: number;
  license_notes: string;
};

export type AnatomyRegion = {
  id: string;
  label: string;
};

export type AnatomyRegionGroup = {
  group: string;
  regions: AnatomyRegion[];
};

export type Exercise = {
  slug: string;
  name: string;
  category: string;
  muscle_group: string;
  difficulty: string;
  image_hint: string;
  video_url: string;
  media_type: string;
  media_url: string;
  youtube_video_id: string;
  source_name: string;
  source_url: string;
  source_license: string;
  attribution: string;
  checked_at: string;
  primary_muscles: string[];
  secondary_muscles: string[];
  instructions: string[];
  cues: string[];
  mistakes: string[];
  media_gallery: ExerciseMedia[];
};

export type ExerciseImportPreviewRecord = {
  slug: string;
  name: string;
  category: string;
  muscle_group: string;
  difficulty: string;
  equipment: string;
  source_name: string;
  source_license: string;
  source_url: string;
  checked_at: string;
  anatomy_note: string;
  primary_muscles: string[];
  secondary_muscles: string[];
  media_gallery_count: number;
  has_media: boolean;
  has_embed_ready_media: boolean;
  requires_anatomy_review: boolean;
};

export type ExerciseImportPreview = {
  path: string;
  status: string;
  source_name: string;
  source_license: string;
  note: string;
  records_total: number;
  records_with_media: number;
  records_with_embed_ready_media: number;
  records_needing_anatomy_review: number;
  records: ExerciseImportPreviewRecord[];
};

export type ScheduledWorkout = {
  id: number;
  user_id: string;
  gym_id: string;
  template_id: number;
  title: string;
  scheduled_at: string;
  expected_people: number;
  status: string;
  notes: string;
};

export type ManagerOverview = {
  gyms: number;
  latest_total_people: number;
  avg_latest_people: number;
  future_avg_prediction: number;
  low_traffic_slots: number;
  forecast_points: number;
  best_model: MetricRow | null;
  peak_location: {
    gym_id: string;
    city: string;
    address: string;
    active_people: number;
    timestamp: string;
  } | null;
};

export type ManagerLocation = {
  gym_id: string;
  city: string;
  address: string;
  latest_people: number;
  avg_people: number;
  peak_people: number;
  future_avg_prediction: number;
  future_peak_prediction: number;
  campaign_candidate_slots: number;
};

export type CampaignSuggestion = {
  gym_id: string;
  city: string;
  address: string;
  timestamp: string;
  expected_people: number;
  score: number;
  campaign_type: string;
  reason: string;
};

export type DashboardData = {
  summary: Summary | null;
  gyms: Gym[];
  metrics: MetricRow[];
  forecast: ForecastPoint[];
  futureForecast: FutureForecastPoint[];
  slots: SlotRecommendation[];
  futureSlots: SlotRecommendation[];
  progress: ProgressSummary | null;
  nextSession: NextSession | null;
  coachAnswer: ChatResponse | null;
  preferences: UserPreference | null;
  gamification: GamificationSummary | null;
  visits: Visit[];
  templates: WorkoutTemplate[];
  achievements: Achievement[];
  trainingPlan: TrainingPlan | null;
  activityDashboard: ActivityDashboard | null;
  exercises: Exercise[];
  scheduledWorkouts: ScheduledWorkout[];
  managerOverview: ManagerOverview | null;
  managerLocations: ManagerLocation[];
  campaigns: CampaignSuggestion[];
  promotions: Promotion[];
  notifications: ManagerNotification[];
};

export type DashboardPatch = Partial<Pick<DashboardData, "progress" | "nextSession" | "preferences" | "gamification" | "futureSlots" | "templates" | "visits" | "achievements" | "activityDashboard" | "trainingPlan" | "exercises" | "scheduledWorkouts" | "promotions" | "notifications">>;
