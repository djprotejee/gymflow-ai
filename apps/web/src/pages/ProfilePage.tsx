import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Award,
  BarChart3,
  BookOpen,
  Bot,
  Building2,
  CalendarClock,
  CalendarCheck,
  ChevronRight,
  CheckCircle2,
  Clock,
  Dumbbell,
  Flame,
  Medal,
  Megaphone,
  MoreHorizontal,
  Pin,
  Search,
  ShieldCheck,
  Sparkles,
  Star,
  Target,
  TrendingUp,
  Trophy,
  Trash2,
  Users,
} from "lucide-react";
import { ForecastChart, FutureForecastChart, ChartSkeleton, SkeletonRows } from "../components/ForecastCharts";
import { MessageText } from "../components/MessageText";
import { MuscleAnatomy } from "../components/MuscleAnatomy";
import { fallbackMetrics } from "../data/modelMetrics";
import { API_URL, getJson } from "../lib/api";
import { createChatSession, loadStoredChatSessions } from "../lib/chatSessions";
import { formatForecastSlot, formatSlot, formatTrainingWindow, prettyModelName, toDateTimeLocalValue } from "../lib/format";
import type {
  Achievement,
  ActiveWorkout,
  ActivityDashboard,
  AuthUser,
  ChatMessage,
  ChatResponse,
  ChatSession,
  DashboardData,
  DashboardPatch,
  Exercise,
  ForecastPoint,
  GamificationSummary,
  Gym,
  ManagerNotification,
  NextSession,
  ProgressSummary,
  Promotion,
  ScheduledWorkout,
  SlotRecommendation,
  UserPreference,
  WorkoutSet,
  WorkoutSetModifierState,
  WorkoutTemplate,
  WorkoutTemplateExercise,
} from "../types";

type CompletedWorkoutSnapshot = {
  id: string;
  title: string;
  mode: ActiveWorkout["mode"];
  startedAt: string;
  finishedAt: string;
  duration_seconds: number;
  exercises: WorkoutTemplateExercise[];
};

const COMPLETED_WORKOUTS_STORAGE_KEY = "gymflow-completed-workouts";

function completedSetRows(item: WorkoutTemplateExercise) {
  return (item.set_rows ?? []).filter((row) => row.completed);
}

function completedWorkoutSetCount(workout: CompletedWorkoutSnapshot) {
  return workout.exercises.reduce((sum, item) => sum + completedSetRows(item).length, 0);
}

function completedWorkoutVolume(workout: CompletedWorkoutSnapshot) {
  return workout.exercises.reduce((sum, item) => (
    sum + completedSetRows(item).reduce((rowSum, row) => rowSum + (row.weight_kg || 0) * (row.reps || 0), 0)
  ), 0);
}

function formatDuration(totalSeconds: number) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function modifierBadges(row: { modifiers?: WorkoutSetModifierState }) {
  const modifiers = row.modifiers;
  const tags: string[] = [];
  if (modifiers?.myo_reps) {
    tags.push(modifiers.myo_reps_matching ? "Myo match" : "Myo");
  }
  if (modifiers?.unilateral) {
    tags.push("Uni");
  }
  if (modifiers?.drop_set) {
    tags.push("Drop");
  }
  if (modifiers?.lengthened_partials) {
    tags.push("Partials");
  }
  return tags;
}

