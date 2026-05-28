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
import { API_URL, authHeaders, getJson } from "../lib/api";
import { createChatSession, loadStoredChatSessions, mapChatSessionRecord } from "../lib/chatSessions";
import { formatForecastSlot, formatSlot, formatTrainingWindow, prettyModelName, toDateTimeLocalValue } from "../lib/format";
import type {
  Achievement,
  ActiveWorkout,
  ActivityDashboard,
  AuthUser,
  ChatMessage,
  ChatResponse,
  ChatSession,
  ChatSessionRecord,
  ChatToolActionTrace,
  ChatToolAction,
  ChatCitation,
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

export function CoachPage({
  data,
  userId,
  selectedGymId,
  onDashboardPatch,
}: {
  data: DashboardData;
  userId: string;
  selectedGymId: string;
  onDashboardPatch: (patch: DashboardPatch) => void;
}) {
  const initialChats = useMemo(() => loadStoredChatSessions(userId, data.coachAnswer?.answer), [userId]);
  const [chatSessions, setChatSessions] = useState<ChatSession[]>(initialChats.sessions);
  const [activeChatId, setActiveChatId] = useState(initialChats.activeId);
  const [chatSearch, setChatSearch] = useState("");
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [historySource, setHistorySource] = useState<"api" | "local">("local");
  const [actionTraces, setActionTraces] = useState<ChatToolActionTrace[]>([]);
  const [pendingActionKey, setPendingActionKey] = useState<string | null>(null);
  const [confirmingActionKey, setConfirmingActionKey] = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem(`gymflow-chat-sessions-${userId}`, JSON.stringify({ sessions: chatSessions, activeId: activeChatId }));
  }, [activeChatId, chatSessions, userId]);

  useEffect(() => {
    void getJson<ChatSessionRecord[]>(`/users/${userId}/chat-sessions`)
      .then((records) => {
        if (!records.length) {
          return;
        }
        const sessions = records.map(mapChatSessionRecord);
        setChatSessions(sessions);
        setActiveChatId((current) => (sessions.some((session) => session.id === current) ? current : sessions[0].id));
        setHistorySource("api");
      })
      .catch(() => setHistorySource("local"));
  }, [userId]);

  useEffect(() => {
    void refreshActionTraces();
  }, [userId]);

  const activeChat = chatSessions.find((session) => session.id === activeChatId) ?? chatSessions[0];
  const messages = activeChat?.messages ?? [];
  const proactiveCards = [
    {
      icon: <Clock size={18} />,
      text: "Find a quieter 1-2 hour training window using the occupancy forecast.",
      label: "Find slot",
      prompt: "Find a quieter slot tomorrow for my preferred gym.",
    },
    {
      icon: <Dumbbell size={18} />,
      text: "Predict my next working set and explain the progression target.",
      label: "Next set",
      prompt: "Predict my next working set and explain the progression model.",
    },
  ];
  const quickActions = [
    "Plan my next training week",
    "Explain Barbell Bench Press technique",
    "Find a quieter slot tomorrow",
    "What should I improve next?",
    "Schedule week",
    "Log target set",
  ];
  const visibleSessions = [...chatSessions]
    .filter((session) => session.title.toLowerCase().includes(chatSearch.toLowerCase()))
    .sort((a, b) => Number(b.pinned) - Number(a.pinned) || new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());

  function updateActiveChat(updater: (session: ChatSession) => ChatSession) {
    setChatSessions((current) =>
      current.map((session) => {
        if (session.id !== activeChatId) {
          return session;
        }
        return updater(session);
      }),
    );
  }

  function appendMessage(message: ChatMessage) {
    updateActiveChat((session) => ({
      ...session,
      updatedAt: new Date().toISOString(),
      messages: [...session.messages, message],
    }));
  }

  function appendAssistantMessage(chatId: string, message: ChatMessage) {
    appendMessage(message);
    void persistMessage(chatId, message);
  }

  async function persistMessage(chatId: string, message: ChatMessage) {
    if (historySource !== "api") {
      return;
    }
    try {
      await fetch(`${API_URL}/users/${userId}/chat-sessions/${chatId}/messages`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ role: message.role, text: message.text, actions: message.actions ?? [], citations: message.citations ?? [] }),
      });
    } catch {
      setHistorySource("local");
    }
  }

  async function sendMessage() {
    const trimmed = input.trim();
    if (!trimmed) {
      return;
    }
    setStatus("loading");
    const chatId = activeChat?.id ?? "";
    const userMessage = { role: "user" as const, text: trimmed };
    appendMessage(userMessage);
    void persistMessage(chatId, userMessage);
    setInput("");
    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ user_id: userId, gym_id: selectedGymId, message: trimmed }),
      });
      if (!response.ok) {
        throw new Error("Chat failed");
      }
      const answer = (await response.json()) as ChatResponse;
      const assistantMessage = {
        role: "assistant" as const,
        text: answer.answer,
        actions: answer.actions ?? [],
        citations: answer.citations ?? [],
      };
      appendAssistantMessage(chatId, assistantMessage);
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  }

  async function startNewChat() {
    const title = `Training chat ${new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}`;
    if (historySource === "api") {
      try {
        const response = await fetch(`${API_URL}/users/${userId}/chat-sessions`, {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ title }),
        });
        if (response.ok) {
          const record = (await response.json()) as ChatSessionRecord;
          const nextSession = mapChatSessionRecord(record);
          setChatSessions((current) => [nextSession, ...current]);
          setActiveChatId(nextSession.id);
        }
      } catch {
        setHistorySource("local");
      }
    } else {
      const nextSession = createChatSession(title);
      setChatSessions((current) => [nextSession, ...current]);
      setActiveChatId(nextSession.id);
    }
    setInput("");
    setOpenMenuId(null);
  }

  async function renameChat(sessionId: string) {
    const session = chatSessions.find((item) => item.id === sessionId);
    const nextTitle = window.prompt("Rename chat", session?.title ?? "Training chat")?.trim();
    if (!nextTitle) {
      return;
    }
    if (historySource === "api") {
      await fetch(`${API_URL}/users/${userId}/chat-sessions/${sessionId}`, {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ title: nextTitle }),
      });
    }
    setChatSessions((current) =>
      current.map((item) => (item.id === sessionId ? { ...item, title: nextTitle, updatedAt: new Date().toISOString() } : item)),
    );
    setOpenMenuId(null);
  }

  async function togglePinChat(sessionId: string) {
    const session = chatSessions.find((item) => item.id === sessionId);
    const nextPinned = !session?.pinned;
    if (historySource === "api") {
      await fetch(`${API_URL}/users/${userId}/chat-sessions/${sessionId}`, {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ pinned: nextPinned }),
      });
    }
    setChatSessions((current) =>
      current.map((item) => (item.id === sessionId ? { ...item, pinned: nextPinned, updatedAt: new Date().toISOString() } : item)),
    );
    setOpenMenuId(null);
  }

  async function deleteChat(sessionId: string) {
    if (!window.confirm("Delete this coach chat?")) {
      return;
    }
    if (historySource === "api") {
      await fetch(`${API_URL}/users/${userId}/chat-sessions/${sessionId}`, { method: "DELETE", headers: authHeaders() });
    }
    setChatSessions((current) => {
      const remaining = current.filter((item) => item.id !== sessionId);
      if (remaining.length === 0) {
        const fresh = createChatSession("Training chat");
        setActiveChatId(fresh.id);
        return [fresh];
      }
      if (activeChatId === sessionId) {
        setActiveChatId(remaining[0].id);
      }
      return remaining;
    });
    setOpenMenuId(null);
  }

  async function createActionTrace(action: ChatToolAction) {
    if (historySource !== "api" || !activeChat?.id) {
      return null;
    }
    try {
      const response = await fetch(`${API_URL}/users/${userId}/chat-tool-actions`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ session_id: activeChat.id, action, status: "suggested" }),
      });
      if (!response.ok) {
        return null;
      }
      return (await response.json()) as ChatToolActionTrace;
    } catch {
      return null;
    }
  }

  async function updateActionTrace(trace: ChatToolActionTrace | null, status: string, result: Record<string, unknown>) {
    if (!trace) {
      return;
    }
    try {
      await fetch(`${API_URL}/users/${userId}/chat-tool-actions/${trace.id}`, {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ status, result }),
      });
      void refreshActionTraces();
    } catch {
      // Trace persistence is audit-only, so product actions should not fail because the trace update did.
    }
  }

  async function refreshActionTraces() {
    try {
      const traces = await getJson<ChatToolActionTrace[]>(`/users/${userId}/chat-tool-actions`);
      setActionTraces(traces);
    } catch {
      setActionTraces([]);
    }
  }

  function citationLabel(citation: ChatCitation) {
    const sourceType = citation.source_type.replace(/_/g, " ");
    const score = Number.isFinite(citation.score) ? citation.score.toFixed(2) : "0.00";
    return `${sourceType} - score ${score}`;
  }

  function actionKey(action: ChatToolAction) {
    return `${action.type}:${action.label}:${JSON.stringify(action.payload)}`;
  }

  function needsActionConfirmation(action: ChatToolAction) {
    return action.type === "manager_create_promotion" || action.type === "manager_notification_draft" || action.type.includes("delete");
  }

  function editFrom(index: number) {
    const message = messages[index];
    if (message.role !== "user") {
      return;
    }
    setInput(message.text);
    updateActiveChat((session) => ({ ...session, updatedAt: new Date().toISOString(), messages: session.messages.slice(0, index) }));
  }

  async function scheduleFromChat(action?: ChatToolAction) {
    const trace = action ? await createActionTrace(action) : null;
    setStatus("loading");
    try {
      const actionGymId = typeof action?.payload.gym_id === "string" ? action.payload.gym_id : selectedGymId;
      const response = await fetch(`${API_URL}/users/${userId}/scheduled-workouts/from-plan?gym_id=${actionGymId}`, { method: "POST", headers: authHeaders() });
      if (!response.ok) {
        throw new Error("Schedule failed");
      }
      const scheduledWorkouts = await getJson<ScheduledWorkout[]>(`/users/${userId}/scheduled-workouts`);
      onDashboardPatch({ scheduledWorkouts });
      appendMessage({ role: "assistant", text: "Done. I added the forecast-aware training week to Planner." });
      await updateActionTrace(trace, "executed", { created: true, scheduled_count: scheduledWorkouts.length });
      setStatus("idle");
    } catch {
      await updateActionTrace(trace, "failed", { error: "Schedule failed" });
      setStatus("error");
    }
  }

  async function logTargetSetFromChat(action?: ChatToolAction) {
    const trace = action ? await createActionTrace(action) : null;
    setStatus("loading");
    try {
      const actionExercise = typeof action?.payload.exercise === "string" ? action.payload.exercise : data.nextSession?.exercise ?? "Barbell Bench Press";
      const actionWeight = typeof action?.payload.weight_kg === "number" ? action.payload.weight_kg : null;
      const actionReps = typeof action?.payload.reps === "number" ? action.payload.reps : null;
      const target = actionWeight === null || actionReps === null
        ? await getJson<NextSession>(`/users/${userId}/next-session?exercise=${encodeURIComponent(actionExercise)}`)
        : null;
      const exerciseName = target?.exercise ?? actionExercise;
      const response = await fetch(`${API_URL}/users/${userId}/workouts`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          exercise: exerciseName,
          weight_kg: actionWeight ?? target?.target_weight_kg ?? 60,
          reps: actionReps ?? target?.target_reps ?? 8,
          set_index: typeof action?.payload.set_index === "number" ? action.payload.set_index : 1,
          notes: "Logged from Coach AI",
        }),
      });
      if (!response.ok) {
        throw new Error("Log failed");
      }
      const [progress, nextSession, activityDashboard, gamification, achievements] = await Promise.all([
        getJson<ProgressSummary>(`/users/${userId}/progress`),
        getJson<NextSession>(`/users/${userId}/next-session?exercise=${encodeURIComponent(exerciseName)}`),
        getJson<ActivityDashboard>(`/users/${userId}/activity-dashboard`),
        getJson<GamificationSummary>(`/users/${userId}/gamification`),
        getJson<Achievement[]>(`/users/${userId}/achievements`),
      ]);
      onDashboardPatch({ progress, nextSession, activityDashboard, gamification, achievements });
      appendMessage({ role: "assistant", text: `Done. I logged one target working set for ${exerciseName} and refreshed your next-session target.` });
      await updateActionTrace(trace, "executed", { exercise: exerciseName, total_sets: progress.total_sets });
      setStatus("idle");
    } catch {
      await updateActionTrace(trace, "failed", { error: "Log failed" });
      setStatus("error");
    }
  }

  function stringPayload(action: ChatToolAction | undefined, key: string, fallback = "") {
    const value = action?.payload[key];
    return typeof value === "string" ? value : fallback;
  }

  function numberPayload(action: ChatToolAction | undefined, key: string, fallback = 0) {
    const value = action?.payload[key];
    return typeof value === "number" ? value : fallback;
  }

  async function createTemplateFromChat(action: ChatToolAction) {
    const trace = await createActionTrace(action);
    setStatus("loading");
    try {
      const response = await fetch(`${API_URL}/users/${userId}/workout-templates`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          name: stringPayload(action, "name", "Coach template"),
          focus: stringPayload(action, "focus", "Hypertrophy"),
          exercises: Array.isArray(action.payload.exercises) ? action.payload.exercises : [],
          estimated_minutes: numberPayload(action, "estimated_minutes", 60),
        }),
      });
      if (!response.ok) {
        throw new Error("Template create failed");
      }
      const templates = await getJson<WorkoutTemplate[]>(`/users/${userId}/workout-templates`);
      onDashboardPatch({ templates });
      appendMessage({ role: "assistant", text: "Done. I created the workout template and refreshed your saved templates." });
      await updateActionTrace(trace, "executed", { template_count: templates.length });
      setStatus("idle");
    } catch {
      await updateActionTrace(trace, "failed", { error: "Template create failed" });
      setStatus("error");
    }
  }

  async function updatePreferencesFromChat(action: ChatToolAction) {
    const trace = await createActionTrace(action);
    setStatus("loading");
    try {
      const current = data.preferences;
      const payload = {
        preferred_min_hour: numberPayload(action, "preferred_min_hour", current?.preferred_min_hour ?? 11),
        preferred_max_hour: numberPayload(action, "preferred_max_hour", current?.preferred_max_hour ?? 16),
        max_crowd_people: numberPayload(action, "max_crowd_people", current?.max_crowd_people ?? 45),
        weekly_goal_sessions: current?.weekly_goal_sessions ?? 4,
        preferred_weekdays: current?.preferred_weekdays ?? [0, 2, 4],
        off_peak_bonus_enabled: current?.off_peak_bonus_enabled ?? true,
      };
      const response = await fetch(`${API_URL}/users/${userId}/preferences`, {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error("Preference update failed");
      }
      const [preferences, futureSlots, gamification] = await Promise.all([
        getJson<UserPreference>(`/users/${userId}/preferences`),
        getJson<SlotRecommendation[]>(`/users/${userId}/recommendations/future-slots?gym_id=${selectedGymId}&max_results=5`),
        getJson<GamificationSummary>(`/users/${userId}/gamification`),
      ]);
      onDashboardPatch({ preferences, futureSlots, gamification });
      appendMessage({ role: "assistant", text: "Done. I updated your training preferences and refreshed personalized recommendations." });
      await updateActionTrace(trace, "executed", { preferred_min_hour: preferences.preferred_min_hour, preferred_max_hour: preferences.preferred_max_hour });
      setStatus("idle");
    } catch {
      await updateActionTrace(trace, "failed", { error: "Preference update failed" });
      setStatus("error");
    }
  }

  async function rescheduleWorkoutFromChat(action: ChatToolAction) {
    const trace = await createActionTrace(action);
    setStatus("loading");
    try {
      const scheduledId = numberPayload(action, "scheduled_id", 0);
      const response = await fetch(`${API_URL}/users/${userId}/scheduled-workouts/${scheduledId}`, {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          status: "planned",
          title: stringPayload(action, "title", "Coach planned workout"),
          scheduled_at: stringPayload(action, "scheduled_at"),
          expected_people: numberPayload(action, "expected_people", 0),
          notes: stringPayload(action, "notes", "Rescheduled by Coach AI"),
        }),
      });
      if (!response.ok) {
        throw new Error("Reschedule failed");
      }
      const scheduledWorkouts = await getJson<ScheduledWorkout[]>(`/users/${userId}/scheduled-workouts`);
      onDashboardPatch({ scheduledWorkouts });
      appendMessage({ role: "assistant", text: "Done. I moved the planned workout into a quieter forecast slot." });
      await updateActionTrace(trace, "executed", { scheduled_id: scheduledId });
      setStatus("idle");
    } catch {
      await updateActionTrace(trace, "failed", { error: "Reschedule failed" });
      setStatus("error");
    }
  }

  async function createPromotionFromChat(action: ChatToolAction) {
    const trace = await createActionTrace(action);
    setStatus("loading");
    try {
      const response = await fetch(`${API_URL}/manager/promotions`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          gym_id: stringPayload(action, "gym_id", selectedGymId),
          title: stringPayload(action, "title", "Quiet-hour promotion"),
          starts_at: stringPayload(action, "starts_at"),
          discount_percent: numberPayload(action, "discount_percent", 10),
          expected_people: numberPayload(action, "expected_people", 0),
          notification_copy: stringPayload(action, "notification_copy", "Train in a quieter slot and get a member perk."),
        }),
      });
      if (!response.ok) {
        throw new Error("Promotion create failed");
      }
      const [promotions, notifications] = await Promise.all([
        getJson<Promotion[]>("/manager/promotions"),
        getJson<ManagerNotification[]>("/manager/notifications"),
      ]);
      onDashboardPatch({ promotions, notifications });
      appendMessage({ role: "assistant", text: "Done. I created the manager promotion draft and refreshed notifications." });
      await updateActionTrace(trace, "executed", { promotion_count: promotions.length });
      setStatus("idle");
    } catch {
      await updateActionTrace(trace, "failed", { error: "Promotion create failed" });
      setStatus("error");
    }
  }

  async function createNotificationDraftFromChat(action: ChatToolAction) {
    const trace = await createActionTrace(action);
    setStatus("loading");
    try {
      const response = await fetch(`${API_URL}/manager/promotions`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          gym_id: stringPayload(action, "gym_id", selectedGymId),
          title: stringPayload(action, "title", "Quiet-hour member notification"),
          starts_at: stringPayload(action, "starts_at"),
          discount_percent: numberPayload(action, "discount_percent", 5),
          expected_people: numberPayload(action, "expected_people", 0),
          notification_copy: stringPayload(action, "notification_copy", "Your preferred gym is quiet soon."),
        }),
      });
      if (!response.ok) {
        throw new Error("Notification draft failed");
      }
      const [promotions, notifications] = await Promise.all([
        getJson<Promotion[]>("/manager/promotions"),
        getJson<ManagerNotification[]>("/manager/notifications"),
      ]);
      onDashboardPatch({ promotions, notifications });
      appendMessage({ role: "assistant", text: "Done. I drafted the manager notification and refreshed the notification queue." });
      await updateActionTrace(trace, "executed", { notification_count: notifications.length });
      setStatus("idle");
    } catch {
      await updateActionTrace(trace, "failed", { error: "Notification draft failed" });
      setStatus("error");
    }
  }

  async function addExerciseToTemplateFromChat(action: ChatToolAction) {
    const trace = await createActionTrace(action);
    setStatus("loading");
    try {
      const templateId = numberPayload(action, "template_id", 0);
      const template = data.templates.find((item) => item.id === templateId) ?? data.templates[0];
      const exercisePayload = action.payload.exercise;
      if (!template || typeof exercisePayload !== "object" || exercisePayload === null) {
        throw new Error("Template exercise update failed");
      }
      const nextExercise = exercisePayload as WorkoutTemplateExercise;
      const response = await fetch(`${API_URL}/users/${userId}/workout-templates/${template.id}`, {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          name: template.name,
          focus: template.focus,
          estimated_minutes: template.estimated_minutes,
          exercises: [...template.exercises, nextExercise],
        }),
      });
      if (!response.ok) {
        throw new Error("Template exercise update failed");
      }
      const templates = await getJson<WorkoutTemplate[]>(`/users/${userId}/workout-templates`);
      onDashboardPatch({ templates });
      appendMessage({ role: "assistant", text: `Done. I added ${nextExercise.exercise} to ${template.name}.` });
      await updateActionTrace(trace, "executed", { template_id: template.id, exercise: nextExercise.exercise });
      setStatus("idle");
    } catch {
      await updateActionTrace(trace, "failed", { error: "Template exercise update failed" });
      setStatus("error");
    }
  }

  async function runChatAction(action: ChatToolAction) {
    setPendingActionKey(actionKey(action));
    setConfirmingActionKey(null);
    try {
      if (action.type === "schedule_week") {
        await scheduleFromChat(action);
        return;
      }
      if (action.type === "log_target_set") {
        await logTargetSetFromChat(action);
        return;
      }
      if (action.type === "create_workout_template") {
        await createTemplateFromChat(action);
        return;
      }
      if (action.type === "add_exercise_to_template") {
        await addExerciseToTemplateFromChat(action);
        return;
      }
      if (action.type === "update_preferences") {
        await updatePreferencesFromChat(action);
        return;
      }
      if (action.type === "reschedule_workout") {
        await rescheduleWorkoutFromChat(action);
        return;
      }
      if (action.type === "manager_create_promotion") {
        await createPromotionFromChat(action);
        return;
      }
      if (action.type === "manager_notification_draft") {
        await createNotificationDraftFromChat(action);
        return;
      }
      appendMessage({ role: "assistant", text: `I cannot execute "${action.label}" yet.` });
    } finally {
      setPendingActionKey(null);
    }
  }

  function executeChatAction(action: ChatToolAction) {
    if (needsActionConfirmation(action)) {
      setConfirmingActionKey(actionKey(action));
      return;
    }
    void runChatAction(action);
  }

  return (
    <section className="coach-layout">
      <aside className="chat-history-panel">
        <div className="chat-history-head">
          <div>
            <p className="eyebrow">Conversations</p>
            <h3>Coach chats</h3>
          </div>
          <button onClick={startNewChat}>New</button>
        </div>
        <label className="search-field">
          <Search size={16} />
          <input value={chatSearch} onChange={(event) => setChatSearch(event.target.value)} placeholder="Search chats" />
        </label>
        <div className="chat-session-list">
          {visibleSessions.map((session) => (
            <div className={`chat-session-item ${session.id === activeChatId ? "active" : ""}`} key={session.id}>
              <button className="chat-session-main" onClick={() => setActiveChatId(session.id)}>
                <span>{session.pinned && <Pin size={12} />} {session.title}</span>
                <small>{session.messages.length} messages</small>
              </button>
              <button className="chat-session-menu-button" onClick={() => setOpenMenuId(openMenuId === session.id ? null : session.id)}>
                <MoreHorizontal size={16} />
              </button>
              {openMenuId === session.id && (
                <div className="chat-session-menu">
                  <button onClick={() => renameChat(session.id)}>Rename</button>
                  <button onClick={() => togglePinChat(session.id)}>{session.pinned ? "Unpin" : "Pin"}</button>
                  <button className="danger-mini" onClick={() => deleteChat(session.id)}><Trash2 size={14} /> Delete</button>
                </div>
              )}
            </div>
          ))}
        </div>
      </aside>
      <article className="coach-window">
        <div className="coach-titlebar">
          <div className="coach-avatar"><Sparkles size={22} /></div>
          <div>
            <h3>AI Assistant</h3>
            <span>{activeChat?.title ?? "Training chat"}</span>
          </div>
          <button onClick={startNewChat}>New chat</button>
        </div>
        <div className="chat-thread">
          <div className="coach-proactive-grid">
            {proactiveCards.map((card) => (
              <button type="button" key={card.label} onClick={() => setInput(card.prompt)}>
                <span>{card.icon}</span>
                <strong>{card.text}</strong>
                <b>{card.label}</b>
              </button>
            ))}
          </div>
          {messages.map((message, index) => (
            <div className={`message ${message.role}`} key={`${message.role}-${index}`}>
              <MessageText text={message.text} />
              {message.role === "assistant" && message.actions && message.actions.length > 0 && (
                <div className="chat-tool-actions">
                  {message.actions.map((action) => {
                    const key = actionKey(action);
                    const isPending = pendingActionKey === key;
                    const isConfirming = confirmingActionKey === key;
                    return (
                      <div className={`chat-action-card ${isConfirming ? "confirming" : ""}`} key={key}>
                        <button onClick={() => executeChatAction(action)} disabled={status === "loading"}>
                          <strong>{isPending ? "Working..." : action.label}</strong>
                          {action.description && <span>{action.description}</span>}
                        </button>
                        {isConfirming && (
                          <div className="chat-action-confirm">
                            <span>This affects manager/demo data.</span>
                            <button onClick={() => void runChatAction(action)}>Confirm</button>
                            <button onClick={() => setConfirmingActionKey(null)}>Cancel</button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              {message.role === "assistant" && message.citations && message.citations.length > 0 && (
                <details className="chat-citations">
                  <summary>Sources used ({message.citations.length})</summary>
                  <div>
                    {message.citations.slice(0, 4).map((citation) => (
                      <article key={citation.chunk_id}>
                        <strong>{citation.title}</strong>
                        <span>{citationLabel(citation)}</span>
                        {citation.matched_terms.length > 0 && <small>Matched: {citation.matched_terms.slice(0, 6).join(", ")}</small>}
                        <p>{citation.preview}</p>
                        {(citation.source_url || citation.license) && (
                          <small>{citation.source_url || "Local source"} {citation.license ? `- ${citation.license}` : ""}</small>
                        )}
                      </article>
                    ))}
                  </div>
                </details>
              )}
              {message.role === "user" && <button className="message-action" onClick={() => editFrom(index)}>Edit</button>}
            </div>
          ))}
          {status === "loading" && (
            <div className="message assistant typing-message">
              <span />
              <span />
              <span />
            </div>
          )}
        </div>
        <div className="quick-actions">
          {quickActions.map((prompt) => (
            <button type="button" key={prompt} onClick={() => setInput(prompt)}>
              {prompt}
            </button>
          ))}
        </div>
        <div className="chat-composer">
          <textarea
            value={input}
            rows={2}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void sendMessage();
              }
            }}
            placeholder="Ask GymFlow AI..."
          />
          <button className="primary-action" onClick={sendMessage} disabled={status === "loading"}>
            <Bot size={17} /> {status === "loading" ? "Thinking" : "Send"}
          </button>
        </div>
        {status === "error" && <span className="form-error">Coach service is not available.</span>}
      </article>
      <article className="panel coach-side-panel">
        <p className="eyebrow">Coach tools</p>
        <h3>What I can do</h3>
        <div className="assistant-capabilities">
          <div><Sparkles size={16} /><span>Find quieter training times</span></div>
          <div><CalendarClock size={16} /><span>Schedule a forecast-aware week</span></div>
          <div><Target size={16} /><span>Predict next-set load and rep ranges</span></div>
          <div><Dumbbell size={16} /><span>Log target workout sets through tool actions</span></div>
          <div><BookOpen size={16} /><span>Explain exercise technique with RAG citations</span></div>
        </div>
        <p>Answers use occupancy forecasts, logged workouts, preferences, progression targets, and the exercise library. Source cards appear when retrieved context is used, and executable actions are recorded in the audit trail.</p>
        <div className="tool-audit-panel">
          <div>
            <span>Action audit</span>
            <strong>{actionTraces.length} recent actions</strong>
          </div>
          {actionTraces.slice(0, 5).map((trace) => (
            <article key={trace.id}>
              <span className={`audit-status ${trace.status}`}>{trace.status}</span>
              <strong>{trace.label}</strong>
              <small>{trace.action_type} {trace.executed_at ? `- ${formatForecastSlot(trace.executed_at)}` : ""}</small>
            </article>
          ))}
          {!actionTraces.length && <small>No assistant actions executed yet.</small>}
        </div>
      </article>
    </section>
  );
}
