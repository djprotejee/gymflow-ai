import { useEffect, useState } from "react";
import {
  CheckCircle2,
  Clock,
  Dumbbell,
  GripVertical,
  PlayCircle,
  Pencil,
  PlusCircle,
  Sparkles,
  Target,
  Trash2,
  X,
} from "lucide-react";
import { MuscleAnatomy } from "../components/MuscleAnatomy";
import { API_URL, getJson } from "../lib/api";
import { formatForecastSlot } from "../lib/format";
import { loadWorkoutDashboardPatch } from "../lib/workoutRefresh";
import type {
  ActiveWorkout,
  AnatomyRegionGroup,
  DashboardData,
  DashboardPatch,
  Exercise,
  NextSession,
  ActiveWorkoutSetRow,
  WorkoutTemplate,
  WorkoutTemplateExercise,
  WorkoutSetModifierState,
} from "../types";

type CompletedWorkoutSnapshot = {
  id: string;
  title: string;
  mode: ActiveWorkout["mode"];
  startedAt: string;
  endedAt: string;
  duration_seconds: number;
  exercises: WorkoutTemplateExercise[];
};

type SetPrediction = {
  weight: number;
  reps: number;
  repsMin: number;
  repsMax: number;
  kind: "working" | "warmup" | "top";
  reason: string;
};

const COMPLETED_WORKOUTS_STORAGE_KEY = "gymflow-completed-workouts";
const ACTIVE_WORKOUT_STORAGE_PREFIX = "gymflow-active-workout";

const EMPTY_SET_MODIFIERS: WorkoutSetModifierState = {
  myo_reps: false,
  myo_reps_matching: false,
  unilateral: false,
  drop_set: false,
  lengthened_partials: false,
};

