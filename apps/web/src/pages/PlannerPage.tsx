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
  WorkoutSet,
  WorkoutTemplate,
  WorkoutTemplateExercise,
} from "../types";

function isGymOpenAt(value: string) {
  const date = new Date(value);
  const day = date.getDay();
  const hour = date.getHours();
  const isWeekend = day === 0 || day === 6;
  return isWeekend ? hour >= 9 && hour < 18 : hour >= 7 && hour < 22;
}

function dateKey(value: Date | string) {
  const date = typeof value === "string" ? new Date(value) : value;
  return date.toISOString().slice(0, 10);
}

function startOfWeek(value: Date) {
  const next = new Date(value);
  const day = next.getDay() || 7;
  next.setDate(next.getDate() - day + 1);
  next.setHours(12, 0, 0, 0);
  return next;
}

export function PlannerPage({
  data,
  userId,
  selectedGymId,
  horizonDays,
  isForecastLoading,
  setHorizonDays,
  setSelectedGymId,
  onDashboardPatch,
}: {
  data: DashboardData;
  userId: string;
  selectedGymId: string;
  horizonDays: number;
  isForecastLoading: boolean;
  setHorizonDays: (value: number) => void;
  setSelectedGymId: (value: string) => void;
  onDashboardPatch: (patch: DashboardPatch) => void;
}) {
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [editingScheduledId, setEditingScheduledId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editTime, setEditTime] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [planDraft, setPlanDraft] = useState<Record<string, { focus: string; scheduled_at: string }>>({});
  const [addMenuDate, setAddMenuDate] = useState<string | null>(null);
  const forecastDates = Array.from(new Set(data.futureForecast.map((point) => point.timestamp.slice(0, 10)))).sort();
  const [selectedForecastDate, setSelectedForecastDate] = useState(forecastDates[0] ?? new Date().toISOString().slice(0, 10));
  const effectiveForecastDate = forecastDates.includes(selectedForecastDate) ? selectedForecastDate : forecastDates[0] ?? selectedForecastDate;
  const selectedGym = data.gyms.find((gym) => gym.gym_id === selectedGymId);
  const forecastStart = new Date(`${effectiveForecastDate}T00:00:00`);
  const forecastEnd = new Date(forecastStart);
  forecastEnd.setDate(forecastStart.getDate() + horizonDays);
  const chartForecast = data.futureForecast.filter((point) => {
    const timestamp = new Date(point.timestamp);
    return timestamp >= forecastStart && timestamp < forecastEnd;
  });
  const weekStart = startOfWeek(new Date(effectiveForecastDate || Date.now()));
  const weekDays = Array.from({ length: 7 }).map((_, index) => {
    const day = new Date(weekStart);
    day.setDate(weekStart.getDate() + index);
    return day;
  });
  const scheduledByDate = new Map<string, ScheduledWorkout[]>();
  data.scheduledWorkouts.forEach((workout) => {
    const key = dateKey(workout.scheduled_at);
    scheduledByDate.set(key, [...(scheduledByDate.get(key) ?? []), workout]);
  });

  useEffect(() => {
    if (forecastDates.length && !forecastDates.includes(selectedForecastDate)) {
      setSelectedForecastDate(forecastDates[0]);
    }
  }, [forecastDates.join(","), selectedForecastDate]);

  async function scheduleWeek() {
    setStatus("saving");
    try {
      const sessions = data.trainingPlan?.sessions ?? [];
      for (const session of sessions) {
        const key = `${session.day_index}-${session.scheduled_at}`;
        const draft = planDraft[key] ?? { focus: session.focus, scheduled_at: session.scheduled_at };
        const response = await fetch(`${API_URL}/users/${userId}/scheduled-workouts`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            gym_id: selectedGymId,
            template_id: 0,
            title: draft.focus,
            scheduled_at: draft.scheduled_at,
            expected_people: session.expected_people,
            notes: session.reason,
          }),
        });
        if (!response.ok) {
          throw new Error("Schedule failed");
        }
      }
      const scheduledWorkouts = await getJson<ScheduledWorkout[]>(`/users/${userId}/scheduled-workouts`);
      onDashboardPatch({ scheduledWorkouts });
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  function updatePlanDraft(key: string, patch: Partial<{ focus: string; scheduled_at: string }>, fallback: { focus: string; scheduled_at: string }) {
    setPlanDraft((current) => ({
      ...current,
      [key]: {
        focus: current[key]?.focus ?? fallback.focus,
        scheduled_at: current[key]?.scheduled_at ?? fallback.scheduled_at,
        ...patch,
      },
    }));
  }

  async function markScheduled(workout: ScheduledWorkout, nextStatus: string) {
    const updated = await fetch(`${API_URL}/users/${userId}/scheduled-workouts/${workout.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: nextStatus, notes: workout.notes }),
    });
    if (updated.ok) {
      const scheduledWorkouts = await getJson<ScheduledWorkout[]>(`/users/${userId}/scheduled-workouts`);
      onDashboardPatch({ scheduledWorkouts });
    }
  }

  function startScheduledEdit(workout: ScheduledWorkout) {
    setEditingScheduledId(workout.id);
    setEditTitle(workout.title);
    setEditTime(toDateTimeLocalValue(workout.scheduled_at));
    setEditNotes(workout.notes);
  }

  async function saveScheduledEdit(workout: ScheduledWorkout) {
    const updated = await fetch(`${API_URL}/users/${userId}/scheduled-workouts/${workout.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: workout.status,
        title: editTitle,
        scheduled_at: editTime ? new Date(editTime).toISOString() : workout.scheduled_at,
        expected_people: workout.expected_people,
        notes: editNotes,
      }),
    });
    if (updated.ok) {
      const scheduledWorkouts = await getJson<ScheduledWorkout[]>(`/users/${userId}/scheduled-workouts`);
      onDashboardPatch({ scheduledWorkouts });
      setEditingScheduledId(null);
    }
  }

  async function deleteScheduled(workout: ScheduledWorkout) {
    if (!window.confirm(`Delete scheduled workout "${workout.title}"?`)) {
      return;
    }
    const deleted = await fetch(`${API_URL}/users/${userId}/scheduled-workouts/${workout.id}`, { method: "DELETE" });
    if (deleted.ok) {
      const scheduledWorkouts = await getJson<ScheduledWorkout[]>(`/users/${userId}/scheduled-workouts`);
      onDashboardPatch({ scheduledWorkouts });
    }
  }

  async function createCalendarWorkout(day: Date, template?: WorkoutTemplate) {
    setStatus("saving");
    try {
      const scheduledAt = new Date(day);
      scheduledAt.setHours(day.getDay() === 0 || day.getDay() === 6 ? 10 : 12, 0, 0, 0);
      const dayForecast = data.futureForecast.filter((point) => point.timestamp.startsWith(dateKey(day)) && isGymOpenAt(point.timestamp));
      const bestPoint = [...dayForecast].sort((left, right) => left.prediction - right.prediction)[0];
      if (bestPoint) {
        const bestDate = new Date(bestPoint.timestamp);
        scheduledAt.setHours(bestDate.getHours(), bestDate.getMinutes(), 0, 0);
      }
      const response = await fetch(`${API_URL}/users/${userId}/scheduled-workouts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          gym_id: selectedGymId,
          template_id: template?.id ?? 0,
          title: template?.name ?? "Planned workout",
          scheduled_at: scheduledAt.toISOString(),
          expected_people: bestPoint ? Math.round(bestPoint.prediction) : 0,
          notes: template
            ? `Added from template: ${template.name}. ${template.exercises.length} exercises, about ${template.estimated_minutes} min.`
            : "Blank planned workout added from weekly planner calendar.",
        }),
      });
      if (!response.ok) {
        throw new Error("Calendar workout create failed");
      }
      const scheduledWorkouts = await getJson<ScheduledWorkout[]>(`/users/${userId}/scheduled-workouts`);
      onDashboardPatch({ scheduledWorkouts });
      setAddMenuDate(null);
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  return (
    <section className="page-grid">
      <article className="panel wide-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Planner</p>
            <h3>Full-day forecast</h3>
            <small>{selectedGym ? `${selectedGym.city}, ${selectedGym.address}` : selectedGymId} · closed hours are marked as closed.</small>
          </div>
          <div className="planner-controls">
            <select value={selectedGymId} onChange={(event) => setSelectedGymId(event.target.value)}>
              {data.gyms.map((gym) => (
                <option key={gym.gym_id} value={gym.gym_id}>{gym.city}, {gym.address}</option>
              ))}
            </select>
            <select className="compact-select" value={horizonDays} onChange={(event) => setHorizonDays(Number(event.target.value))}>
              <option value={1}>Today</option>
              <option value={3}>Next 3 days</option>
              <option value={7}>Week</option>
            </select>
            <input
              type="date"
              value={effectiveForecastDate}
              min={forecastDates[0]}
              max={forecastDates[forecastDates.length - 1]}
              onChange={(event) => setSelectedForecastDate(event.target.value)}
            />
          </div>
        </div>
        <div className="chart-frame planner-chart">{isForecastLoading ? <ChartSkeleton /> : <FutureForecastChart data={chartForecast} />}</div>
      </article>
      <article className="panel">
        <p className="eyebrow">Recommended slots</p>
        <h3>Best times that match your preferences</h3>
        <div className="slot-list">
          {isForecastLoading && data.futureSlots.length === 0 && <SkeletonRows count={3} />}
          {data.futureSlots.map((slot) => (
            <div className="slot-card" key={slot.timestamp}>
              <span>{slot.window_label ?? formatTrainingWindow(slot.timestamp)}</span>
              <strong>{Math.round(slot.expected_people)} people</strong>
              <small>{slot.reason}</small>
            </div>
          ))}
        </div>
      </article>
      <article className="panel wide-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Weekly microcycle</p>
            <h3>Monday-Sunday calendar</h3>
            <small>Add or remove planned workouts without leaving the planner.</small>
          </div>
          <button className="primary-action" onClick={scheduleWeek} disabled={status === "saving"}>
            <CalendarClock size={17} /> Schedule week
          </button>
        </div>
        {status === "saved" && <span className="form-success">Plan copied into your scheduled workouts.</span>}
        {status === "error" && <span className="form-error">Could not schedule this plan.</span>}
        <div className="weekly-calendar-grid">
          {weekDays.map((day) => {
            const key = dateKey(day);
            const dayWorkouts = scheduledByDate.get(key) ?? [];
            const dayForecast = data.futureForecast.filter((point) => point.timestamp.startsWith(key) && isGymOpenAt(point.timestamp));
            const bestPoint = [...dayForecast].sort((left, right) => left.prediction - right.prediction)[0];
            return (
              <div className="weekly-calendar-day" key={key}>
                <div className="weekly-calendar-head">
                  <span>{day.toLocaleDateString(undefined, { weekday: "short" })}</span>
                  <strong>{day.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</strong>
                </div>
                <small>{bestPoint ? `${Math.round(bestPoint.prediction)} people · ${formatTrainingWindow(bestPoint.timestamp)}` : "Closed or no forecast"}</small>
                <div className="weekly-calendar-workouts">
                  {dayWorkouts.map((workout) => (
                    <div key={workout.id}>
                      <span>{workout.title}</span>
                      <button type="button" onClick={() => deleteScheduled(workout)} aria-label={`Remove ${workout.title}`}>Remove</button>
                    </div>
                  ))}
                </div>
                <div className="calendar-add-control">
                  <button type="button" onClick={() => setAddMenuDate((current) => current === key ? null : key)}>Add workout</button>
                  {addMenuDate === key && (
                    <div className="calendar-add-menu">
                      <button type="button" onClick={() => createCalendarWorkout(day)}>
                        <strong>Plan blank workout</strong>
                        <span>Pick title and details later</span>
                      </button>
                      {data.templates.slice(0, 4).map((template) => (
                        <button type="button" key={template.id} onClick={() => createCalendarWorkout(day, template)}>
                          <strong>{template.name}</strong>
                          <span>{template.exercises.length} exercises В· {template.estimated_minutes} min</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        <div className="panel-heading compact-heading">
          <div>
            <p className="eyebrow">AI draft</p>
            <h3>Forecast-aware training plan</h3>
          </div>
        </div>
        <div className="plan-list">
          {isForecastLoading && !data.trainingPlan?.sessions?.length && <SkeletonRows count={4} />}
          {(data.trainingPlan?.sessions ?? []).map((session) => (
            <div className="plan-card editable-plan-card" key={`${session.day_index}-${session.scheduled_at}`}>
              <div>
                <span>Session {session.day_index}</span>
                <input
                  value={planDraft[`${session.day_index}-${session.scheduled_at}`]?.focus ?? session.focus}
                  onChange={(event) => updatePlanDraft(
                    `${session.day_index}-${session.scheduled_at}`,
                    { focus: event.target.value },
                    { focus: session.focus, scheduled_at: session.scheduled_at },
                  )}
                />
                <input
                  type="datetime-local"
                  value={toDateTimeLocalValue(planDraft[`${session.day_index}-${session.scheduled_at}`]?.scheduled_at ?? session.scheduled_at)}
                  onChange={(event) => updatePlanDraft(
                    `${session.day_index}-${session.scheduled_at}`,
                    { scheduled_at: new Date(event.target.value).toISOString() },
                    { focus: session.focus, scheduled_at: session.scheduled_at },
                  )}
                />
                <small>{
                  planDraft[`${session.day_index}-${session.scheduled_at}`]?.scheduled_at
                    ? formatTrainingWindow(planDraft[`${session.day_index}-${session.scheduled_at}`].scheduled_at, Math.min(120, session.estimated_minutes))
                    : session.window_label ?? formatTrainingWindow(session.scheduled_at, Math.min(120, session.estimated_minutes))
                } · {session.estimated_minutes} min</small>
              </div>
              <b>{Math.round(session.expected_people)} people</b>
            </div>
          ))}
        </div>
      </article>
      <article className="panel">
        <p className="eyebrow">Scheduled workouts</p>
        <h3>{data.scheduledWorkouts.length} planned sessions</h3>
        <div className="slot-list">
          {data.scheduledWorkouts.slice(0, 8).map((workout) => (
            <div className="slot-card stacked-card" key={workout.id}>
              {editingScheduledId === workout.id ? (
                <div className="scheduled-edit-form">
                  <input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} />
                  <input type="datetime-local" value={editTime} onChange={(event) => setEditTime(event.target.value)} />
                  <input value={editNotes} onChange={(event) => setEditNotes(event.target.value)} />
                  <div className="mini-actions">
                    <button onClick={() => saveScheduledEdit(workout)}>Save</button>
                    <button onClick={() => setEditingScheduledId(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <>
                  <span>{formatTrainingWindow(workout.scheduled_at)} · {workout.gym_id}</span>
                  <strong>{workout.title}</strong>
                  <small>{workout.status} · expected {Math.round(workout.expected_people)} people</small>
                  <div className="mini-actions">
                    <button onClick={() => markScheduled(workout, "completed")}>Done</button>
                    <button onClick={() => markScheduled(workout, "skipped")}>Skip</button>
                    <button onClick={() => startScheduledEdit(workout)}>Edit</button>
                    <button className="danger-mini" onClick={() => deleteScheduled(workout)}>Delete</button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </article>
    </section>
  );
}