function formatAchievementDate(value: string) {
  if (!value) {
    return "Locked";
  }
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function achievementIcon(code: string) {
  if (code.includes("consistency")) {
    return <Flame size={18} />;
  }
  if (code.includes("off_peak")) {
    return <Clock size={18} />;
  }
  if (code.includes("strength") || code.includes("bench")) {
    return <Dumbbell size={18} />;
  }
  if (code.includes("template")) {
    return <BookOpen size={18} />;
  }
  if (code.includes("volume")) {
    return <BarChart3 size={18} />;
  }
  if (code.includes("explorer")) {
    return <Star size={18} />;
  }
  if (code.includes("specialist")) {
    return <Award size={18} />;
  }
  if (code.includes("attendance")) {
    return <CalendarCheck size={18} />;
  }
  if (code.includes("secret")) {
    return <Sparkles size={18} />;
  }
  return <Medal size={18} />;
}

function niceChartMax(value: number) {
  if (value <= 0) {
    return 1;
  }
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalized = value / magnitude;
  const niceNormalized = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return niceNormalized * magnitude;
}

export function ProfilePage({
  data,
  userId,
  selectedGymId,
  horizonDays,
  setSelectedGymId,
  onDashboardPatch,
}: {
  data: DashboardData;
  userId: string;
  selectedGymId: string;
  horizonDays: number;
  setSelectedGymId: (value: string) => void;
  onDashboardPatch: (patch: DashboardPatch) => void;
}) {
  const [minHour, setMinHour] = useState(String(data.preferences?.preferred_min_hour ?? 11));
  const [maxHour, setMaxHour] = useState(String(data.preferences?.preferred_max_hour ?? 16));
  const [crowdLimit, setCrowdLimit] = useState(String(data.preferences?.max_crowd_people ?? 45));
  const [weeklyGoal, setWeeklyGoal] = useState(String(data.preferences?.weekly_goal_sessions ?? 4));
  const [preferredGymId, setPreferredGymId] = useState(data.preferences?.preferred_gym_id ?? selectedGymId);
  const [repMode, setRepMode] = useState<"auto" | "custom" | "pr">(data.preferences?.preferred_rep_mode ?? "auto");
  const [repMin, setRepMin] = useState(String(data.preferences?.preferred_rep_min ?? 8));
  const [repMax, setRepMax] = useState(String(data.preferences?.preferred_rep_max ?? 10));
  const [weekdays, setWeekdays] = useState<number[]>(data.preferences?.preferred_weekdays ?? [0, 2, 4]);
  const [offPeakBonus, setOffPeakBonus] = useState(data.preferences?.off_peak_bonus_enabled ?? true);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [profileInsightView, setProfileInsightView] = useState<"history" | "favorites" | "performance" | "muscles">("history");
  const [favoriteSort, setFavoriteSort] = useState<"sets" | "volume" | "best">("sets");
  const [favoritePeriod, setFavoritePeriod] = useState<"month" | "year" | "all">("all");
  const [historySort, setHistorySort] = useState<"recent" | "volume" | "sets">("recent");
  const [performanceMetric, setPerformanceMetric] = useState<"volume" | "sets" | "best" | "workouts">("volume");
  const [favoriteDetailMetric, setFavoriteDetailMetric] = useState<"pr" | "volume" | "sets">("pr");
  const [selectedFavoriteExerciseName, setSelectedFavoriteExerciseName] = useState<string | null>(null);
  const [showAchievementPantheon, setShowAchievementPantheon] = useState(false);
  const [completedWorkouts, setCompletedWorkouts] = useState<CompletedWorkoutSnapshot[]>([]);
  const [selectedCompletedWorkoutId, setSelectedCompletedWorkoutId] = useState<string | null>(null);

  useEffect(() => {
    if (!data.preferences) {
      return;
    }
    setMinHour(String(data.preferences.preferred_min_hour));
    setMaxHour(String(data.preferences.preferred_max_hour));
    setCrowdLimit(String(data.preferences.max_crowd_people));
    setWeeklyGoal(String(data.preferences.weekly_goal_sessions));
    setPreferredGymId(data.preferences.preferred_gym_id || selectedGymId);
    setRepMode(data.preferences.preferred_rep_mode ?? "auto");
    setRepMin(String(data.preferences.preferred_rep_min ?? 8));
    setRepMax(String(data.preferences.preferred_rep_max ?? 10));
    setWeekdays(data.preferences.preferred_weekdays);
    setOffPeakBonus(data.preferences.off_peak_bonus_enabled);
  }, [data.preferences, selectedGymId]);

  useEffect(() => {
    try {
      const storedWorkouts = window.localStorage.getItem(COMPLETED_WORKOUTS_STORAGE_KEY);
      setCompletedWorkouts(storedWorkouts ? JSON.parse(storedWorkouts) : []);
    } catch {
      setCompletedWorkouts([]);
    }
  }, []);

  function toggleWeekday(day: number) {
    setWeekdays((current) => (
      current.includes(day)
        ? current.filter((value) => value !== day)
        : [...current, day].sort((left, right) => left - right)
    ));
  }

  async function savePreferences() {
    setStatus("saving");
    try {
      const response = await fetch(`${API_URL}/users/${userId}/preferences`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preferred_min_hour: Number(minHour),
          preferred_max_hour: Number(maxHour),
          max_crowd_people: Number(crowdLimit),
          weekly_goal_sessions: Number(weeklyGoal),
          preferred_weekdays: weekdays,
          off_peak_bonus_enabled: offPeakBonus,
          preferred_gym_id: preferredGymId,
          preferred_rep_mode: repMode,
          preferred_rep_min: Number(repMin),
          preferred_rep_max: Number(repMax),
        }),
      });
      if (!response.ok) {
        throw new Error("Preference save failed");
      }
      const preferences = (await response.json()) as UserPreference;
      const [futureSlots, gamification] = await Promise.all([
        getJson<SlotRecommendation[]>(`/users/${userId}/recommendations/future-slots?gym_id=${preferredGymId}&days=${horizonDays}&max_results=3`),
        getJson<GamificationSummary>(`/users/${userId}/gamification`),
      ]);
      setSelectedGymId(preferredGymId);
      onDashboardPatch({ preferences, futureSlots, gamification });
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  const weeklySessions = data.gamification?.weekly_sessions ?? 0;
  const weeklyGoalValue = data.gamification?.weekly_goal_sessions ?? Number(weeklyGoal);
  const loggedSets = data.activityDashboard?.logged_sets ?? data.progress?.total_sets ?? 0;
  const visits = data.activityDashboard?.visits ?? data.visits.length;
  const templates = data.activityDashboard?.templates ?? data.templates.length;
  const offPeakShare = data.activityDashboard?.off_peak_visit_share ?? 0;
  const unlockedAchievementCount = data.achievements.filter((achievement) => achievement.progress >= achievement.target).length;
  const xp = Math.round(visits * 35 + loggedSets * 12 + templates * 45 + unlockedAchievementCount * 80 + (data.gamification?.off_peak_bonus_points ?? 0));
  const level = Math.max(1, Math.floor(xp / 250) + 1);
  const levelFloor = (level - 1) * 250;
  const levelProgress = Math.min(100, Math.round(((xp - levelFloor) / 250) * 100));
  const achievementCatalog = data.achievements;
  const weeklyPercent = Math.min(100, Math.round((weeklySessions / Math.max(1, weeklyGoalValue)) * 100));
  const progressExercises = [...(data.progress?.exercises ?? [])].sort((left, right) => right.total_volume_kg - left.total_volume_kg);
  const totalTrainingVolume = progressExercises.reduce((sum, item) => sum + item.total_volume_kg, 0);
  const periodLabels = { month: "1 Month", year: "1 Year", all: "All Time" };
  const bucketByMonth = favoritePeriod !== "month";
  const monthFormatter = new Intl.DateTimeFormat(undefined, { month: "short" });
  const dayFormatter = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
  const bucketKeyForDate = (isoDate: string) => (bucketByMonth ? isoDate.slice(0, 7) : isoDate.slice(0, 10));
  const bucketLabelForKey = (key: string) => {
    if (bucketByMonth) {
      return monthFormatter.format(new Date(`${key}-01T00:00:00`));
    }
    return dayFormatter.format(new Date(`${key}T00:00:00`));
  };
  const recentWorkoutRows = data.activityDashboard?.recent_workouts ?? [];
  const latestWorkoutTime = recentWorkoutRows.reduce((latest, row) => (
    !latest || row.performed_at > latest ? row.performed_at : latest
  ), "");
  const periodCutoff = favoritePeriod === "all" || !latestWorkoutTime
    ? null
    : new Date(new Date(latestWorkoutTime).getTime() - (favoritePeriod === "month" ? 31 : 365) * 24 * 60 * 60 * 1000);
  const periodWorkoutRows = recentWorkoutRows.filter((row) => !periodCutoff || new Date(row.performed_at) >= periodCutoff);
  const periodProgressMap = periodWorkoutRows.reduce((map, row) => {
    const current = map.get(row.exercise) ?? { exercise: row.exercise, sets: 0, total_volume_kg: 0, best_weight_kg: 0, last_performed_at: row.performed_at };
    current.sets += 1;
    current.total_volume_kg += row.weight_kg * row.reps;
    current.best_weight_kg = Math.max(current.best_weight_kg, row.weight_kg);
    current.last_performed_at = row.performed_at > current.last_performed_at ? row.performed_at : current.last_performed_at;
    map.set(row.exercise, current);
    return map;
  }, new Map<string, { exercise: string; sets: number; total_volume_kg: number; best_weight_kg: number; last_performed_at: string }>());
  const favoriteExerciseStats = (periodProgressMap.size > 0
    ? Array.from(periodProgressMap.values())
    : progressExercises.map((item) => ({ ...item, last_performed_at: "" }))
  );
  const topFavoriteExercises = [...favoriteExerciseStats].sort((left, right) => {
    if (favoriteSort === "volume") {
      return right.total_volume_kg - left.total_volume_kg;
    }
    if (favoriteSort === "best") {
      return right.best_weight_kg - left.best_weight_kg;
    }
    return right.sets - left.sets;
  }).slice(0, 8);
  const selectedFavoriteExercise = topFavoriteExercises.find((exercise) => exercise.exercise === selectedFavoriteExerciseName) ?? topFavoriteExercises[0] ?? null;
  const sortedCompletedWorkouts = [...completedWorkouts].sort((left, right) => {
    if (historySort === "volume") {
      return completedWorkoutVolume(right) - completedWorkoutVolume(left);
    }
    if (historySort === "sets") {
      return completedWorkoutSetCount(right) - completedWorkoutSetCount(left);
    }
    return right.startedAt.localeCompare(left.startedAt);
  });
  const backendWorkoutGroups = Array.from(recentWorkoutRows.reduce((map, row) => {
    const day = row.performed_at.slice(0, 10);
    const current = map.get(day) ?? { id: day, title: `${new Date(row.performed_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })} workout`, performedAt: row.performed_at, rows: [] as typeof recentWorkoutRows };
    current.rows.push(row);
    map.set(day, current);
    return map;
  }, new Map<string, { id: string; title: string; performedAt: string; rows: typeof recentWorkoutRows }>()).values()).sort((left, right) => {
    if (historySort === "volume") {
      const rightVolume = right.rows.reduce((sum, row) => sum + row.weight_kg * row.reps, 0);
      const leftVolume = left.rows.reduce((sum, row) => sum + row.weight_kg * row.reps, 0);
      return rightVolume - leftVolume;
    }
    if (historySort === "sets") {
      return right.rows.length - left.rows.length;
    }
    return right.performedAt.localeCompare(left.performedAt);
  });
  const selectedBackendWorkout = backendWorkoutGroups.find((workout) => workout.id === selectedCompletedWorkoutId) ?? backendWorkoutGroups[0] ?? null;
  const selectedCompletedWorkout = sortedCompletedWorkouts.find((workout) => workout.id === selectedCompletedWorkoutId) ?? sortedCompletedWorkouts[0] ?? null;
  const performanceRows = [
    ...completedWorkouts.flatMap((workout) => workout.exercises.flatMap((exercise) => completedSetRows(exercise).map((row) => ({
      day: workout.startedAt.slice(0, 10),
      workoutId: workout.id,
      weight: row.weight_kg,
      reps: row.reps,
      duration: workout.duration_seconds,
    })))),
    ...recentWorkoutRows.map((row) => ({
      day: row.performed_at.slice(0, 10),
      workoutId: row.performed_at.slice(0, 10),
      weight: row.weight_kg,
      reps: row.reps,
      duration: 0,
    })),
  ].filter((row) => !periodCutoff || new Date(row.day) >= periodCutoff);
  const dailyPerformance = Array.from(performanceRows.reduce((map, workout) => {
    const key = bucketKeyForDate(workout.day);
    const current = map.get(key) ?? { key, label: bucketLabelForKey(key), sets: 0, volume: 0, best: 0, workouts: new Set<string>(), duration: 0 };
    current.sets += 1;
    current.volume += workout.weight * workout.reps;
    current.best = Math.max(current.best, workout.weight);
    current.workouts.add(workout.workoutId);
    current.duration += workout.duration;
    map.set(key, current);
    return map;
  }, new Map<string, { key: string; label: string; sets: number; volume: number; best: number; workouts: Set<string>; duration: number }>()).values()).sort((left, right) => left.key.localeCompare(right.key)).slice(-12).map((item) => ({
    ...item,
    workoutCount: item.workouts.size,
  }));
  const selectedExerciseRows = selectedFavoriteExercise
    ? periodWorkoutRows.filter((row) => row.exercise === selectedFavoriteExercise.exercise).sort((left, right) => left.performed_at.localeCompare(right.performed_at))
    : [];
  let runningPr = 0;
  const selectedExercisePoints = Array.from(selectedExerciseRows.reduce((map, row) => {
    const key = bucketKeyForDate(row.performed_at);
    const current = map.get(key) ?? { key, label: bucketLabelForKey(key), sets: 0, volume: 0, best: 0 };
    current.sets += 1;
    current.volume += row.weight_kg * row.reps;
    current.best = Math.max(current.best, row.weight_kg);
    map.set(key, current);
    return map;
  }, new Map<string, { key: string; label: string; sets: number; volume: number; best: number }>()).values()).sort((left, right) => left.key.localeCompare(right.key)).map((point) => {
    runningPr = Math.max(runningPr, point.best);
    return { ...point, pr: runningPr };
  });
  const favoriteDetailValue = (point: (typeof selectedExercisePoints)[number]) => {
    if (favoriteDetailMetric === "volume") {
      return point.volume;
    }
    if (favoriteDetailMetric === "sets") {
      return point.sets;
    }
    return point.pr;
  };
  const favoriteDetailValues = selectedExercisePoints.map(favoriteDetailValue);
  const maxFavoriteDetailValue = Math.max(1, ...favoriteDetailValues);
  const favoriteChartFloor = favoriteDetailMetric === "pr" && selectedExercisePoints.length > 1
    ? Math.max(0, Math.min(...favoriteDetailValues) - Math.max(2.5, (maxFavoriteDetailValue - Math.min(...favoriteDetailValues)) * 0.35))
    : 0;
  const favoriteChartRange = Math.max(1, maxFavoriteDetailValue - favoriteChartFloor);
  const favoriteChartTicks = [1, 0.66, 0.33, 0].map((ratio) => Math.round(favoriteChartFloor + favoriteChartRange * ratio));
  const formatChartNumber = (value: number) => (value >= 1000 ? `${Math.round(value / 100) / 10}k` : String(Math.round(value * 10) / 10));
  const favoriteLinePoints = selectedExercisePoints.map((point, index) => {
    const value = favoriteDetailValue(point);
    const x = selectedExercisePoints.length === 1 ? 320 : 58 + (index * 524) / Math.max(1, selectedExercisePoints.length - 1);
    const y = 184 - ((value - favoriteChartFloor) / favoriteChartRange) * 132;
    return { ...point, value, x, y };
  });
  const favoriteLinePath = favoriteLinePoints.map((point) => `${point.x},${point.y}`).join(" ");
  const exerciseMuscleLookup = new Map(data.exercises.map((exercise) => [exercise.name, exercise.muscle_group]));
  const muscleDistribution = Array.from(progressExercises.reduce((map, item) => {
    const muscle = exerciseMuscleLookup.get(item.exercise) ?? "Other";
    map.set(muscle, (map.get(muscle) ?? 0) + item.sets);
    return map;
  }, new Map<string, number>()).entries()).sort((left, right) => right[1] - left[1]);
  const maxMuscleSets = Math.max(1, ...muscleDistribution.map(([, sets]) => sets));
  const performanceValue = (item: (typeof dailyPerformance)[number]) => {
    if (performanceMetric === "sets") {
      return item.sets;
    }
    if (performanceMetric === "best") {
      return item.best;
    }
    if (performanceMetric === "workouts") {
      return item.workoutCount;
    }
    return item.volume;
  };
  const performanceValues = dailyPerformance.map(performanceValue);
  const maxPerformanceValue = Math.max(1, ...performanceValues);
  const performanceChartMax = niceChartMax(maxPerformanceValue);
  const performanceAxisTicks = [1, 0.75, 0.5, 0.25, 0].map((ratio) => performanceChartMax * ratio);
  const performancePlot = { left: 62, right: 18, top: 18, bottom: 42, width: 720, height: 260 };
  const performancePlotWidth = performancePlot.width - performancePlot.left - performancePlot.right;
  const performancePlotHeight = performancePlot.height - performancePlot.top - performancePlot.bottom;
  const performanceY = (value: number) => performancePlot.top + (1 - Math.min(1, Math.max(0, value / performanceChartMax))) * performancePlotHeight;
  const performanceSlotWidth = dailyPerformance.length ? performancePlotWidth / dailyPerformance.length : performancePlotWidth;
  const performanceBarWidth = Math.min(44, Math.max(16, performanceSlotWidth * 0.36));
  const shouldShowPerformanceLabel = (index: number) => dailyPerformance.length <= 8 || index % 2 === 0 || index === dailyPerformance.length - 1;
  const compactPerformanceLabel = (key: string, fallback: string) => {
    if (bucketByMonth) {
      return fallback;
    }
    const date = new Date(`${key}T00:00:00`);
    return `${date.getDate()}.${String(date.getMonth() + 1).padStart(2, "0")}`;
  };
  const performanceTotal = dailyPerformance.reduce((sum, item) => sum + performanceValue(item), 0);
  const performanceLabel = {
    volume: "Volume",
    sets: "Sets",
    best: "Best load",
    workouts: "Workouts",
  }[performanceMetric];
  const repModeLabel = {
    auto: "Let model decide",
    custom: `${data.preferences?.preferred_rep_min ?? 8}-${data.preferences?.preferred_rep_max ?? 10} reps`,
    pr: "PR ramp",
  }[data.preferences?.preferred_rep_mode ?? "auto"];

  return (
    <section className="personalization-grid">
      <article className="panel wide-panel profile-hub-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Profile</p>
            <h3>Your progress hub</h3>
          </div>
          <Dumbbell className="accent-icon" size={26} />
        </div>
        <div className="profile-stat-grid">
          <div><Clock size={18} /><strong>{visits}</strong><span>Check-ins</span></div>
          <div><Dumbbell size={18} /><strong>{totalTrainingVolume.toLocaleString()} kg</strong><span>Volume lifted</span></div>
          <div><Activity size={18} /><strong>{loggedSets}</strong><span>Logged sets</span></div>
          <div><Trophy size={18} /><strong>{unlockedAchievementCount}</strong><span>Badges</span></div>
        </div>
        <div className="profile-shortcut-list">
          <button className={profileInsightView === "history" ? "active" : ""} onClick={() => setProfileInsightView("history")}><BookOpen size={18} /><span>Workout History</span><b>{sortedCompletedWorkouts.length || backendWorkoutGroups.length}</b></button>
          <button className={profileInsightView === "favorites" ? "active" : ""} onClick={() => setProfileInsightView("favorites")}><Trophy size={18} /><span>Favorite Exercises</span><b>{topFavoriteExercises.length}</b></button>
          <button className={profileInsightView === "performance" ? "active" : ""} onClick={() => setProfileInsightView("performance")}><Activity size={18} /><span>Performance Over Time</span><b>{dailyPerformance.length}</b></button>
          <button className={profileInsightView === "muscles" ? "active" : ""} onClick={() => setProfileInsightView("muscles")}><Target size={18} /><span>Muscle Distribution</span><b>{muscleDistribution.length}</b></button>
        </div>
        <div className="profile-insight-panel">
          {profileInsightView === "history" && (
            <div className="profile-workout-history">
              <div className="profile-toolbar">
                {(["recent", "volume", "sets"] as const).map((option) => (
                  <button className={historySort === option ? "active" : ""} key={option} onClick={() => setHistorySort(option)}>
                    {option === "recent" ? "Recent" : option === "volume" ? "Volume" : "Sets"}
                  </button>
                ))}
              </div>
              {completedWorkouts.length > 0 ? (
                <>
                  <div className="profile-workout-list">
                    {sortedCompletedWorkouts.map((workout) => (
                      <button
                        type="button"
                        className={selectedCompletedWorkout?.id === workout.id ? "active" : ""}
                        key={workout.id}
                        onClick={() => setSelectedCompletedWorkoutId(workout.id)}
                      >
                        <strong>{workout.title}</strong>
                        <span>{formatForecastSlot(workout.startedAt)}</span>
                        <small>{formatDuration(workout.duration_seconds)} - {completedWorkoutSetCount(workout)} sets - {Math.round(completedWorkoutVolume(workout)).toLocaleString()} kg</small>
                        <em>Open</em>
                      </button>
                    ))}
                  </div>
                  {selectedCompletedWorkout && (
                    <div className="profile-workout-detail">
                      <div className="profile-workout-detail-head">
                        <div>
                          <span>{formatForecastSlot(selectedCompletedWorkout.startedAt)}</span>
                          <strong>{selectedCompletedWorkout.title}</strong>
                        </div>
                        <small>{formatDuration(selectedCompletedWorkout.duration_seconds)} total</small>
                      </div>
                      {selectedCompletedWorkout.exercises.filter((item) => completedSetRows(item).length > 0).map((item) => (
                        <details className="profile-workout-exercise" key={`${selectedCompletedWorkout.id}-${item.exercise}`}>
                          <summary>
                            <strong>{item.exercise}</strong>
                            <span>{completedSetRows(item).length} sets</span>
                          </summary>
                          <div className="profile-set-list">
                            {completedSetRows(item).map((row) => (
                              <div key={row.id}>
                                <span>Set {row.set_number}</span>
                                <strong>{row.weight_kg} kg x {item.unilateral ? `${row.left_reps || row.reps}/${row.right_reps || row.reps}` : row.reps}</strong>
                                <div className="set-modifier-badges">
                                  {modifierBadges(row).map((tag) => <i key={tag}>{tag}</i>)}
                                </div>
                                <small>Rest before: {formatDuration(row.rest_before_seconds ?? 0)}</small>
                              </div>
                            ))}
                          </div>
                        </details>
                      ))}
                    </div>
                  )}
                </>
              ) : backendWorkoutGroups.length > 0 ? (
                <>
                  <div className="profile-workout-list">
                    {backendWorkoutGroups.map((workout) => {
                      const volume = workout.rows.reduce((sum, row) => sum + row.weight_kg * row.reps, 0);
                      return (
                        <button
                          type="button"
                          className={selectedBackendWorkout?.id === workout.id ? "active" : ""}
                          key={workout.id}
                          onClick={() => setSelectedCompletedWorkoutId(workout.id)}
                        >
                          <strong>{workout.title}</strong>
                          <span>{formatForecastSlot(workout.performedAt)}</span>
                          <small>{workout.rows.length} sets - {Math.round(volume).toLocaleString()} kg</small>
                          <em>Open</em>
                        </button>
                      );
                    })}
                  </div>
                  {selectedBackendWorkout && (
                    <div className="profile-workout-detail">
                      <div className="profile-workout-detail-head">
                        <div>
                          <span>{formatForecastSlot(selectedBackendWorkout.performedAt)}</span>
                          <strong>{selectedBackendWorkout.title}</strong>
                        </div>
                        <small>{selectedBackendWorkout.rows.length} logged sets</small>
                      </div>
                      {Array.from(selectedBackendWorkout.rows.reduce((map, row) => {
                        const rows = map.get(row.exercise) ?? [];
                        rows.push(row);
                        map.set(row.exercise, rows);
                        return map;
                      }, new Map<string, typeof selectedBackendWorkout.rows>()).entries()).map(([exercise, rows]) => (
                        <details className="profile-workout-exercise" key={`${selectedBackendWorkout.id}-${exercise}`}>
                          <summary>
                            <strong>{exercise}</strong>
                            <span>{rows.length} sets</span>
                          </summary>
                          <div className="profile-set-list">
                            {rows.map((row) => (
                              <div key={row.id}>
                                <span>Set {row.set_index}</span>
                                <strong>{row.weight_kg} kg x {row.reps}</strong>
                                <small>{row.notes || "Logged workout set"}</small>
                              </div>
                            ))}
                          </div>
                        </details>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div className="empty-chart">Finish an active workout to save full workout history here.</div>
              )}
            </div>
          )}
          {profileInsightView === "favorites" && (
            <div className="profile-history-list">
              <div className="profile-segmented-row">
                {(["month", "year", "all"] as const).map((period) => (
                  <button className={favoritePeriod === period ? "active" : ""} key={period} onClick={() => setFavoritePeriod(period)}>{periodLabels[period]}</button>
                ))}
              </div>
              <div className="profile-sort-row">
                <button className={favoriteSort === "sets" ? "active" : ""} onClick={() => setFavoriteSort("sets")}>Sets</button>
                <button className={favoriteSort === "volume" ? "active" : ""} onClick={() => setFavoriteSort("volume")}>Volume</button>
                <button className={favoriteSort === "best" ? "active" : ""} onClick={() => setFavoriteSort("best")}>Best</button>
              </div>
              {topFavoriteExercises.map((exercise, index) => (
                <button
                  type="button"
                  className={`profile-favorite-card ${selectedFavoriteExercise?.exercise === exercise.exercise ? "active" : ""}`}
                  key={exercise.exercise}
                  onClick={() => setSelectedFavoriteExerciseName(exercise.exercise)}
                >
                  <span>#{index + 1}</span>
                  <div>
                    <strong>{exercise.exercise}</strong>
                    <small>{exercise.sets} sets - {Math.round(exercise.total_volume_kg).toLocaleString()} kg volume - {exercise.best_weight_kg} kg best</small>
                  </div>
                  <ChevronRight size={18} />
                </button>
              ))}
              {!topFavoriteExercises.length && <div className="empty-chart">Log sets to see favorite exercises.</div>}
              {selectedFavoriteExercise && (
                <div className="profile-exercise-detail">
                  <div className="profile-exercise-detail-head">
                    <div>
                      <strong>{selectedFavoriteExercise.exercise}</strong>
                      <span>{selectedFavoriteExercise.sets} sets - {Math.round(selectedFavoriteExercise.total_volume_kg).toLocaleString()} kg total volume</span>
                    </div>
                    <small>{selectedFavoriteExercise.best_weight_kg} kg PR</small>
                  </div>
                  <div className="profile-sort-row">
                    {(["pr", "volume", "sets"] as const).map((metric) => (
                      <button className={favoriteDetailMetric === metric ? "active" : ""} key={metric} onClick={() => setFavoriteDetailMetric(metric)}>
                        {metric === "pr" ? "PR" : metric === "volume" ? "Volume" : "Sets"}
                      </button>
                    ))}
                  </div>
                  <div className={`profile-line-chart ${favoriteDetailMetric === "pr" ? "as-line" : ""}`}>
                    {favoriteDetailMetric === "pr" && selectedExercisePoints.length > 0 ? (
                      <svg className="profile-pr-line-chart" viewBox="0 0 640 230" role="img" aria-label={`${selectedFavoriteExercise.exercise} PR progress`}>
                        {[0.33, 0.66, 1].map((ratio) => (
                          <g key={ratio}>
                            <line x1="46" x2="594" y1={184 - ratio * 132} y2={184 - ratio * 132} />
                            <text x="12" y={188 - ratio * 132}>{formatChartNumber(favoriteChartFloor + favoriteChartRange * ratio)}</text>
                          </g>
                        ))}
                        <polyline points={favoriteLinePath} />
                        {favoriteLinePoints.map((point) => (
                          <g key={point.key}>
                            <circle cx={point.x} cy={point.y} r="6">
                              <title>{`${point.label}: PR ${point.pr} kg, ${Math.round(point.volume)} kg, ${point.sets} sets`}</title>
                            </circle>
                            <text className="profile-pr-value" x={point.x} y={Math.max(24, point.y - 12)}>{point.pr}kg</text>
                            <text className="profile-pr-label" x={point.x} y="214">{point.label}</text>
                          </g>
                        ))}
                      </svg>
                    ) : (
                      <>
                        <div className="profile-chart-axis" aria-hidden="true">
                          {favoriteChartTicks.map((tick) => <span key={tick}>{formatChartNumber(tick)}</span>)}
                        </div>
                        {selectedExercisePoints.map((point) => (
                          <div key={point.key} title={`${point.label}: PR ${point.pr} kg, ${Math.round(point.volume)} kg, ${point.sets} sets`}>
                            <i style={{ height: `${Math.max(8, Math.round((favoriteDetailValue(point) / maxFavoriteDetailValue) * 100))}%` }} />
                            <b>{favoriteDetailMetric === "volume" ? `${Math.round(point.volume / 100) / 10}k` : favoriteDetailValue(point)}</b>
                            <span>{point.label}</span>
                          </div>
                        ))}
                      </>
                    )}
                    {!selectedExercisePoints.length && <div className="empty-chart">No set rows inside this period.</div>}
                  </div>
                  <div className="profile-exercise-records">
                    {selectedExerciseRows.slice(-8).reverse().map((row) => (
                      <div key={row.id}>
                        <span>{formatForecastSlot(row.performed_at)}</span>
                        <strong>{row.weight_kg} kg x {row.reps}</strong>
                        <small>Set {row.set_index}{row.notes ? ` - ${row.notes}` : ""}</small>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          {profileInsightView === "performance" && (
            <div className="profile-performance-panel">
              <div className="profile-segmented-row">
                {(["month", "year", "all"] as const).map((period) => (
                  <button className={favoritePeriod === period ? "active" : ""} key={period} onClick={() => setFavoritePeriod(period)}>{periodLabels[period]}</button>
                ))}
              </div>
              <div className="profile-sort-row">
                {(["volume", "sets", "best", "workouts"] as const).map((metric) => (
                  <button className={performanceMetric === metric ? "active" : ""} key={metric} onClick={() => setPerformanceMetric(metric)}>
                    {metric === "volume" ? "Volume" : metric === "sets" ? "Sets" : metric === "best" ? "Best" : "Workouts"}
                  </button>
                ))}
              </div>
              <div className="profile-chart-summary">
                <strong>{performanceLabel}</strong>
                <span>{Math.round(performanceTotal).toLocaleString()} total across {dailyPerformance.length} logged {bucketByMonth ? "months" : "days"}</span>
              </div>
              <div className="profile-metric-strip">
                <div><span>Volume</span><strong>{Math.round(dailyPerformance.reduce((sum, item) => sum + item.volume, 0)).toLocaleString()} kg</strong></div>
                <div><span>Sets</span><strong>{dailyPerformance.reduce((sum, item) => sum + item.sets, 0)}</strong></div>
                <div><span>Best</span><strong>{Math.max(0, ...dailyPerformance.map((item) => item.best))} kg</strong></div>
              </div>
              <div className="profile-performance-chart">
                <svg viewBox={`0 0 ${performancePlot.width} ${performancePlot.height}`} role="img" aria-label={`${performanceLabel} over time`}>
                  {performanceAxisTicks.map((tick) => {
                    const y = performanceY(tick);
                    return (
                      <g key={`${performanceMetric}-${tick}`}>
                        <line x1={performancePlot.left} x2={performancePlot.width - performancePlot.right} y1={y} y2={y} />
                        <text className="profile-performance-y-label" x={performancePlot.left - 10} y={y + 4}>{formatChartNumber(tick)}</text>
                      </g>
                    );
                  })}
                  {dailyPerformance.map((item, index) => {
                    const value = performanceValue(item);
                    const centerX = performancePlot.left + performanceSlotWidth * (index + 0.5);
                    const barHeight = performancePlot.top + performancePlotHeight - performanceY(value);
                    const x = centerX - performanceBarWidth / 2;
                    const y = performanceY(value);
                    return (
                      <g key={item.key}>
                        <title>{`${item.label}: ${Math.round(item.volume)} kg, ${item.sets} sets, best ${item.best} kg`}</title>
                        <rect x={x} y={y} width={performanceBarWidth} height={barHeight} rx="9" />
                        <text className="profile-performance-value" x={centerX} y={Math.max(14, y - 9)}>
                          {performanceMetric === "volume" ? `${Math.round(item.volume / 100) / 10}k` : performanceValue(item)}
                        </text>
                        <text className="profile-performance-x-label" x={centerX} y={performancePlot.height - 12}>
                          {shouldShowPerformanceLabel(index) ? compactPerformanceLabel(item.key, item.label) : ""}
                        </text>
                      </g>
                    );
                  })}
                </svg>
                {!dailyPerformance.length && <div className="empty-chart">Performance chart appears after logged sets.</div>}
              </div>
            </div>
          )}
          {profileInsightView === "muscles" && (
            <div className="muscle-distribution-list">
              {muscleDistribution.map(([muscle, sets]) => (
                <div key={muscle}>
                  <span>{muscle}</span>
                  <div><i style={{ width: `${Math.round((sets / maxMuscleSets) * 100)}%` }} /></div>
                  <strong>{sets}</strong>
                </div>
              ))}
              {!muscleDistribution.length && <div className="empty-chart">Muscle distribution appears after logged sets.</div>}
            </div>
          )}
        </div>
      </article>
      <article className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">User profile</p>
            <h3>Preference-aware forecast use</h3>
          </div>
          <Target className="accent-icon" size={26} />
        </div>
        <div className="preference-list">
          <div><Building2 size={17} /><span>Preferred gym</span><strong>{data.gyms.find((gym) => gym.gym_id === preferredGymId)?.address ?? preferredGymId}</strong></div>
          <div><Clock size={17} /><span>Preferred window</span><strong>{data.preferences ? `${data.preferences.preferred_min_hour}:00-${data.preferences.preferred_max_hour}:00` : "11:00-16:00"}</strong></div>
          <div><Users size={17} /><span>Crowd tolerance</span><strong>{data.preferences?.max_crowd_people ?? 45} people</strong></div>
          <div><CalendarClock size={17} /><span>Weekly goal</span><strong>{data.preferences?.weekly_goal_sessions ?? 4} sessions</strong></div>
          <div><Target size={17} /><span>Rep target</span><strong>{repModeLabel}</strong></div>
        </div>
        <div className="form-grid preference-form">
          <label>Preferred gym
            <select
              value={preferredGymId}
              onChange={(event) => {
                setPreferredGymId(event.target.value);
                setSelectedGymId(event.target.value);
              }}
            >
              {data.gyms.map((gym) => (
                <option key={gym.gym_id} value={gym.gym_id}>{gym.city}, {gym.address}</option>
              ))}
            </select>
          </label>
          <label>Min hour<input type="number" min="0" max="23" value={minHour} onChange={(event) => setMinHour(event.target.value)} /></label>
          <label>Max hour<input type="number" min="1" max="24" value={maxHour} onChange={(event) => setMaxHour(event.target.value)} /></label>
          <label>Crowd limit<input type="number" min="0" max="300" value={crowdLimit} onChange={(event) => setCrowdLimit(event.target.value)} /></label>
          <label>Weekly goal<input type="number" min="1" max="14" value={weeklyGoal} onChange={(event) => setWeeklyGoal(event.target.value)} /></label>
          <label>Preferred rep range
            <select value={repMode} onChange={(event) => setRepMode(event.target.value as "auto" | "custom" | "pr")}>
              <option value="auto">Let model decide</option>
              <option value="custom">Custom range</option>
              <option value="pr">PR ramp</option>
            </select>
          </label>
          <label>Rep min<input type="number" min="1" max="30" value={repMin} disabled={repMode !== "custom"} onChange={(event) => setRepMin(event.target.value)} /></label>
          <label>Rep max<input type="number" min="1" max="30" value={repMax} disabled={repMode !== "custom"} onChange={(event) => setRepMax(event.target.value)} /></label>
          {repMode === "pr" && (
            <div className="wide-field preference-hint">
              PR ramp uses personal estimated strength, lighter warm-up targets, and a heavy top-set aim.
            </div>
          )}
          <div className="weekday-picker wide-field">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((label, index) => (
              <button className={weekdays.includes(index) ? "active" : ""} key={label} onClick={() => toggleWeekday(index)}>
                {label}
              </button>
            ))}
          </div>
          <label className="toggle-row wide-field">
            <input type="checkbox" checked={offPeakBonus} onChange={(event) => setOffPeakBonus(event.target.checked)} />
            Off-peak bonus enabled
          </label>
          <button className="primary-action wide-field" onClick={savePreferences} disabled={status === "saving"}>
            <Target size={17} /> {status === "saving" ? "Saving preferences" : "Save preferences"}
          </button>
          {status === "saved" && <span className="form-success wide-field">Preferences saved and slot recommendations refreshed.</span>}
          {status === "error" && <span className="form-error wide-field">Could not save preferences.</span>}
        </div>
      </article>
      <article className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Gamification</p>
            <h3>Level {level} Athlete</h3>
          </div>
          <Trophy className="accent-icon" size={26} />
        </div>
        <div className="level-card">
          <div>
            <span>{xp} XP</span>
            <strong>{levelProgress}% to level {level + 1}</strong>
          </div>
          <div className="progress-bar"><i style={{ width: `${levelProgress}%` }} /></div>
        </div>
        <div className="kpi-grid compact-kpis">
          <div className="kpi-card"><span>Consistency</span><strong>{data.gamification?.consistency_score ?? 0}%</strong></div>
          <div className="kpi-card"><span>Streak</span><strong>{data.gamification?.current_streak_days ?? 0}d</strong></div>
          <div className="kpi-card"><span>Off-peak bonus</span><strong>{data.gamification?.off_peak_bonus_points ?? 0}</strong></div>
        </div>
        <div className="weekly-challenge">
          <div>
            <strong>Weekly challenge</strong>
            <span>{weeklySessions}/{weeklyGoalValue} planned or completed sessions</span>
          </div>
          <div className="progress-bar"><i style={{ width: `${weeklyPercent}%` }} /></div>
        </div>
        <p>{data.gamification?.next_action ?? "Book a low-traffic slot that matches your preferred window."}</p>
      </article>
      <article className="panel wide-panel">
        <p className="eyebrow">Attendance journal</p>
        <h3>{data.activityDashboard?.visits ?? data.visits.length} QR check-ins tracked</h3>
        <div className="kpi-grid compact-kpis">
          <div className="kpi-card"><span>Logged sets</span><strong>{data.activityDashboard?.logged_sets ?? data.progress?.total_sets ?? 0}</strong></div>
          <div className="kpi-card"><span>Off-peak share</span><strong>{data.activityDashboard?.off_peak_visit_share ?? 0}%</strong></div>
          <div className="kpi-card"><span>Templates</span><strong>{data.activityDashboard?.templates ?? data.templates.length}</strong></div>
        </div>
        <div className="visit-list">
          {data.visits.slice(0, 5).map((visit) => (
            <div className="visit-card" key={visit.id}>
              <span>{formatSlot(visit.checked_in_at)} · {visit.gym_id}</span>
              <strong>{visit.active_people_at_checkin} people</strong>
              <small>{visit.note}</small>
            </div>
          ))}
        </div>
      </article>
      <article className="panel">
        <button className="achievement-panel-button" type="button" onClick={() => setShowAchievementPantheon((current) => !current)}>
          <span>
            <small className="eyebrow">Achievements</small>
            <strong>Badges and trophies</strong>
          </span>
          <b>{showAchievementPantheon ? "Compact" : "View all"}</b>
        </button>
        <div className={`achievement-grid ${showAchievementPantheon ? "full" : ""}`}>
          {achievementCatalog.slice(0, showAchievementPantheon ? achievementCatalog.length : 6).map((achievement) => {
            const percent = Math.min(100, Math.round((achievement.progress / Math.max(1, achievement.target)) * 100));
            const unlocked = Boolean(achievement.unlocked_at) || percent >= 100;
            const secret = achievement.code.includes("secret");
            return (
              <div className={`achievement-card ${unlocked ? "unlocked" : ""} ${secret ? "secret" : ""}`} key={achievement.code}>
                <div className="achievement-icon">{achievementIcon(achievement.code)}</div>
                <div className="achievement-copy">
                  <strong>{achievement.title}</strong>
                  <span>{secret && !unlocked ? "Secret achievement. Requirement hidden." : achievement.description}</span>
                </div>
                <div className="progress-bar"><i style={{ width: `${percent}%` }} /></div>
                <small>{unlocked ? `Unlocked ${formatAchievementDate(achievement.unlocked_at)}` : `${Math.round(achievement.progress)}/${achievement.target}`}</small>
              </div>
            );
          })}
        </div>
        {!achievementCatalog.length && <div className="empty-chart">Achievements will appear after activity loads.</div>}
      </article>
    </section>
  );
}