export function WorkoutsPage({
  data,
  userId,
  onDashboardPatch,
}: {
  data: DashboardData;
  userId: string;
  onDashboardPatch: (patch: DashboardPatch) => void;
}) {
  const [exercise, setExercise] = useState("");
  const [weightKg, setWeightKg] = useState("62.5");
  const [reps, setReps] = useState("");
  const [setIndex, setSetIndex] = useState("1");
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [selectedExerciseSlug, setSelectedExerciseSlug] = useState("");
  const [activeWorkout, setActiveWorkout] = useState<ActiveWorkout | null>(() => {
    try {
      const storedWorkout = window.localStorage.getItem(`${ACTIVE_WORKOUT_STORAGE_PREFIX}-${userId}`);
      return storedWorkout ? JSON.parse(storedWorkout) : null;
    } catch {
      return null;
    }
  });
  const [exerciseQuery, setExerciseQuery] = useState("");
  const [exerciseMuscleFilter, setExerciseMuscleFilter] = useState("All");
  const [exerciseDifficultyFilter, setExerciseDifficultyFilter] = useState("All");
  const [exerciseQuickFilter, setExerciseQuickFilter] = useState("All");
  const [restSeconds, setRestSeconds] = useState(90);
  const [restTimerActive, setRestTimerActive] = useState(false);
  const [restTimerMode, setRestTimerMode] = useState<"global" | "exercise">("exercise");
  const [globalRestSeconds, setGlobalRestSeconds] = useState(90);
  const [selectedHistoryExercise, setSelectedHistoryExercise] = useState<string | null>(null);
  const [workoutWorkspaceView] = useState<"history" | "templates" | "progress" | "ai">("templates");
  const [draggedActiveExerciseIndex, setDraggedActiveExerciseIndex] = useState<number | null>(null);
  const [draggedTemplateExerciseIndex, setDraggedTemplateExerciseIndex] = useState<number | null>(null);
  const [anatomyCatalog, setAnatomyCatalog] = useState<AnatomyRegionGroup[]>([]);
  const [selectedMediaId, setSelectedMediaId] = useState<number | null>(null);
  const [selectedNextSession, setSelectedNextSession] = useState<NextSession | null>(null);
  const [dismissedAlternateNote, setDismissedAlternateNote] = useState(false);
  const [showTrainingPrinciple, setShowTrainingPrinciple] = useState(() => {
    try {
      return window.localStorage.getItem("gymflow-hide-hypertrophy-anchor") !== "true";
    } catch {
      return true;
    }
  });
  const [workoutNow, setWorkoutNow] = useState(Date.now());
  const [completedWorkouts, setCompletedWorkouts] = useState<CompletedWorkoutSnapshot[]>([]);
  const [selectedCompletedWorkoutId, setSelectedCompletedWorkoutId] = useState<string | null>(null);
  const [setModifiers, setSetModifiers] = useState<WorkoutSetModifierState>(EMPTY_SET_MODIFIERS);
  const [customExerciseDraft, setCustomExerciseDraft] = useState({
    name: "",
    category: "Custom",
    muscle_group: "Arms",
    difficulty: "Custom",
    primary_muscles: [] as string[],
    secondary_muscles: [] as string[],
    allow_empty_primary: false,
  });
  const [customExerciseDetailsDraft, setCustomExerciseDetailsDraft] = useState({
    category: "Custom",
    muscle_group: "Arms",
    difficulty: "Custom",
    primary_muscles: [] as string[],
    secondary_muscles: [] as string[],
    allow_empty_primary: false,
    instructions: [] as string[],
    cues: [] as string[],
    mistakes: [] as string[],
  });
  const [editingTemplateId, setEditingTemplateId] = useState<number | null>(null);
  const [templateBuilderOpen, setTemplateBuilderOpen] = useState(false);
  const [templateBuilderExercises, setTemplateBuilderExercises] = useState<WorkoutTemplateExercise[]>([]);
  const [templateDraft, setTemplateDraft] = useState({
    name: "",
    focus: "Hypertrophy",
    estimated_minutes: "60",
  });
  const selectedExercise = selectedExerciseSlug ? data.exercises.find((item) => item.slug === selectedExerciseSlug) ?? null : null;
  const selectedExerciseIsCustom = selectedExercise?.source_name === "GymFlow AI user custom exercise";
  const selectedExerciseIsAlternating = Boolean(selectedExercise && /\b(alternate|alternating)\b/i.test(selectedExercise.name));
  const exerciseMuscles = ["All", ...Array.from(new Set(data.exercises.map((item) => item.muscle_group))).sort()];
  const exerciseCategories = ["All", ...Array.from(new Set(data.exercises.map((item) => item.category))).sort()];
  const exerciseDifficulties = ["All", ...Array.from(new Set(data.exercises.map((item) => item.difficulty))).sort()];
  const exerciseQuickFilters = ["All", "With media", "Upper", "Lower", "Push", "Pull", "Machine", "Cable", "Bodyweight"];
  const hasSelectedProgressionTarget = Boolean(
    selectedExercise &&
    selectedNextSession &&
    (selectedNextSession.target_weight_kg > 0 || !selectedNextSession.reason?.toLowerCase().includes("no history")),
  );
  const matchingExercises = data.exercises
    .filter((item) => {
      const query = exerciseQuery.trim().toLowerCase();
      const matchesQuery = !query || item.name.toLowerCase().includes(query) || item.muscle_group.toLowerCase().includes(query);
      const matchesMuscle = exerciseMuscleFilter === "All" || item.muscle_group === exerciseMuscleFilter;
      const matchesDifficulty = exerciseDifficultyFilter === "All" || item.difficulty === exerciseDifficultyFilter;
      const searchable = `${item.name} ${item.category} ${item.muscle_group}`.toLowerCase();
      const hasMedia = item.media_gallery.some(isTrueExternalExerciseMedia) || Boolean(item.youtube_video_id);
      const matchesQuick = matchesExerciseQuickFilter(exerciseQuickFilter, item, searchable, hasMedia);
      return matchesQuery && matchesMuscle && matchesDifficulty && matchesQuick;
    });
  const filteredExercises = matchingExercises;
  const activeWorkoutVolume = activeWorkout?.exercises.reduce((sum, item) => {
    return sum + activeExerciseRows(item).reduce((rowSum, row) => {
      const trackedReps = item.unilateral ? Math.max(row.left_reps || row.reps || 0, row.right_reps || row.reps || 0) : row.reps;
      return rowSum + trackedReps * row.weight_kg;
    }, 0);
  }, 0) ?? 0;
  const activeWorkoutSets = activeWorkout?.exercises.reduce((sum, item) => sum + activeExerciseRows(item).length, 0) ?? 0;
  const activeWorkoutElapsedSeconds = activeWorkout ? Math.max(0, Math.floor((workoutNow - Date.parse(activeWorkout.startedAt)) / 1000)) : 0;
  const selectedCompletedWorkout = completedWorkouts.find((item) => item.id === selectedCompletedWorkoutId) ?? completedWorkouts[0] ?? null;
  const progressExercises = [...(data.progress?.exercises ?? [])].sort((left, right) => right.total_volume_kg - left.total_volume_kg);
  const filteredProgressExercises = selectedHistoryExercise
    ? progressExercises.filter((item) => item.exercise === selectedHistoryExercise)
    : progressExercises;
  const historyRows = selectedHistoryExercise
    ? data.activityDashboard?.recent_workouts.filter((item) => item.exercise === selectedHistoryExercise) ?? []
    : data.activityDashboard?.recent_workouts ?? [];
  const exactQueryMatch = data.exercises.some((item) => item.name.toLowerCase() === exerciseQuery.trim().toLowerCase());
  const showCustomExerciseBuilder = Boolean(exerciseQuery.trim()) && !selectedExercise && !exactQueryMatch;
  const customAllowsEmptyPrimary =
    customExerciseDraft.allow_empty_primary ||
    customExerciseDraft.muscle_group === "Conditioning" ||
    ["Conditioning", "Cardio", "Recovery"].includes(customExerciseDraft.category);
  const exerciseMediaOptions = selectedExercise
    ? selectedExercise.media_gallery.filter(isTrueExternalExerciseMedia).filter((item, index, items) => {
        const mediaKey = `${item.media_type}::${item.media_url || item.source_url}`;
        return items.findIndex((candidate) => `${candidate.media_type}::${candidate.media_url || candidate.source_url}` === mediaKey) === index;
      })
    : [];
  const activeMediaId = selectedMediaId ?? exerciseMediaOptions[0]?.id ?? null;
  const compactMediaOptions = exerciseMediaOptions.length > 1 ? exerciseMediaOptions.filter((item) => item.id !== activeMediaId).slice(0, 3) : [];
  const primaryExerciseMedia = preferredExerciseMedia();

  function nextCustomExerciseDefaults(name: string) {
    const inferredMuscleGroup = exerciseMuscleFilter !== "All" ? exerciseMuscleFilter : "Arms";
    const inferredCategory = inferredMuscleGroup === "Conditioning"
        ? "Conditioning"
        : "Hypertrophy";
    const inferredDifficulty = exerciseDifficultyFilter !== "All" ? exerciseDifficultyFilter : "Custom";
    const allowEmpty = inferredMuscleGroup === "Conditioning" || ["Conditioning", "Cardio", "Recovery"].includes(inferredCategory);
    return {
      name,
      category: inferredCategory,
      muscle_group: inferredMuscleGroup,
      difficulty: inferredDifficulty,
      primary_muscles: [] as string[],
      secondary_muscles: [] as string[],
      allow_empty_primary: allowEmpty,
    };
  }

  function parseYouTubeMediaId(value: string) {
    const trimmed = value.trim();
    if (!trimmed) {
      return "";
    }
    if (/^[a-zA-Z0-9_-]{11}$/.test(trimmed)) {
      return trimmed;
    }
    const match = trimmed.match(/(?:v=|youtu\.be\/|embed\/)([a-zA-Z0-9_-]{11})/);
    return match?.[1] ?? "";
  }

  function isRenderableExerciseMedia(item: { media_type: string; media_url: string; source_url: string; embed_allowed: boolean }) {
    const youtubeId = parseYouTubeMediaId(item.media_url || item.source_url);
    if (youtubeId) {
      return true;
    }
    if ((item.media_type === "external_image" || item.media_type === "local_image" || item.media_type === "image") && item.media_url) {
      return true;
    }
    if ((item.media_type === "external_gif" || item.media_type === "local_gif" || item.media_type === "gif") && item.media_url) {
      return true;
    }
    if ((item.media_type === "external_video" || item.media_type === "local_video") && item.media_url && item.embed_allowed) {
      return true;
    }
    return false;
  }

  function isTrueExternalExerciseMedia(item: { media_type: string; media_url: string; source_url: string; embed_allowed: boolean; source_name: string }) {
    if (item.source_name === "GymFlow AI generated reference") {
      return false;
    }
    return isRenderableExerciseMedia(item);
  }

  function youtubeSearchUrl(name: string) {
    return `https://www.youtube.com/results?search_query=${encodeURIComponent(`${name} proper form exercise`)}`;
  }

  function exerciseMediaRank(item: Exercise["media_gallery"][number]) {
    const mediaType = item.media_type.toLowerCase();
    if (parseYouTubeMediaId(item.media_url || item.source_url) && item.embed_allowed) {
      return 0;
    }
    if (mediaType.includes("video") && item.media_url && item.embed_allowed) {
      return 1;
    }
    if (mediaType.includes("gif") && item.media_url) {
      return 2;
    }
    if (mediaType.includes("image") && item.media_url) {
      return 3;
    }
    return 9;
  }

  function preferredExerciseMedia() {
    if (!selectedExercise) {
      return null;
    }
    const rankedMediaOptions = [...exerciseMediaOptions].sort((left, right) => exerciseMediaRank(left) - exerciseMediaRank(right));
    const selectedGalleryItem = selectedMediaId !== null
      ? selectedExercise.media_gallery.find((item) => item.id === selectedMediaId) ?? null
      : null;
    const activeGalleryItem = selectedGalleryItem ?? rankedMediaOptions[0] ?? null;
    if (activeGalleryItem) {
      const embeddedYouTubeId = parseYouTubeMediaId(activeGalleryItem.media_url || activeGalleryItem.source_url);
      if (embeddedYouTubeId && activeGalleryItem.embed_allowed) {
        return { kind: "youtube" as const, youtubeId: embeddedYouTubeId };
      }
      if ((activeGalleryItem.media_type === "external_video" || activeGalleryItem.media_type === "local_video" || activeGalleryItem.media_type === "video") && activeGalleryItem.media_url && activeGalleryItem.embed_allowed) {
        return { kind: "video" as const, mediaUrl: activeGalleryItem.media_url, title: activeGalleryItem.title };
      }
      if (
        (activeGalleryItem.media_type === "external_image" ||
          activeGalleryItem.media_type === "local_image" ||
          activeGalleryItem.media_type === "image" ||
          activeGalleryItem.media_type === "external_gif" ||
          activeGalleryItem.media_type === "local_gif" ||
          activeGalleryItem.media_type === "gif") &&
        activeGalleryItem.media_url
      ) {
        return { kind: "image" as const, mediaUrl: activeGalleryItem.media_url, title: activeGalleryItem.title };
      }
    }
    const youtubeGalleryItem = exerciseMediaOptions.find((item) => parseYouTubeMediaId(item.media_url || item.source_url));
    if (selectedExercise.youtube_video_id) {
      return { kind: "youtube" as const, youtubeId: selectedExercise.youtube_video_id };
    }
    if (youtubeGalleryItem) {
      return { kind: "youtube" as const, youtubeId: parseYouTubeMediaId(youtubeGalleryItem.media_url || youtubeGalleryItem.source_url) };
    }
    const externalVideoItem = exerciseMediaOptions.find((item) => item.media_type.includes("video") && item.media_url && item.embed_allowed);
    if (externalVideoItem) {
      return { kind: "video" as const, mediaUrl: externalVideoItem.media_url, title: externalVideoItem.title };
    }
    const gifGalleryItem = exerciseMediaOptions.find((item) =>
      ["external_gif", "local_gif", "gif"].includes(item.media_type) && item.media_url
    );
    if (gifGalleryItem) {
      return { kind: "image" as const, mediaUrl: gifGalleryItem.media_url, title: gifGalleryItem.title };
    }
    const imageGalleryItem = exerciseMediaOptions.find((item) =>
      ["external_image", "local_image", "image"].includes(item.media_type) && item.media_url
    );
    if (imageGalleryItem) {
      return { kind: "image" as const, mediaUrl: imageGalleryItem.media_url, title: imageGalleryItem.title };
    }
    return null;
  }

  function matchesExerciseQuickFilter(filter: string, item: Exercise, searchable: string, hasMedia: boolean) {
    const group = item.muscle_group.toLowerCase();
    const name = item.name.toLowerCase();
    if (filter === "All") {
      return true;
    }
    if (filter === "With media") {
      return hasMedia;
    }
    if (filter === "Upper") {
      return ["arms", "back", "chest", "shoulders"].includes(group);
    }
    if (filter === "Lower") {
      return ["legs", "glutes", "hamstrings", "calves"].includes(group);
    }
    if (filter === "Push") {
      return group === "chest" || group === "shoulders" || name.includes("tricep") || name.includes("press") || name.includes("push");
    }
    if (filter === "Pull") {
      return group === "back" || name.includes("curl") || name.includes("row") || name.includes("pulldown") || name.includes("pull-up");
    }
    return searchable.includes(filter.toLowerCase());
  }

  function normalizedInstructionSteps(steps: string[]) {
    const cleaned = steps
      .flatMap((step) => {
        const normalized = step.replace(/\u200b/g, "").replace(/\s+/g, " ").trim();
        if (!/\d+[.)]\s+/.test(normalized)) {
          return [normalized];
        }
        return normalized.split(/\s*\d+[.)]\s+/).filter(Boolean);
      })
      .map((step) => step.replace(/^\d+[.)]\s*/, "").trim())
      .filter(Boolean);
    const merged: string[] = [];
    for (const step of cleaned) {
      if (!merged.length) {
        merged.push(step);
        continue;
      }
      const previous = merged[merged.length - 1];
      const shouldMerge =
        !/[.!?]$/.test(previous) ||
        /^[a-z(]/.test(step) ||
        /\b(the|a|an|and|or|to|with|without|by|during|at|on|in|of)$/i.test(previous);
      if (shouldMerge) {
        merged[merged.length - 1] = `${previous} ${step}`.replace(/\s+/g, " ").trim();
        continue;
      }
      merged.push(step);
    }
    return merged;
  }

  function formatSetModifiers(modifiers?: {
    myo_reps: boolean;
    myo_reps_matching: boolean;
    unilateral: boolean;
    drop_set: boolean;
    lengthened_partials: boolean;
  }) {
    if (!modifiers) {
      return "";
    }
    const tags: string[] = [];
    if (modifiers.myo_reps) {
      tags.push(modifiers.myo_reps_matching ? "Myo-reps matching" : "Myo-reps");
    }
    if (modifiers.drop_set) {
      tags.push("Drop-set");
    }
    if (modifiers.lengthened_partials) {
      tags.push("Lengthened partials");
    }
    return tags.join(" - ");
  }

  function modifierBadges(modifiers?: WorkoutSetModifierState) {
    const tags: string[] = [];
    if (modifiers?.myo_reps) {
      tags.push(modifiers.myo_reps_matching ? "Myo match" : "Myo");
    }
    if (modifiers?.drop_set) {
      tags.push("Drop");
    }
    if (modifiers?.lengthened_partials) {
      tags.push("Partials");
    }
    return tags;
  }

  useEffect(() => {
    void getJson<AnatomyRegionGroup[]>("/exercise-library/anatomy-regions")
      .then((response) => setAnatomyCatalog(response))
      .catch(() => setAnatomyCatalog([]));
  }, []);

  useEffect(() => {
    try {
      const storedWorkouts = window.localStorage.getItem(COMPLETED_WORKOUTS_STORAGE_KEY);
      setCompletedWorkouts(storedWorkouts ? JSON.parse(storedWorkouts) : []);
    } catch {
      setCompletedWorkouts([]);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(COMPLETED_WORKOUTS_STORAGE_KEY, JSON.stringify(completedWorkouts.slice(0, 20)));
  }, [completedWorkouts]);

  useEffect(() => {
    const storageKey = `${ACTIVE_WORKOUT_STORAGE_PREFIX}-${userId}`;
    try {
      if (activeWorkout) {
        window.localStorage.setItem(storageKey, JSON.stringify(activeWorkout));
      } else {
        window.localStorage.removeItem(storageKey);
      }
    } catch {
      // Browser storage can fail in private mode; the active in-memory workout still remains usable.
    }
  }, [activeWorkout, userId]);

  useEffect(() => {
    if (!activeWorkout) {
      return;
    }
    const timer = window.setInterval(() => setWorkoutNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [activeWorkout]);

  useEffect(() => {
    const nextName = exerciseQuery.trim();
    setCustomExerciseDraft((current) => {
      if (!showCustomExerciseBuilder) {
        return nextCustomExerciseDefaults("");
      }
      const nextDraft = { ...current, name: nextName };
      if (current.name === nextName && current.category && current.muscle_group) {
        return nextDraft;
      }
      return {
        ...nextCustomExerciseDefaults(nextName),
        primary_muscles: current.primary_muscles,
        secondary_muscles: current.secondary_muscles,
      };
    });
  }, [exerciseDifficultyFilter, exerciseMuscleFilter, exerciseQuery, showCustomExerciseBuilder]);

  useEffect(() => {
    if (!selectedExercise) {
      return;
    }
    setDismissedAlternateNote(false);
    setSelectedMediaId(selectedExercise.media_gallery[0]?.id ?? null);
    setCustomExerciseDetailsDraft({
      category: selectedExercise.category,
      muscle_group: selectedExercise.muscle_group,
      difficulty: selectedExercise.difficulty,
      primary_muscles: [...selectedExercise.primary_muscles],
      secondary_muscles: [...selectedExercise.secondary_muscles],
      allow_empty_primary: selectedExercise.primary_muscles.length === 0,
      instructions: [...selectedExercise.instructions],
      cues: [...selectedExercise.cues],
      mistakes: [...selectedExercise.mistakes],
    });
  }, [selectedExercise]);

  useEffect(() => {
    // The picker owns the exercise name used by the logging form, so keep both in sync.
    if (selectedExerciseSlug && !selectedExercise) {
      setSelectedExerciseSlug("");
      return;
    }
    if (selectedExercise) {
      setExercise(selectedExercise.name);
    }
  }, [selectedExercise, selectedExerciseSlug]);

  useEffect(() => {
    if (!selectedExercise) {
      setSelectedNextSession(null);
      return;
    }
    void getJson<NextSession>(`/users/${userId}/next-session?exercise=${encodeURIComponent(selectedExercise.name)}`)
      .then((response) => setSelectedNextSession(response))
      .catch(() => setSelectedNextSession(null));
  }, [selectedExercise, userId]);

  useEffect(() => {
    // The rest timer is local UI state; persisted workout history only stores completed set data.
    if (!restTimerActive) {
      return;
    }
    if (restSeconds <= 0) {
      setRestTimerActive(false);
      return;
    }
    const timer = window.setTimeout(() => setRestSeconds((current) => Math.max(0, current - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [restSeconds, restTimerActive]);

  function chooseExercise(slug: string) {
    if (slug === selectedExerciseSlug) {
      setSelectedExerciseSlug("");
      setExercise("");
      setSelectedNextSession(null);
      return;
    }
    const nextExercise = data.exercises.find((item) => item.slug === slug);
    setSelectedExerciseSlug(slug);
    if (nextExercise) {
      setExercise(nextExercise.name);
    }
  }

  function currentTargetReps() {
    return Number(reps || selectedNextSession?.target_reps || 0);
  }

  function roundLoad(value: number) {
    return Math.max(0, Math.round(value / 2.5) * 2.5);
  }

  function roundLoadDown(value: number) {
    return Math.max(0, Math.floor(value / 2.5) * 2.5);
  }

  function parseLoadInput(value: string) {
    const normalized = value.replace(",", ".").trim();
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function estimateEpley(weight: number, repsValue: number) {
    return weight * (1 + Math.max(1, repsValue) / 30);
  }

  function preferredRepRange(item: WorkoutTemplateExercise) {
    const mode = data.preferences?.preferred_rep_mode ?? "auto";
    if (mode === "custom") {
      const low = Math.max(1, Math.min(30, data.preferences?.preferred_rep_min ?? 8));
      const high = Math.max(low, Math.min(30, data.preferences?.preferred_rep_max ?? 10));
      return { mode, low, high };
    }
    if (mode === "pr") {
      return { mode, low: 1, high: 3 };
    }
    const center = item.reps || currentTargetReps() || selectedNextSession?.target_reps || 9;
    return { mode, low: Math.max(5, center - 1), high: Math.min(15, center + 1) };
  }

  function loadForRepTarget(e1rm: number, repsValue: number) {
    return roundLoad(e1rm / (1 + Math.max(1, repsValue) / 30));
  }

  function prRampPrediction(item: WorkoutTemplateExercise, history: ReturnType<typeof exerciseHistoryRows>, rowIndex: number, fallbackWeight: number): SetPrediction {
    const bestE1rm = history.length
      ? Math.max(...history.map((row) => estimateEpley(row.weight_kg, row.reps)))
      : estimateEpley(Math.max(0, fallbackWeight), 3);
    const topWeight = Math.max(fallbackWeight, loadForRepTarget(bestE1rm, 2));
    const ramp = [
      { ratio: 0.5, repsMin: 8, repsMax: 10, kind: "warmup" as const, label: "50% warm-up" },
      { ratio: 0.7, repsMin: 4, repsMax: 6, kind: "warmup" as const, label: "70% warm-up" },
      { ratio: 0.85, repsMin: 2, repsMax: 3, kind: "warmup" as const, label: "85% warm-up" },
      { ratio: 1, repsMin: 1, repsMax: 3, kind: "top" as const, label: "heavy top set" },
    ];
    const step = ramp[Math.min(rowIndex, ramp.length - 1)];
    return {
      weight: roundLoad(topWeight * step.ratio),
      reps: Math.round((step.repsMin + step.repsMax) / 2),
      repsMin: step.repsMin,
      repsMax: step.repsMax,
      kind: step.kind,
      reason: `PR mode: ${step.label} based on personal estimated strength. Warm-up sets are intended to prepare without creating extra fatigue.`,
    };
  }

  function exerciseHistoryRows(exerciseName: string) {
    return (data.activityDashboard?.recent_workouts ?? [])
      .filter((row) => row.exercise.toLowerCase() === exerciseName.toLowerCase())
      .sort((left, right) => left.performed_at.localeCompare(right.performed_at));
  }

  function predictSetTarget(item: WorkoutTemplateExercise, rows: ActiveWorkoutSetRow[], rowIndex: number): SetPrediction {
    const repPolicy = preferredRepRange(item);
    const history = exerciseHistoryRows(item.exercise);
    const fallbackWeight = item.target_weight_kg || parseLoadInput(weightKg) || selectedNextSession?.target_weight_kg || 0;
    if (repPolicy.mode === "pr") {
      return prRampPrediction(item, history, rowIndex, fallbackWeight);
    }
    const priorRows = rows.slice(0, rowIndex).filter((row) => row.completed || row.reps || row.left_reps || row.right_reps);
    const previousRow = priorRows[priorRows.length - 1];
    if (previousRow) {
      const previousReps = setRowLoggedReps(item, previousRow);
      const sessionDrop = priorRows.length >= 2
        ? Math.max(1, setRowLoggedReps(item, priorRows[priorRows.length - 2]) - previousReps)
        : 1;
      const firstPrior = priorRows[0];
      const firstE1rm = estimateEpley(firstPrior.weight_kg, setRowLoggedReps(item, firstPrior));
      const previousE1rm = estimateEpley(previousRow.weight_kg, previousReps);
      const accumulatedLoadDrop = firstPrior.weight_kg - previousRow.weight_kg >= 2.5;
      const repsAtOrBelowLowerTarget = previousReps <= repPolicy.low;
      const repsDroppedHard = setRowLoggedReps(item, firstPrior) - previousReps >= 2;
      const estimatedStrengthDrop = firstE1rm > 0 ? (firstE1rm - previousE1rm) / firstE1rm : 0;
      const shouldDeloadForFatigue = repsAtOrBelowLowerTarget || repsDroppedHard || (accumulatedLoadDrop && (previousReps <= repPolicy.low || estimatedStrengthDrop >= 0.03));
      if (previousReps >= 12) {
        return {
          weight: roundLoad(previousRow.weight_kg + 2.5),
          reps: repPolicy.low,
          repsMin: repPolicy.low,
          repsMax: repPolicy.high,
          kind: "working",
          reason: "Previous set exceeded the upper rep target; increase load slightly and rebuild reps inside your preferred range.",
        };
      }
      const nextReps = Math.max(repPolicy.low, Math.min(repPolicy.high, previousReps - sessionDrop));
      const nextWeight = shouldDeloadForFatigue
        ? roundLoadDown(previousRow.weight_kg - 2.5)
        : roundLoadDown(previousRow.weight_kg);
      return {
        weight: nextWeight,
        reps: nextReps,
        repsMin: nextReps,
        repsMax: Math.min(repPolicy.high, nextReps + 2),
        kind: "working",
        reason: shouldDeloadForFatigue
          ? "Earlier sets show accumulated fatigue, so the next target lowers the load instead of rounding it up."
          : "Uses the current workout fatigue pattern from earlier sets of this exercise.",
      };
    }

    const fallbackReps = item.reps || currentTargetReps() || selectedNextSession?.target_reps || 8;
    if (!history.length) {
      return {
        weight: roundLoad(fallbackWeight),
        reps: fallbackReps || 8,
        repsMin: repPolicy.low,
        repsMax: repPolicy.high,
        kind: "working",
        reason: "No personal history for this exercise yet; using a conservative first-session estimate.",
      };
    }

    const latestDay = history[history.length - 1].performed_at.slice(0, 10);
    const latestSession = history.filter((row) => row.performed_at.slice(0, 10) === latestDay);
    const matchingSet = latestSession.find((row) => row.set_index === rowIndex + 1) ?? latestSession[Math.min(rowIndex, latestSession.length - 1)];
    const avgLatestReps = latestSession.reduce((sum, row) => sum + row.reps, 0) / Math.max(1, latestSession.length);
    const bestRecentWeight = Math.max(...latestSession.map((row) => row.weight_kg));
    if (rowIndex === 0 && avgLatestReps >= 10) {
      const estimated = Math.max(...latestSession.map((row) => estimateEpley(row.weight_kg, row.reps)));
      return {
        weight: Math.max(roundLoad(bestRecentWeight), loadForRepTarget(estimated, repPolicy.low)),
        reps: repPolicy.low,
        repsMin: repPolicy.low,
        repsMax: repPolicy.high,
        kind: "working",
        reason: "Recent session cleared the target range; suggests a load that fits your preferred reps.",
      };
    }
    const matchingE1rm = estimateEpley(matchingSet.weight_kg, matchingSet.reps);
    const targetReps = Math.max(repPolicy.low, Math.min(repPolicy.high, matchingSet.reps));
    return {
      weight: loadForRepTarget(matchingE1rm, targetReps),
      reps: targetReps,
      repsMin: Math.max(repPolicy.low, targetReps - 1),
      repsMax: Math.min(repPolicy.high, targetReps + 1),
      kind: "working",
      reason: "Uses the matching set from the latest personal session and adapts it to your preferred rep range.",
    };
  }

  function setRowLoggedReps(item: WorkoutTemplateExercise, row: ActiveWorkoutSetRow) {
    if (item.unilateral) {
      return Math.min(row.left_reps || row.reps || 0, row.right_reps || row.reps || 0);
    }
    return Number(row.reps || 0);
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

  function nextSetRow(setNumber: number, item?: WorkoutTemplateExercise, blankReps = false): ActiveWorkoutSetRow {
    const baseItem = item ?? {
      exercise,
      sets: setNumber,
      reps: currentTargetReps() || 8,
      target_weight_kg: parseLoadInput(weightKg) || selectedNextSession?.target_weight_kg || 0,
      rest_seconds: 90,
    };
    const prediction = predictSetTarget(baseItem, item?.set_rows ?? [], setNumber - 1);
      const rowReps = blankReps ? 0 : prediction.reps;
      const rowWeight = prediction.weight;
    return {
      id: `${Date.now()}-${setNumber}-${Math.random().toString(16).slice(2)}`,
      set_number: setNumber,
      weight_kg: rowWeight,
      reps: rowReps,
      left_reps: item?.left_reps ?? rowReps,
      right_reps: item?.right_reps ?? rowReps,
        target_weight_kg: prediction.weight,
      target_reps: prediction.reps,
      target_reps_min: prediction.repsMin,
      target_reps_max: prediction.repsMax,
      target_kind: prediction.kind,
      prediction_reason: prediction.reason,
      modifiers: { ...setModifiers, unilateral: false },
    };
  }

  function activeExerciseRows(item: WorkoutTemplateExercise): ActiveWorkoutSetRow[] {
    if (item.set_rows?.length) {
      return item.set_rows;
    }
    const rows: ActiveWorkoutSetRow[] = [];
    Array.from({ length: Math.max(1, item.sets || 1) }, (_, rowIndex) => {
      rows.push({
        ...nextSetRow(rowIndex + 1, { ...item, set_rows: rows }),
        id: `${item.exercise}-${rowIndex + 1}`,
        modifiers: EMPTY_SET_MODIFIERS,
        completed: false,
      });
    });
    return rows;
  }

  function nextActiveExercise(name: string, expanded = true): WorkoutTemplateExercise {
    const targetReps = currentTargetReps();
    const nextExercise = {
      exercise: name,
      sets: 1,
      reps: targetReps,
      target_weight_kg: parseLoadInput(weightKg),
      rest_seconds: 90,
      unilateral: false,
      left_reps: targetReps,
      right_reps: targetReps,
      expanded,
      set_modifiers: EMPTY_SET_MODIFIERS,
    };
    return { ...nextExercise, set_rows: [nextSetRow(1, nextExercise)] };
  }

  async function createCustomExercise() {
    const nextName = customExerciseDraft.name.trim();
    if (!nextName) {
      return;
    }
    setStatus("saving");
    try {
      const response = await fetch(`${API_URL}/users/${userId}/exercise-library`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: nextName,
          muscle_group: customExerciseDraft.muscle_group,
          category: customExerciseDraft.category,
          difficulty: customExerciseDraft.difficulty,
          primary_muscles: customExerciseDraft.primary_muscles,
          secondary_muscles: customExerciseDraft.secondary_muscles,
          allow_empty_primary: customAllowsEmptyPrimary,
        }),
      });
      if (!response.ok) {
        throw new Error("Custom exercise create failed");
      }
      const created = await response.json();
      const refreshed = await getJson<typeof data.exercises>("/exercise-library");
      onDashboardPatch({ exercises: refreshed });
      setSelectedExerciseSlug(String(created.slug ?? ""));
      setExercise(String(created.name ?? nextName));
      setExerciseQuery(String(created.name ?? nextName));
      setCustomExerciseDraft(nextCustomExerciseDefaults(""));
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  function clearExerciseSelection(resetFilters = false) {
    setSelectedExerciseSlug("");
    setExercise("");
    setExerciseQuery("");
    if (resetFilters) {
      setExerciseMuscleFilter("All");
      setExerciseDifficultyFilter("All");
      setExerciseQuickFilter("All");
    }
    setCustomExerciseDraft(nextCustomExerciseDefaults(""));
  }

  function toggleCustomRegion(target: "primary_muscles" | "secondary_muscles", regionId: string) {
    setCustomExerciseDraft((current) => {
      const nextPrimary = [...current.primary_muscles];
      const nextSecondary = [...current.secondary_muscles];
      const inPrimary = nextPrimary.includes(regionId);
      const inSecondary = nextSecondary.includes(regionId);
      if (target === "primary_muscles") {
        const updatedPrimary = inPrimary ? nextPrimary.filter((item) => item !== regionId) : [...nextPrimary, regionId];
        return {
          ...current,
          primary_muscles: updatedPrimary,
          secondary_muscles: nextSecondary.filter((item) => item !== regionId),
          allow_empty_primary: current.allow_empty_primary && updatedPrimary.length === 0,
        };
      }
      const updatedSecondary = inSecondary ? nextSecondary.filter((item) => item !== regionId) : [...nextSecondary, regionId];
      return {
        ...current,
        secondary_muscles: updatedSecondary.filter((item) => !nextPrimary.includes(item)),
      };
    });
  }

  async function refreshExercisesAfterMutation(nextSlug?: string) {
    const refreshedExercises = await getJson<typeof data.exercises>("/exercise-library");
    onDashboardPatch({ exercises: refreshedExercises });
    if (!nextSlug) {
      return;
    }
    const stillExists = refreshedExercises.find((item) => item.slug === nextSlug);
    if (stillExists) {
      setSelectedExerciseSlug(stillExists.slug);
      setExercise(stillExists.name);
      setExerciseQuery(stillExists.name);
      return;
    }
    clearExerciseSelection();
  }

  async function saveSelectedCustomExercise() {
    if (!selectedExercise || !selectedExerciseIsCustom) {
      return;
    }
    setStatus("saving");
    try {
      const response = await fetch(`${API_URL}/users/${userId}/exercise-library/${selectedExercise.slug}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(customExerciseDetailsDraft),
      });
      if (!response.ok) {
        throw new Error("Custom exercise update failed");
      }
      await refreshExercisesAfterMutation(selectedExercise.slug);
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  async function deleteSelectedCustomExercise() {
    if (!selectedExercise || !selectedExerciseIsCustom) {
      return;
    }
    setStatus("saving");
    try {
      const response = await fetch(`${API_URL}/users/${userId}/exercise-library/${selectedExercise.slug}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error("Custom exercise delete failed");
      }
      await refreshExercisesAfterMutation();
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  function toggleExerciseDetailsRegion(target: "primary_muscles" | "secondary_muscles", regionId: string) {
    setCustomExerciseDetailsDraft((current) => {
      const nextPrimary = [...current.primary_muscles];
      const nextSecondary = [...current.secondary_muscles];
      const inPrimary = nextPrimary.includes(regionId);
      const inSecondary = nextSecondary.includes(regionId);
      if (target === "primary_muscles") {
        const updatedPrimary = inPrimary ? nextPrimary.filter((item) => item !== regionId) : [...nextPrimary, regionId];
        return {
          ...current,
          primary_muscles: updatedPrimary,
          secondary_muscles: nextSecondary.filter((item) => item !== regionId),
        };
      }
      const updatedSecondary = inSecondary ? nextSecondary.filter((item) => item !== regionId) : [...nextSecondary, regionId];
      return {
        ...current,
        secondary_muscles: updatedSecondary.filter((item) => !nextPrimary.includes(item)),
      };
    });
  }

  function addExerciseToActiveWorkout() {
    const nextName = exercise.trim() || exerciseQuery.trim();
    if (!nextName) {
      return;
    }
    const nextExercise = nextActiveExercise(nextName);
    setActiveWorkout((current) => {
      if (!current) {
        return {
          mode: "custom",
          title: "Custom workout",
          exercises: [nextExercise],
          startedAt: new Date().toISOString(),
        };
      }
      return { ...current, exercises: [...current.exercises, nextExercise] };
    });
  }

  function updateActiveExercise(index: number, patch: Partial<WorkoutTemplateExercise>) {
    setActiveWorkout((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        exercises: current.exercises.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
      };
    });
  }

  function updateActiveSetRow(exerciseIndex: number, rowIndex: number, patch: Partial<ActiveWorkoutSetRow>) {
    setActiveWorkout((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        exercises: current.exercises.map((item, itemIndex) => {
          if (itemIndex !== exerciseIndex) {
            return item;
          }
          const rows = activeExerciseRows(item).map((row, nextRowIndex) => (nextRowIndex === rowIndex ? { ...row, ...patch } : row));
          return {
            ...item,
            set_rows: rows,
            sets: rows.length,
            reps: rows[rowIndex]?.reps ?? item.reps,
            target_weight_kg: rows[rowIndex]?.weight_kg ?? item.target_weight_kg,
          };
        }),
      };
    });
  }

  function addSetRow(exerciseIndex: number) {
    setActiveWorkout((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        exercises: current.exercises.map((item, itemIndex) => {
          if (itemIndex !== exerciseIndex) {
            return item;
          }
          const rows = activeExerciseRows(item);
          const nextRows = [...rows, nextSetRow(rows.length + 1, { ...item, set_rows: rows }, true)];
          return { ...item, set_rows: nextRows, sets: nextRows.length };
        }),
      };
    });
  }

  function removeSetRow(exerciseIndex: number) {
    setActiveWorkout((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        exercises: current.exercises.map((item, itemIndex) => {
          if (itemIndex !== exerciseIndex) {
            return item;
          }
          const rows = activeExerciseRows(item);
          const nextRows = rows.length > 1 ? rows.slice(0, -1) : rows;
          return { ...item, set_rows: nextRows, sets: nextRows.length };
        }),
      };
    });
  }

  function updateActiveExerciseUnilateral(exerciseIndex: number, unilateral: boolean) {
    setActiveWorkout((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        exercises: current.exercises.map((item, itemIndex) => {
          if (itemIndex !== exerciseIndex) {
            return item;
          }
          return { ...item, unilateral };
        }),
      };
    });
  }

  function updateActiveSetModifiers(exerciseIndex: number, rowIndex: number, patch: Partial<WorkoutSetModifierState>) {
    setActiveWorkout((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        exercises: current.exercises.map((item, itemIndex) => {
          if (itemIndex !== exerciseIndex) {
            return item;
          }
          const rows = activeExerciseRows(item).map((row, nextRowIndex) => {
            if (nextRowIndex !== rowIndex || row.completed) {
              return row;
            }
            const nextModifiers = { ...(row.modifiers ?? EMPTY_SET_MODIFIERS), ...patch, unilateral: false };
            if (!nextModifiers.myo_reps) {
              nextModifiers.myo_reps_matching = false;
            }
            return { ...row, modifiers: nextModifiers };
          });
          return { ...item, set_rows: rows };
        }),
      };
    });
  }

  function cancelActiveWorkout() {
    if (!activeWorkout) {
      return;
    }
    if (!window.confirm("Cancel this active workout? Logged backend sets stay saved, but the active workout draft will be removed.")) {
      return;
    }
    setActiveWorkout(null);
    setRestTimerActive(false);
    setStatus("idle");
  }

  function moveActiveExercise(index: number, direction: -1 | 1) {
    setActiveWorkout((current) => {
      if (!current) {
        return current;
      }
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= current.exercises.length) {
        return current;
      }
      const nextExercises = [...current.exercises];
      const [moved] = nextExercises.splice(index, 1);
      nextExercises.splice(nextIndex, 0, moved);
      return { ...current, exercises: nextExercises };
    });
  }

  function reorderActiveExercise(sourceIndex: number | null, targetIndex: number) {
    if (sourceIndex === null || sourceIndex === targetIndex) {
      return;
    }
    setActiveWorkout((current) => {
      if (!current || sourceIndex < 0 || sourceIndex >= current.exercises.length || targetIndex < 0 || targetIndex >= current.exercises.length) {
        return current;
      }
      const nextExercises = [...current.exercises];
      const [moved] = nextExercises.splice(sourceIndex, 1);
      nextExercises.splice(targetIndex, 0, moved);
      return { ...current, exercises: nextExercises };
    });
    setDraggedActiveExerciseIndex(null);
  }

  function addSelectedExerciseToTemplateBuilder() {
    const nextName = exercise.trim() || selectedExercise?.name || exerciseQuery.trim();
    if (!nextName) {
      return;
    }
    setTemplateBuilderExercises((current) => [...current, nextActiveExercise(nextName, true)]);
    setTemplateBuilderOpen(true);
  }

  function removeTemplateBuilderExercise(index: number) {
    setTemplateBuilderExercises((current) => current.filter((_, itemIndex) => itemIndex !== index));
  }

  function moveTemplateBuilderExercise(index: number, direction: -1 | 1) {
    setTemplateBuilderExercises((current) => {
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= current.length) {
        return current;
      }
      const nextExercises = [...current];
      const [moved] = nextExercises.splice(index, 1);
      nextExercises.splice(nextIndex, 0, moved);
      return nextExercises;
    });
  }

  function reorderTemplateBuilderExercise(sourceIndex: number | null, targetIndex: number) {
    if (sourceIndex === null || sourceIndex === targetIndex) {
      return;
    }
    setTemplateBuilderExercises((current) => {
      if (sourceIndex < 0 || sourceIndex >= current.length || targetIndex < 0 || targetIndex >= current.length) {
        return current;
      }
      const nextExercises = [...current];
      const [moved] = nextExercises.splice(sourceIndex, 1);
      nextExercises.splice(targetIndex, 0, moved);
      return nextExercises;
    });
    setDraggedTemplateExerciseIndex(null);
  }

  function removeActiveExercise(index: number) {
    setActiveWorkout((current) => {
      if (!current) {
        return current;
      }
      const nextExercises = current.exercises.filter((_, itemIndex) => itemIndex !== index);
      return nextExercises.length ? { ...current, exercises: nextExercises } : null;
    });
  }

  async function logActiveSetRow(item: WorkoutTemplateExercise, exerciseIndex: number, rowIndex: number) {
    // One-click active-session logging reuses the same API contract as the manual set form.
    const row = activeExerciseRows(item)[rowIndex];
    if (!row || row.completed) {
      return;
    }
    const isUnilateral = Boolean(item.unilateral);
    const leftReps = Number(row.left_reps || row.reps || 0);
    const rightReps = Number(row.right_reps || row.reps || 0);
    const loggedReps = isUnilateral ? Math.max(leftReps, rightReps) : Number(row.reps || 0);
    const latestCompletedAt = latestActiveSetCompletedAt();
    const restBeforeSeconds = latestCompletedAt ? Math.max(0, Math.floor((Date.now() - Date.parse(latestCompletedAt)) / 1000)) : 0;
    const splitNote = isUnilateral ? ` Unilateral split: left ${leftReps}, right ${rightReps}.` : "";
    const restNote = restBeforeSeconds ? ` Rest before set: ${formatDuration(restBeforeSeconds)}.` : "";
    if (!loggedReps) {
      return;
    }
    setExercise(item.exercise);
    setWeightKg(String(row.weight_kg));
    setReps(String(loggedReps));
    setSetIndex(String(row.set_number));
    setNotes(`Logged from active workout: ${activeWorkout?.title ?? "Workout"}.${splitNote}${restNote}`);
    setStatus("saving");
    try {
      const response = await fetch(`${API_URL}/users/${userId}/workouts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          exercise: item.exercise,
          weight_kg: row.weight_kg,
          reps: loggedReps,
          set_index: row.set_number,
          notes: `Logged from active workout: ${activeWorkout?.title ?? "Workout"}.${splitNote}${restNote}`,
          modifiers: { ...(row.modifiers ?? EMPTY_SET_MODIFIERS), unilateral: isUnilateral },
        }),
      });
      if (!response.ok) {
        throw new Error("Workout save failed");
      }
      updateActiveSetRow(exerciseIndex, rowIndex, {
        completed: true,
        completed_at: new Date().toISOString(),
        rest_before_seconds: restBeforeSeconds,
        target_weight_kg: row.weight_kg,
        target_reps: loggedReps,
        target_reps_min: loggedReps,
        target_reps_max: loggedReps,
        target_kind: "working",
        prediction_reason: "Logged value from the completed set.",
      });
      setRestSeconds(item.rest_seconds);
      setRestTimerActive(true);
      onDashboardPatch(await loadWorkoutDashboardPatch(userId, item.exercise));
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  function latestActiveSetCompletedAt() {
    const completedTimes = activeWorkout?.exercises
      .flatMap((item) => activeExerciseRows(item))
      .map((row) => row.completed_at)
      .filter(Boolean) as string[] | undefined;
    const sortedTimes = completedTimes?.sort() ?? [];
    return sortedTimes.length ? sortedTimes[sortedTimes.length - 1] : null;
  }

  function startRest(seconds: number) {
    setRestSeconds(seconds);
    setRestTimerActive(true);
  }

  function dismissTrainingPrinciple() {
    setShowTrainingPrinciple(false);
    try {
      window.localStorage.setItem("gymflow-hide-hypertrophy-anchor", "true");
    } catch {
      // Non-critical preference persistence can fail in private browsing.
    }
  }

  async function saveWorkoutSet() {
    if (!activeWorkout) {
      return;
    }
    const nextExercise = exercise.trim() || selectedExercise?.name || exerciseQuery.trim();
    if (!nextExercise || !reps.trim()) {
      return;
    }
    setStatus("saving");
    try {
      const response = await fetch(`${API_URL}/users/${userId}/workouts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          exercise: nextExercise,
          weight_kg: parseLoadInput(weightKg),
          reps: currentTargetReps(),
          set_index: Number(setIndex),
          notes,
          modifiers: setModifiers,
        }),
      });
      if (!response.ok) {
        throw new Error("Workout save failed");
      }
      onDashboardPatch(await loadWorkoutDashboardPatch(userId, nextExercise));
      setSetIndex(String(Number(setIndex) + 1));
      setNotes("");
      setSetModifiers(EMPTY_SET_MODIFIERS);
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  function hydrateActiveExercise(item: WorkoutTemplateExercise, index: number): WorkoutTemplateExercise {
    const nextItem = {
      ...item,
      unilateral: item.unilateral ?? false,
      left_reps: item.left_reps ?? item.reps,
      right_reps: item.right_reps ?? item.reps,
      set_modifiers: EMPTY_SET_MODIFIERS,
      expanded: index === 0,
    };
    return { ...nextItem, set_rows: item.set_rows?.length ? item.set_rows : activeExerciseRows(nextItem) };
  }

  function startTemplate(template: WorkoutTemplate) {
    setActiveWorkout({
      mode: "template",
      title: template.name,
      templateId: template.id,
      exercises: template.exercises.map(hydrateActiveExercise),
      startedAt: new Date().toISOString(),
    });
    setWorkoutNow(Date.now());
    setStatus("idle");
  }

  function startCustomWorkout() {
    const nextExercise = exercise.trim() || selectedExercise?.name || exerciseQuery.trim();
    if (!nextExercise) {
      return;
    }
    setActiveWorkout({
      mode: "custom",
      title: "Custom workout",
      exercises: [nextActiveExercise(nextExercise)],
      startedAt: new Date().toISOString(),
    });
    setWorkoutNow(Date.now());
    setStatus("idle");
  }

  async function finishWorkout() {
    if (!activeWorkout) {
      return;
    }
    const endedAt = new Date().toISOString();
    const snapshot: CompletedWorkoutSnapshot = {
      id: `${activeWorkout.startedAt}-${endedAt}`,
      title: activeWorkout.title,
      mode: activeWorkout.mode,
      startedAt: activeWorkout.startedAt,
      endedAt,
      duration_seconds: Math.max(0, Math.floor((Date.parse(endedAt) - Date.parse(activeWorkout.startedAt)) / 1000)),
      exercises: activeWorkout.exercises,
    };
    if (activeWorkout.exercises.some((item) => activeExerciseRows(item).some((row) => row.completed))) {
      setCompletedWorkouts((current) => [snapshot, ...current].slice(0, 20));
      setSelectedCompletedWorkoutId(snapshot.id);
    }
    setActiveWorkout(null);
    setStatus("saved");
  }

  function templateExercisesFromCurrentState() {
    if (templateBuilderExercises.length) {
      return templateBuilderExercises.map(templateExercisePayload);
    }
    if (activeWorkout?.exercises.length) {
      return activeWorkout.exercises.map(templateExercisePayload);
    }
    const nextExercise = exercise.trim() || selectedExercise?.name || exerciseQuery.trim();
    if (!nextExercise) {
      return [];
    }
    return [{
      exercise: nextExercise,
      sets: 3,
      reps: currentTargetReps(),
      target_weight_kg: parseLoadInput(weightKg),
      rest_seconds: 90,
    }];
  }

  function templateExercisePayload(item: WorkoutTemplateExercise) {
    return {
      exercise: item.exercise,
      sets: item.sets,
      reps: item.reps || activeExerciseRows(item)[0]?.reps || 8,
      target_weight_kg: item.target_weight_kg || activeExerciseRows(item)[0]?.weight_kg || 0,
      rest_seconds: item.rest_seconds,
    };
  }

  async function refreshTemplates() {
    const templates = await getJson<WorkoutTemplate[]>(`/users/${userId}/workout-templates`);
    onDashboardPatch({ templates });
    return templates;
  }

  function editTemplate(template: WorkoutTemplate) {
    setEditingTemplateId(template.id);
    setTemplateDraft({
      name: template.name,
      focus: template.focus,
      estimated_minutes: String(template.estimated_minutes),
    });
    setTemplateBuilderExercises(template.exercises.map(hydrateActiveExercise));
    setTemplateBuilderOpen(true);
  }

  async function saveTemplateDraft() {
    const exercises = templateExercisesFromCurrentState();
    const nextName = templateDraft.name.trim() || activeWorkout?.title || "Workout template";
    if (!exercises.length) {
      setStatus("error");
      return;
    }
    setStatus("saving");
    try {
      const response = await fetch(`${API_URL}/users/${userId}/workout-templates${editingTemplateId ? `/${editingTemplateId}` : ""}`, {
        method: editingTemplateId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: nextName,
          focus: templateDraft.focus.trim() || "Hypertrophy",
          exercises,
          estimated_minutes: Number(templateDraft.estimated_minutes) || 60,
        }),
      });
      if (!response.ok) {
        throw new Error("Workout template save failed");
      }
      await refreshTemplates();
      setEditingTemplateId(null);
      setTemplateBuilderExercises([]);
      setTemplateBuilderOpen(false);
      setTemplateDraft({ name: "", focus: "Hypertrophy", estimated_minutes: "60" });
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  async function deleteTemplate(templateId: number) {
    const template = data.templates.find((item) => item.id === templateId);
    if (!window.confirm(`Delete template "${template?.name ?? "this template"}"?`)) {
      return;
    }
    setStatus("saving");
    try {
      const response = await fetch(`${API_URL}/users/${userId}/workout-templates/${templateId}`, { method: "DELETE" });
      if (!response.ok) {
        throw new Error("Workout template delete failed");
      }
      await refreshTemplates();
      if (editingTemplateId === templateId) {
        setEditingTemplateId(null);
        setTemplateBuilderExercises([]);
        setTemplateBuilderOpen(false);
        setTemplateDraft({ name: "", focus: "Hypertrophy", estimated_minutes: "60" });
      }
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  function resumeCompletedWorkout(snapshot: CompletedWorkoutSnapshot) {
    setActiveWorkout({
      mode: snapshot.mode,
      title: `${snapshot.title} copy`,
      exercises: snapshot.exercises.map((item, index) => hydrateActiveExercise({
        ...item,
        set_rows: activeExerciseRows(item).map((row) => ({
          ...row,
          completed: false,
          completed_at: undefined,
          rest_before_seconds: undefined,
        })),
      }, index)),
      startedAt: new Date().toISOString(),
    });
    setWorkoutNow(Date.now());
  }

  function deleteCompletedWorkout(id: string) {
    if (!window.confirm("Delete this completed workout from local history?")) {
      return;
    }
    setCompletedWorkouts((current) => current.filter((item) => item.id !== id));
    if (selectedCompletedWorkoutId === id) {
      setSelectedCompletedWorkoutId(null);
    }
  }

  function renderModifierButtons(
    current: WorkoutSetModifierState | undefined,
    onPatch: (patch: Partial<WorkoutSetModifierState>) => void,
  ) {
    const value = current ?? EMPTY_SET_MODIFIERS;
    return (
      <>
        <button className={value.myo_reps ? "active" : ""} onClick={() => onPatch({ myo_reps: !value.myo_reps })}>Myo-reps</button>
        <button className={value.myo_reps_matching ? "active" : ""} onClick={() => onPatch({ myo_reps_matching: !value.myo_reps_matching })} disabled={!value.myo_reps}>Matching</button>
        <button className={value.drop_set ? "active" : ""} onClick={() => onPatch({ drop_set: !value.drop_set })}>Drop-set</button>
        <button className={value.lengthened_partials ? "active" : ""} onClick={() => onPatch({ lengthened_partials: !value.lengthened_partials })}>Partials</button>
      </>
    );
  }

  return (
    <section className="page-grid">
      <article className="panel">
        <p className="eyebrow">Smart workout notes</p>
        <h3>{hasSelectedProgressionTarget ? `${selectedNextSession?.exercise}: next target` : "Start, log, and finish workouts"}</h3>
        {showTrainingPrinciple && (
          <div className="training-principle-card">
            <div className="training-principle-head">
              <span>Hypertrophy anchor</span>
              <button type="button" onClick={dismissTrainingPrinciple} aria-label="Dismiss hypertrophy anchor">
                <X size={15} />
              </button>
            </div>
            <strong>Progressive overload, 1-3 RIR, clean reps, slow deep stretch.</strong>
            <small>Hypertrophy work is judged by load, reps, effort, and technique. Conditioning, planks, and very low-effort work can still be useful, but they are not counted as the main growth driver.</small>
          </div>
        )}
        {activeWorkout && (
          <div className="active-workout">
            <div>
              <span>Active workout</span>
              <strong>{activeWorkout.title}</strong>
              <small>{activeWorkoutSets} sets - {activeWorkoutVolume.toLocaleString()} kg planned volume</small>
            </div>
            <div className="workout-elapsed">
              <span>Total time</span>
              <strong>{formatDuration(activeWorkoutElapsedSeconds)}</strong>
            </div>
            <div className="rest-control-panel">
              <div className="rest-mode-control" aria-label="Rest timer mode">
                <button className={restTimerMode === "exercise" ? "active" : ""} onClick={() => setRestTimerMode("exercise")}>By exercise</button>
                <button className={restTimerMode === "global" ? "active" : ""} onClick={() => setRestTimerMode("global")}>Global</button>
              </div>
              {restTimerMode === "global" && (
                <label className="rest-global-input">
                  <span>sec</span>
                  <input
                    type="number"
                    min="15"
                    max="600"
                    step="15"
                    value={globalRestSeconds}
                    onChange={(event) => setGlobalRestSeconds(Number(event.target.value))}
                  />
                </label>
              )}
            </div>
            <div className={`rest-timer ${restTimerActive ? "active" : "off"}`}>
              <span>{restTimerMode === "global" ? "Global rest" : "Exercise rest"}</span>
              <strong>{restTimerActive ? `${Math.floor(restSeconds / 60)}:${String(restSeconds % 60).padStart(2, "0")}` : "Off"}</strong>
              <button onClick={() => (restTimerActive ? setRestTimerActive(false) : startRest(restTimerMode === "global" ? globalRestSeconds : restSeconds))}>
                {restTimerActive ? "Pause" : "Start"}
              </button>
            </div>
            <button className="primary-action" onClick={finishWorkout} disabled={status === "saving"}>
              <CheckCircle2 size={17} /> Finish workout
            </button>
            <button className="secondary-action cancel-workout-button" onClick={cancelActiveWorkout} disabled={status === "saving"}>
              <X size={16} /> Cancel workout
            </button>
          </div>
        )}
        {activeWorkout && (
          <div className="active-exercise-list">
            {activeWorkout.exercises.map((item, index) => (
              <details
                className={`active-exercise-card ${draggedActiveExerciseIndex === index ? "dragging" : ""}`}
                key={`${activeWorkout.startedAt}-${item.exercise}-${index}`}
                open={item.expanded ?? index === 0}
                onToggle={(event) => updateActiveExercise(index, { expanded: event.currentTarget.open })}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  reorderActiveExercise(draggedActiveExerciseIndex, index);
                }}
              >
                <summary className="active-exercise-summary">
                  <div>
                    <span
                      className="drag-handle"
                      draggable
                      onClick={(event) => event.preventDefault()}
                      onDragStart={(event) => {
                        event.dataTransfer.effectAllowed = "move";
                        setDraggedActiveExerciseIndex(index);
                      }}
                      onDragEnd={() => setDraggedActiveExerciseIndex(null)}
                      title="Drag to reorder exercise"
                    >
                      <GripVertical size={14} /> Exercise {index + 1}
                    </span>
                    <strong>{item.exercise}</strong>
                  </div>
                  <small>
                    {activeExerciseRows(item).filter((row) => row.completed).length}/{activeExerciseRows(item).length} sets logged
                  </small>
                </summary>
                <div className="active-set-card-body">
                  <div className="active-exercise-controls">
                    <label>Rest period, sec
                      <input
                        type="number"
                        min="15"
                        max="600"
                        step="15"
                        value={item.rest_seconds}
                        onChange={(event) => updateActiveExercise(index, { rest_seconds: Number(event.target.value) })}
                      />
                    </label>
                    <label className="active-unilateral-toggle">
                      <span>Unilateral</span>
                      <input
                        type="checkbox"
                        checked={Boolean(item.unilateral)}
                        onChange={(event) => updateActiveExerciseUnilateral(index, event.target.checked)}
                      />
                    </label>
                  </div>
                  <div className="active-set-row-list">
                    {activeExerciseRows(item).map((row, rowIndex) => {
                      const dynamicPrediction = predictSetTarget(item, activeExerciseRows(item), rowIndex);
                      const predicted = row.completed && row.target_reps
                        ? {
                          weight: row.target_weight_kg ?? row.weight_kg,
                          reps: row.target_reps,
                          repsMin: row.target_reps_min ?? row.target_reps,
                          repsMax: row.target_reps_max ?? row.target_reps,
                          kind: row.target_kind ?? "working",
                          reason: row.prediction_reason ?? "Predicted from personal workout history.",
                        }
                        : dynamicPrediction;
                      const aimLabel = predicted.repsMin === predicted.repsMax
                        ? `${predicted.reps} reps`
                        : `${predicted.repsMin}-${predicted.repsMax} reps`;
                      return (
                        <div className={`active-set-row ${row.completed ? "completed" : ""}`} key={row.id}>
                          <span>{row.set_number}</span>
                          <div className="set-modifier-badges">
                            {modifierBadges(row.modifiers).map((tag) => <i key={tag}>{tag}</i>)}
                          </div>
                          <input
                            type="text"
                            inputMode="decimal"
                            value={row.weight_kg}
                            onChange={(event) => updateActiveSetRow(index, rowIndex, { weight_kg: parseLoadInput(event.target.value) })}
                            aria-label={`${item.exercise} set ${row.set_number} weight`}
                          />
                          <b>x</b>
                          {item.unilateral ? (
                            <div className="unilateral-rep-grid compact">
                              <input
                                type="number"
                                min="1"
                                max="100"
                                value={row.left_reps || ""}
                                placeholder={String(predicted.reps)}
                                onChange={(event) => updateActiveSetRow(index, rowIndex, { left_reps: Number(event.target.value), reps: Math.max(Number(event.target.value), row.right_reps || row.reps || 0) })}
                                aria-label={`${item.exercise} set ${row.set_number} left reps`}
                              />
                              <input
                                type="number"
                                min="1"
                                max="100"
                                value={row.right_reps || ""}
                                placeholder={String(predicted.reps)}
                                onChange={(event) => updateActiveSetRow(index, rowIndex, { right_reps: Number(event.target.value), reps: Math.max(row.left_reps || row.reps || 0, Number(event.target.value)) })}
                                aria-label={`${item.exercise} set ${row.set_number} right reps`}
                              />
                            </div>
                          ) : (
                            <input
                              type="number"
                              min="1"
                              max="100"
                              value={row.reps || ""}
                              placeholder={String(predicted.reps)}
                              onChange={(event) => updateActiveSetRow(index, rowIndex, { reps: Number(event.target.value), left_reps: Number(event.target.value), right_reps: Number(event.target.value) })}
                              aria-label={`${item.exercise} set ${row.set_number} reps`}
                            />
                          )}
                          <div className="set-aim-chip" title={predicted.reason}>
                            <span>{row.completed ? "Logged" : predicted.kind === "warmup" ? "Warm-up" : predicted.kind === "top" ? "Top set" : "Aim"}</span>
                            <strong>{predicted.weight} kg x {aimLabel}</strong>
                          </div>
                          <small>{row.completed ? `Rest ${formatDuration(row.rest_before_seconds ?? 0)}` : "Not logged"}</small>
                          <button onClick={() => logActiveSetRow(item, index, rowIndex)} disabled={status === "saving" || row.completed || (!row.reps && !row.left_reps && !row.right_reps)}>
                            {row.completed ? "Done" : "Log"}
                          </button>
                          <details className="set-modifier-menu row-modifier-menu">
                            <summary>Set</summary>
                            <div className="active-set-modifiers">
                              {renderModifierButtons(row.modifiers, (patch) => updateActiveSetModifiers(index, rowIndex, patch))}
                            </div>
                          </details>
                        </div>
                      );
                    })}
                  </div>
                  <div className="active-set-actions">
                    <button className="danger-mini" onClick={() => removeSetRow(index)}>Remove Set</button>
                    <button onClick={() => startRest(restTimerMode === "global" ? globalRestSeconds : item.rest_seconds)}>
                      Rest {restTimerMode === "global" ? `${globalRestSeconds}s` : `${item.rest_seconds}s`}
                    </button>
                    <button className="primary-action" onClick={() => addSetRow(index)}>Add Set</button>
                    <button className="danger-mini" onClick={() => removeActiveExercise(index)}>Remove exercise</button>
                  </div>
                </div>
              </details>
            ))}
          </div>
        )}
        {hasSelectedProgressionTarget && selectedNextSession && (
          <div className="score-card">
            <span>{selectedNextSession.reason ?? "Log workouts to receive progression targets."}</span>
            <strong>{selectedNextSession.target_weight_kg > 0 ? `${selectedNextSession.target_weight_kg} kg` : `${selectedNextSession.target_reps} reps`}</strong>
          </div>
        )}
        <div className="form-grid compact-form">
          <label className="wide-field exercise-search-field">Exercise
            <div className="exercise-search-input-row">
              <input value={exerciseQuery} onChange={(event) => setExerciseQuery(event.target.value)} placeholder="Search or create an exercise" />
              {(exerciseQuery.trim() || selectedExerciseSlug) && (
                <button type="button" className="exercise-clear-button" onClick={() => clearExerciseSelection()} aria-label="Clear exercise selection">
                  <X size={16} />
                </button>
              )}
            </div>
            <div className="exercise-library-meta">
              <span>{filteredExercises.length} shown from {matchingExercises.length} matches and {data.exercises.length} exercises</span>
                <button type="button" onClick={() => {
                  clearExerciseSelection(true);
                }}>
                  Reset filters
                </button>
            </div>
            <div className="exercise-chip-row">
              {exerciseQuickFilters.map((item) => (
                <button
                  type="button"
                  className={exerciseQuickFilter === item ? "active" : ""}
                  key={item}
                  onClick={() => setExerciseQuickFilter(item)}
                >
                  {item}
                </button>
              ))}
            </div>
            <div className="exercise-filter-row">
              <select value={exerciseMuscleFilter} onChange={(event) => setExerciseMuscleFilter(event.target.value)}>
                {exerciseMuscles.map((item) => <option key={item} value={item}>{item === "All" ? "All muscles" : item}</option>)}
              </select>
              <select value={exerciseDifficultyFilter} onChange={(event) => setExerciseDifficultyFilter(event.target.value)}>
                {exerciseDifficulties.map((item) => <option key={item} value={item}>{item === "All" ? "All levels" : item}</option>)}
              </select>
            </div>
            <div className="exercise-search-results">
              {filteredExercises.map((item) => (
                <button type="button" className={item.slug === selectedExerciseSlug ? "active" : ""} key={item.slug} onClick={() => chooseExercise(item.slug)}>
                  <span>{item.name}</span>
                  <small>{item.muscle_group} - {item.difficulty}</small>
                </button>
              ))}
              {showCustomExerciseBuilder && (
                <button type="button" onClick={createCustomExercise} disabled={status === "saving"}>
                  <span>Create "{customExerciseDraft.name.trim()}"</span>
                  <small>Custom exercise with manual anatomy setup</small>
                </button>
              )}
            </div>
            {showCustomExerciseBuilder && (
              <div className="custom-exercise-builder">
                <div className="custom-exercise-head">
                  <div>
                    <span>Custom exercise builder</span>
                    <strong>{customExerciseDraft.name.trim()}</strong>
                  </div>
                  <button
                    type="button"
                    className="secondary-action"
                    onClick={() => setCustomExerciseDraft(nextCustomExerciseDefaults(exerciseQuery.trim()))}
                  >
                    <Target size={15} /> Reset draft
                  </button>
                </div>
                <div className="exercise-filter-row">
                  <select
                    value={customExerciseDraft.muscle_group}
                    onChange={(event) => {
                      const nextGroup = event.target.value;
                      setCustomExerciseDraft((current) => ({
                        ...current,
                        muscle_group: nextGroup,
                        allow_empty_primary:
                          current.allow_empty_primary || nextGroup === "Conditioning" || ["Conditioning", "Cardio", "Recovery"].includes(current.category),
                      }));
                    }}
                  >
                    {exerciseMuscles.filter((item) => item !== "All").map((item) => <option key={item} value={item}>{item}</option>)}
                    <option value="Conditioning">Conditioning</option>
                  </select>
                  <select
                    value={customExerciseDraft.category}
                    onChange={(event) => {
                      const nextCategory = event.target.value;
                      setCustomExerciseDraft((current) => ({
                        ...current,
                        category: nextCategory,
                        allow_empty_primary:
                          current.allow_empty_primary || current.muscle_group === "Conditioning" || ["Conditioning", "Cardio", "Recovery"].includes(nextCategory),
                      }));
                    }}
                  >
                    {exerciseCategories.filter((item) => item !== "All").map((item) => <option key={item} value={item}>{item}</option>)}
                    <option value="Custom">Custom</option>
                    <option value="Cardio">Cardio</option>
                    <option value="Conditioning">Conditioning</option>
                  </select>
                  <select
                    value={customExerciseDraft.difficulty}
                    onChange={(event) => setCustomExerciseDraft((current) => ({ ...current, difficulty: event.target.value }))}
                  >
                    {exerciseDifficulties.filter((item) => item !== "All").map((item) => <option key={item} value={item}>{item}</option>)}
                    <option value="Custom">Custom</option>
                  </select>
                </div>
                <label className="modifier-toggle custom-exercise-toggle">
                  <input
                    type="checkbox"
                    checked={customAllowsEmptyPrimary}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setCustomExerciseDraft((current) => ({
                        ...current,
                        allow_empty_primary: checked,
                        primary_muscles: checked ? [] : current.primary_muscles,
                        secondary_muscles: checked ? [] : current.secondary_muscles,
                      }));
                    }}
                    disabled={!["Conditioning", "Cardio", "Recovery"].includes(customExerciseDraft.category) && customExerciseDraft.muscle_group !== "Conditioning"}
                  />
                  Allow no primary focus for conditioning/cardio style work
                </label>
                <div className="custom-exercise-anatomy-grid">
                  <div className="custom-exercise-anatomy-panel">
                    <strong>Primary muscles</strong>
                    <small>Choose the main focus. Isolation work can skip secondary.</small>
                    {anatomyCatalog.map((group) => (
                      <div key={`primary-${group.group}`} className="anatomy-chip-group">
                        <span>{group.group}</span>
                        <div className="anatomy-chip-row">
                          {group.regions.map((region) => (
                            <button
                              type="button"
                              key={`primary-${region.id}`}
                              className={customExerciseDraft.primary_muscles.includes(region.id) ? "active" : ""}
                              onClick={() => toggleCustomRegion("primary_muscles", region.id)}
                              disabled={customAllowsEmptyPrimary}
                            >
                              {region.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="custom-exercise-anatomy-panel">
                    <strong>Secondary muscles</strong>
                    <small>Optional. Leave empty when the movement is truly isolated.</small>
                    {anatomyCatalog.map((group) => (
                      <div key={`secondary-${group.group}`} className="anatomy-chip-group">
                        <span>{group.group}</span>
                        <div className="anatomy-chip-row">
                          {group.regions.map((region) => (
                            <button
                              type="button"
                              key={`secondary-${region.id}`}
                              className={customExerciseDraft.secondary_muscles.includes(region.id) ? "active" : ""}
                              onClick={() => toggleCustomRegion("secondary_muscles", region.id)}
                              disabled={customAllowsEmptyPrimary}
                            >
                              {region.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="custom-exercise-summary">
                  <span>Primary: {customAllowsEmptyPrimary ? "none" : customExerciseDraft.primary_muscles.length || "group default"}</span>
                  <span>Secondary: {customExerciseDraft.secondary_muscles.length}</span>
                  <button type="button" className="primary-action" onClick={createCustomExercise} disabled={status === "saving"}>
                    <PlusCircle size={16} /> Save custom exercise
                  </button>
                </div>
              </div>
            )}
          </label>
          {!activeWorkout && (
            <div className="wide-field workout-start-panel">
              <div>
                <span>Browse mode</span>
                <strong>{exercise.trim() || selectedExercise?.name || "Select an exercise to start"}</strong>
                <small>Technique, media, and anatomy stay available before logging starts.</small>
              </div>
              <button className="primary-action" onClick={startCustomWorkout} disabled={status === "saving" || !(exercise.trim() || selectedExercise?.name || exerciseQuery.trim())}>
                Start new workout
              </button>
            </div>
          )}
          {activeWorkout && (
            <>
              <div className="wide-field workout-start-panel active">
                <div>
                  <span>Logging mode</span>
                  <strong>{activeWorkout.title}</strong>
                  <small>Add exercises above, then log each set from the workout cards.</small>
                </div>
                <button className="secondary-action" onClick={addExerciseToActiveWorkout}>
                  Add selected exercise
                </button>
              </div>
            </>
          )}
          {status === "saved" && <span className="form-success wide-field">Workout changes saved.</span>}
          {status === "error" && <span className="form-error wide-field">Could not save this change.</span>}
        </div>
      </article>
      <article className="panel">
        <p className="eyebrow">Exercise library</p>
        <h3>{selectedExercise?.name ?? "Select exercise"}</h3>
        {selectedExercise && (
          <>
            {primaryExerciseMedia?.kind === "youtube" ? (
              <div className="exercise-player-frame">
                <iframe
                  className="exercise-player"
                  src={`https://www.youtube-nocookie.com/embed/${primaryExerciseMedia.youtubeId}`}
                  title={`${selectedExercise.name} technique video`}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                  allowFullScreen
                />
              </div>
            ) : primaryExerciseMedia?.kind === "image" ? (
              <div className="exercise-player-frame exercise-photo-frame">
                <div className="exercise-photo-stage">
                  <img
                    className="exercise-gallery-image"
                    src={primaryExerciseMedia.mediaUrl}
                    alt={primaryExerciseMedia.title || `${selectedExercise.name} reference`}
                  />
                </div>
                <div className="exercise-media-overlay">
                  <span>Photo reference</span>
                  <a href={youtubeSearchUrl(selectedExercise.name)} target="_blank" rel="noreferrer">
                    <PlayCircle size={15} /> Find video
                  </a>
                </div>
              </div>
            ) : primaryExerciseMedia?.kind === "video" ? (
              <div className="exercise-player-frame">
                <video className="exercise-gallery-video" src={primaryExerciseMedia.mediaUrl} controls preload="metadata" />
              </div>
            ) : (
              <div className="exercise-youtube-fallback">
                <span>Technique media not reviewed yet</span>
                <strong>{selectedExercise.name}</strong>
                <small>Open a prepared YouTube search while this exercise waits for a reviewed GIF/photo/video source.</small>
                <a className="primary-action" href={youtubeSearchUrl(selectedExercise.name)} target="_blank" rel="noreferrer">
                  Open YouTube technique search
                </a>
              </div>
            )}
            {compactMediaOptions.length > 0 && (
              <div className="exercise-media-gallery">
                {compactMediaOptions.map((item) => (
                  <button
                    type="button"
                    className={`exercise-media-card ${selectedMediaId === item.id ? "active" : ""}`}
                    key={item.id}
                    onClick={() => setSelectedMediaId(item.id)}
                  >
                    {item.thumbnail_url ? (
                      <img className="exercise-media-thumb" src={item.thumbnail_url} alt="" loading="lazy" />
                    ) : (
                      <span className="exercise-media-thumb-placeholder" />
                    )}
                    <strong>{item.title || item.media_type}</strong>
                    <small>{item.source_name || "Exercise media"}</small>
                  </button>
                ))}
              </div>
            )}
            {selectedExerciseIsAlternating && !dismissedAlternateNote && (
              <div className="exercise-coach-note">
                <div>
                  <span>Tracking note</span>
                  <strong>Alternating reps are usually noisier to track than simultaneous or true unilateral work.</strong>
                  <small>Use alternate reps when there is a specific reason. For hypertrophy logging, the unilateral toggle records left and right reps inside one set.</small>
                </div>
                <button type="button" onClick={() => setDismissedAlternateNote(true)} aria-label="Dismiss alternating exercise note">
                  <X size={15} />
                </button>
              </div>
            )}
            <MuscleAnatomy exercise={selectedExercise} />
            <div className="instruction-list">
              {normalizedInstructionSteps(selectedExercise.instructions).map((step, index) => (
                <div key={`${selectedExercise.slug}-step-${index}`}><b>{index + 1}</b><p>{step}</p></div>
              ))}
            </div>
            <div className="cue-cloud">
              {selectedExercise.cues.map((cue) => <span key={cue}>{cue}</span>)}
            </div>
            <div className="mistake-list">
              <strong>Common mistakes</strong>
              {selectedExercise.mistakes.map((mistake) => <span key={mistake}>{mistake}</span>)}
            </div>
            <div className="exercise-detail-actions">
              <button className="primary-action" onClick={addExerciseToActiveWorkout}>
                <Dumbbell size={16} /> Use in workout
              </button>
            </div>
            <details className="source-note">
              <summary>Content source</summary>
              <span>{selectedExercise.source_name || "Local seed"} - {selectedExercise.source_license || "No external license metadata"}</span>
              <small>{selectedExercise.attribution || "Technique notes are stored as project demo content."}</small>
              {selectedExercise.checked_at && <small>Checked: {selectedExercise.checked_at}</small>}
            </details>
            {selectedExerciseIsCustom && (
              <details className="custom-exercise-builder custom-exercise-editor">
                <summary className="custom-exercise-head">
                  <div>
                    <span>Custom exercise editor</span>
                    <strong>{selectedExercise.name}</strong>
                  </div>
                  <span>Edit anatomy</span>
                </summary>
                  <div className="mini-actions">
                    <button type="button" onClick={saveSelectedCustomExercise}>
                      <Pencil size={14} /> Save changes
                    </button>
                    <button type="button" className="danger-mini" onClick={deleteSelectedCustomExercise}>
                      <Trash2 size={14} /> Delete
                    </button>
                  </div>
                <div className="exercise-filter-row">
                  <select
                    value={customExerciseDetailsDraft.muscle_group}
                    onChange={(event) => setCustomExerciseDetailsDraft((current) => ({ ...current, muscle_group: event.target.value }))}
                  >
                    {exerciseMuscles.filter((item) => item !== "All").map((item) => <option key={item} value={item}>{item}</option>)}
                    <option value="Conditioning">Conditioning</option>
                  </select>
                  <select
                    value={customExerciseDetailsDraft.category}
                    onChange={(event) => setCustomExerciseDetailsDraft((current) => ({ ...current, category: event.target.value }))}
                  >
                    {exerciseCategories.filter((item) => item !== "All").map((item) => <option key={item} value={item}>{item}</option>)}
                    <option value="Custom">Custom</option>
                    <option value="Cardio">Cardio</option>
                    <option value="Conditioning">Conditioning</option>
                  </select>
                  <select
                    value={customExerciseDetailsDraft.difficulty}
                    onChange={(event) => setCustomExerciseDetailsDraft((current) => ({ ...current, difficulty: event.target.value }))}
                  >
                    {exerciseDifficulties.filter((item) => item !== "All").map((item) => <option key={item} value={item}>{item}</option>)}
                    <option value="Custom">Custom</option>
                  </select>
                </div>
                <label className="modifier-toggle custom-exercise-toggle">
                  <input
                    type="checkbox"
                    checked={customExerciseDetailsDraft.allow_empty_primary}
                    onChange={(event) => setCustomExerciseDetailsDraft((current) => ({
                      ...current,
                      allow_empty_primary: event.target.checked,
                      primary_muscles: event.target.checked ? [] : current.primary_muscles,
                      secondary_muscles: event.target.checked ? [] : current.secondary_muscles,
                    }))}
                  />
                  Allow no primary focus
                </label>
                <div className="custom-exercise-anatomy-grid">
                  <div className="custom-exercise-anatomy-panel">
                    <strong>Primary muscles</strong>
                    <small>Main focus for the exercise.</small>
                    {anatomyCatalog.map((group) => (
                      <div key={`details-primary-${group.group}`} className="anatomy-chip-group">
                        <span>{group.group}</span>
                        <div className="anatomy-chip-row">
                          {group.regions.map((region) => (
                            <button
                              type="button"
                              key={`details-primary-${region.id}`}
                              className={customExerciseDetailsDraft.primary_muscles.includes(region.id) ? "active" : ""}
                              onClick={() => toggleExerciseDetailsRegion("primary_muscles", region.id)}
                              disabled={customExerciseDetailsDraft.allow_empty_primary}
                            >
                              {region.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="custom-exercise-anatomy-panel">
                    <strong>Secondary muscles</strong>
                    <small>Optional support muscles.</small>
                    {anatomyCatalog.map((group) => (
                      <div key={`details-secondary-${group.group}`} className="anatomy-chip-group">
                        <span>{group.group}</span>
                        <div className="anatomy-chip-row">
                          {group.regions.map((region) => (
                            <button
                              type="button"
                              key={`details-secondary-${region.id}`}
                              className={customExerciseDetailsDraft.secondary_muscles.includes(region.id) ? "active" : ""}
                              onClick={() => toggleExerciseDetailsRegion("secondary_muscles", region.id)}
                              disabled={customExerciseDetailsDraft.allow_empty_primary}
                            >
                              {region.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </details>
            )}
          </>
        )}
        <div className="smart-ai-inline-panel">
          <p className="eyebrow">AI recommendations</p>
          <h4>Next useful action</h4>
          <div className="recommendation-stack compact">
            <div>
              <Sparkles size={16} />
              <span>{data.nextSession?.reason ?? "Log one working set to unlock a progression target for the selected exercise."}</span>
            </div>
            <div>
              <Clock size={16} />
              <span>{data.gamification?.next_action ?? "Pick a lower-traffic training window before starting the session."}</span>
            </div>
          </div>
        </div>
      </article>
      <article className="panel wide-panel workout-workspace-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Training workspace</p>
            <h3>Workout templates</h3>
            <small>Reusable workouts live here. History and progress are kept in Profile.</small>
          </div>
        </div>
        {workoutWorkspaceView === "history" && (
          <div className="workspace-section completed-workouts-panel">
            <p className="eyebrow">Completed workouts</p>
            <h3>{selectedCompletedWorkout ? selectedCompletedWorkout.title : "Workout history"}</h3>
            {completedWorkouts.length === 0 ? (
              <div className="empty-chart">Finish an active workout to save the full session timeline here.</div>
            ) : (
              <div className="completed-workout-layout">
                <div className="completed-workout-list">
                  {completedWorkouts.map((workout) => (
                    <button
                      type="button"
                      className={selectedCompletedWorkout?.id === workout.id ? "active" : ""}
                      key={workout.id}
                      onClick={() => setSelectedCompletedWorkoutId(workout.id)}
                    >
                      <span>{formatForecastSlot(workout.startedAt)}</span>
                      <strong>{workout.title}</strong>
                      <small>{formatDuration(workout.duration_seconds)} - {workout.exercises.reduce((sum, item) => sum + activeExerciseRows(item).filter((row) => row.completed).length, 0)} logged sets</small>
                    </button>
                  ))}
                </div>
                {selectedCompletedWorkout && (
                  <div className="completed-workout-detail">
                    <div className="completed-workout-head">
                      <div>
                        <span>{formatForecastSlot(selectedCompletedWorkout.startedAt)}</span>
                        <strong>{formatDuration(selectedCompletedWorkout.duration_seconds)} total</strong>
                      </div>
                      <div className="mini-actions">
                        <button onClick={() => resumeCompletedWorkout(selectedCompletedWorkout)}>Edit copy</button>
                        <button className="danger-mini" onClick={() => deleteCompletedWorkout(selectedCompletedWorkout.id)}>Delete</button>
                      </div>
                    </div>
                    {selectedCompletedWorkout.exercises.map((item) => (
                      <details className="completed-exercise-card" key={`${selectedCompletedWorkout.id}-${item.exercise}`}>
                        <summary>
                          <strong>{item.exercise}</strong>
                          <small>{activeExerciseRows(item).filter((row) => row.completed).length} sets</small>
                        </summary>
                        <div className="completed-set-list">
                          {activeExerciseRows(item).map((row) => (
                            <div key={row.id}>
                              <span>{row.set_number}</span>
                              <strong>{row.weight_kg} kg x {item.unilateral ? `${row.left_reps || row.reps}/${row.right_reps || row.reps}` : row.reps}</strong>
                              <div className="set-modifier-badges">
                                {modifierBadges(row.modifiers).map((tag) => <i key={tag}>{tag}</i>)}
                              </div>
                              <small>Rest before: {formatDuration(row.rest_before_seconds ?? 0)}</small>
                            </div>
                          ))}
                        </div>
                      </details>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        {workoutWorkspaceView === "templates" && (
          <div className="workspace-section">
            <p className="eyebrow">Saved workout templates</p>
            <h3>Build reusable workouts</h3>
            {!templateBuilderOpen ? (
              <button className="primary-action" onClick={() => setTemplateBuilderOpen(true)}>
                <PlusCircle size={16} /> Create workout template
              </button>
            ) : (
              <div className="template-builder template-create-panel">
                <div>
                  <label>Name<input value={templateDraft.name} onChange={(event) => setTemplateDraft((current) => ({ ...current, name: event.target.value }))} placeholder={activeWorkout?.title ?? "Upper 2"} /></label>
                  <label>Focus<input value={templateDraft.focus} onChange={(event) => setTemplateDraft((current) => ({ ...current, focus: event.target.value }))} /></label>
                  <label>Minutes<input type="number" min="10" max="240" value={templateDraft.estimated_minutes} onChange={(event) => setTemplateDraft((current) => ({ ...current, estimated_minutes: event.target.value }))} /></label>
                </div>
                <div className="template-builder-list">
                  {templateBuilderExercises.map((item, index) => (
                    <div
                      className={`template-builder-row ${draggedTemplateExerciseIndex === index ? "dragging" : ""}`}
                      key={`${item.exercise}-${index}`}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event) => {
                        event.preventDefault();
                        reorderTemplateBuilderExercise(draggedTemplateExerciseIndex, index);
                      }}
                    >
                      <span
                        className="drag-handle"
                        draggable
                        onDragStart={(event) => {
                          event.dataTransfer.effectAllowed = "move";
                          setDraggedTemplateExerciseIndex(index);
                        }}
                        onDragEnd={() => setDraggedTemplateExerciseIndex(null)}
                        title="Drag to reorder exercise"
                      >
                        <GripVertical size={16} />
                      </span>
                      <strong>{item.exercise}</strong>
                      <small>{item.sets}x{item.reps} at {item.target_weight_kg} kg</small>
                      <button className="danger-mini" onClick={() => removeTemplateBuilderExercise(index)}>Remove</button>
                    </div>
                  ))}
                  {!templateBuilderExercises.length && <span className="template-builder-empty">Select an exercise above and add it here.</span>}
                </div>
                <div className="template-builder-actions">
                  <button className="secondary-action" onClick={addSelectedExerciseToTemplateBuilder} disabled={!(exercise.trim() || selectedExercise?.name || exerciseQuery.trim())}>
                    <PlusCircle size={16} /> Add selected exercise
                  </button>
                  <button className="primary-action" onClick={saveTemplateDraft} disabled={status === "saving" || !templateBuilderExercises.length}>
                    <PlusCircle size={16} /> {editingTemplateId ? "Save template changes" : "Save workout"}
                  </button>
                  <button
                    className="secondary-action"
                    onClick={() => {
                      setEditingTemplateId(null);
                      setTemplateBuilderOpen(false);
                      setTemplateBuilderExercises([]);
                      setTemplateDraft({ name: "", focus: "Hypertrophy", estimated_minutes: "60" });
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
            <div className="template-grid">
              {data.templates.map((template) => (
                <div className="template-card" key={template.id}>
                  <div>
                    <span>{template.focus} - {template.estimated_minutes} min</span>
                    <strong>{template.name}</strong>
                  </div>
                  <ul>
                    {template.exercises.slice(0, 3).map((item) => (
                      <li key={item.exercise}>{item.exercise}: {item.sets}x{item.reps} at {item.target_weight_kg} kg</li>
                    ))}
                  </ul>
                  <div className="template-card-actions">
                    <button className="primary-action" onClick={() => startTemplate(template)}>Start workout</button>
                    <button className="secondary-action" onClick={() => editTemplate(template)}>
                      <Pencil size={14} /> Edit
                    </button>
                    <button className="danger-mini" onClick={() => deleteTemplate(template.id)} disabled={status === "saving"}>
                      <Trash2 size={14} /> Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {workoutWorkspaceView === "progress" && (
          <div className="workspace-section">
            <p className="eyebrow">Progress</p>
            <h3>{data.progress?.total_sets ?? 0} logged sets</h3>
            <div className="segmented-control">
              <button className={!selectedHistoryExercise ? "active" : ""} onClick={() => setSelectedHistoryExercise(null)}>All</button>
              {progressExercises.map((item) => (
                <button
                  className={selectedHistoryExercise === item.exercise ? "active" : ""}
                  key={item.exercise}
                  onClick={() => setSelectedHistoryExercise(item.exercise)}
                >
                  {item.exercise}
                </button>
              ))}
            </div>
            <table>
              <thead>
                <tr><th>Exercise</th><th>Sets</th><th>Best</th><th>Volume</th></tr>
              </thead>
              <tbody>
                {filteredProgressExercises.map((exercise) => (
                  <tr key={exercise.exercise}>
                    <td>{exercise.exercise}</td>
                    <td>{exercise.sets}</td>
                    <td>{exercise.best_weight_kg} kg</td>
                    <td>{exercise.total_volume_kg} kg</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="workout-history-list">
              {historyRows.slice(0, 6).map((workout) => (
                <button className="history-card" key={workout.id} onClick={() => setSelectedHistoryExercise(workout.exercise)}>
                  <span>{formatForecastSlot(workout.performed_at)}</span>
                  <strong>{workout.exercise}</strong>
                  <small>
                    {workout.weight_kg} kg x {workout.reps} - set {workout.set_index}
                    {formatSetModifiers(workout.modifiers) ? ` - ${formatSetModifiers(workout.modifiers)}` : ""}
                  </small>
                </button>
              ))}
            </div>
          </div>
        )}
        {workoutWorkspaceView === "ai" && (
          <div className="workspace-section ai-recommendations-panel">
            <p className="eyebrow">AI recommendations</p>
            <h3>Next useful action</h3>
            <div className="recommendation-stack">
              <div>
                <Sparkles size={16} />
                <span>{data.nextSession?.reason ?? "Log one working set to unlock a progression target."}</span>
              </div>
              <div>
                <Clock size={16} />
                <span>{data.gamification?.next_action ?? "Pick a lower-traffic slot before starting the session."}</span>
              </div>
            </div>
          </div>
        )}
      </article>
    </section>
  );
}
