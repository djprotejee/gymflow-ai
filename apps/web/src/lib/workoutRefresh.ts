import { getJson } from "./api";
import type {
  Achievement,
  ActivityDashboard,
  DashboardPatch,
  GamificationSummary,
  NextSession,
  ProgressSummary,
} from "../types";

export async function loadWorkoutDashboardPatch(userId: string, exercise: string): Promise<DashboardPatch> {
  const encodedExercise = encodeURIComponent(exercise);
  // Mutations that affect training data should refresh every dependent product surface together.
  const [progress, nextSession, gamification, achievements, activityDashboard] = await Promise.all([
    getJson<ProgressSummary>(`/users/${userId}/progress`),
    getJson<NextSession>(`/users/${userId}/next-session?exercise=${encodedExercise}`),
    getJson<GamificationSummary>(`/users/${userId}/gamification`),
    getJson<Achievement[]>(`/users/${userId}/achievements`),
    getJson<ActivityDashboard>(`/users/${userId}/activity-dashboard`),
  ]);
  return { progress, nextSession, gamification, achievements, activityDashboard };
}
