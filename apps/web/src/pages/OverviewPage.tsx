import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BookOpen,
  Bot,
  Building2,
  CalendarClock,
  CheckCircle2,
  Clock,
  Dumbbell,
  Megaphone,
  MoreHorizontal,
  Pin,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
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
  View,
  WorkoutSet,
  WorkoutTemplate,
  WorkoutTemplateExercise,
} from "../types";

export function OverviewPage({
  data,
  user,
  selectedGym,
  selectedGymId,
  isForecastLoading,
  setSelectedGymId,
  setActiveView,
}: {
  data: DashboardData;
  user: AuthUser;
  selectedGym?: Gym;
  selectedGymId: string;
  isForecastLoading: boolean;
  setSelectedGymId: (value: string) => void;
  setActiveView: (value: View) => void;
}) {
  const bestSlot = data.futureSlots[0];
  const todayPlan = data.trainingPlan?.sessions[0];
  const selectedGymLabel = selectedGym ? `${selectedGym.city}, ${selectedGym.address}` : "Львів, Стрийська";
  const nextWorkout = data.scheduledWorkouts.find((workout) => workout.status === "planned");

  return (
    <section className="member-app-shell overview-home">
        <div className="member-header-row">
          <div>
            <h3>Hello, {user.display_name.split(" ")[0] || "Alex"}!</h3>
            <p>Home base for today. Forecast details and weekly planning live in Planner.</p>
          </div>
          <div className="member-meta">
            <span>Current streak</span>
            <strong>{data.gamification?.current_streak_days ?? 0} days</strong>
          </div>
        </div>
        <div className="best-time-banner">
          <Sparkles size={24} />
          <div>
            <strong>
              Best time to train: {bestSlot ? bestSlot.window_label ?? formatTrainingWindow(bestSlot.timestamp) : "open Planner"}
            </strong>
            <span>
              {bestSlot
                ? `${Math.round(bestSlot.expected_people)} people expected. ${bestSlot.reason}`
                : "Generate a future forecast to receive a personalized slot."}
            </span>
          </div>
          <button className="banner-action" onClick={() => setActiveView("planner")}>Open Planner</button>
        </div>
        <div className="member-ai-tip">
          <Clock size={18} />
          <div>
            <strong>Forecast-aware coaching</strong>
            <span>
              Low-traffic sessions are prioritized when they match your preferred days, crowd limit, and training frequency.
            </span>
          </div>
          <button onClick={() => setActiveView("coach")}>Ask AI Coach</button>
        </div>
        <div className="overview-action-grid">
          <button className="overview-action-card" onClick={() => setActiveView("planner")}>
            <CalendarClock size={20} />
            <span>Selected gym</span>
            <strong>{selectedGymLabel}</strong>
            <small>Open the full-day forecast and weekly calendar.</small>
          </button>
          <button className="overview-action-card" onClick={() => setActiveView("planner")}>
            <Sparkles size={20} />
            <span>Best next window</span>
            <strong>{bestSlot ? bestSlot.window_label ?? formatTrainingWindow(bestSlot.timestamp) : "No slot yet"}</strong>
            <small>{bestSlot ? `${Math.round(bestSlot.expected_people)} people expected` : "Planner will load personalized slots."}</small>
          </button>
          <button className="overview-action-card" onClick={() => setActiveView("workouts")}>
            <Dumbbell size={20} />
            <span>Training</span>
            <strong>{nextWorkout?.title ?? todayPlan?.focus ?? "Start workout"}</strong>
            <small>{nextWorkout ? formatTrainingWindow(nextWorkout.scheduled_at) : "Log sets or start from a template."}</small>
          </button>
          <button className="overview-action-card" onClick={() => setActiveView("profile")}>
            <Trophy size={20} />
            <span>Progress</span>
            <strong>{data.progress?.total_sets ?? 0} logged sets</strong>
            <small>History, favorites, performance, and muscle distribution.</small>
          </button>
        </div>
      </section>
  );
}
