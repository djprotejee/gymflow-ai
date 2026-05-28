import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { LoginPage } from "./components/LoginPage";
import { Sidebar } from "./components/Sidebar";
import { emptyData } from "./data/emptyData";
import { API_URL, getJson, getJsonOr } from "./lib/api";
import type {
  Achievement,
  ActivityDashboard,
  AuthUser,
  CampaignSuggestion,
  DashboardData,
  DashboardPatch,
  Exercise,
  ForecastPoint,
  FutureForecastPoint,
  GamificationSummary,
  Gym,
  ManagerLocation,
  ManagerNotification,
  ManagerOverview,
  MetricRow,
  NextSession,
  ProgressSummary,
  Promotion,
  ScheduledWorkout,
  SlotRecommendation,
  Summary,
  TrainingPlan,
  UserPreference,
  View,
  Visit,
  WorkoutTemplate,
} from "./types";
import "./styles.css";

const OverviewPage = lazy(() => import("./pages/OverviewPage").then((module) => ({ default: module.OverviewPage })));
const PlannerPage = lazy(() => import("./pages/PlannerPage").then((module) => ({ default: module.PlannerPage })));
const WorkoutsPage = lazy(() => import("./pages/WorkoutsPage").then((module) => ({ default: module.WorkoutsPage })));
const CoachPage = lazy(() => import("./pages/CoachPage").then((module) => ({ default: module.CoachPage })));
const ProfilePage = lazy(() => import("./pages/ProfilePage").then((module) => ({ default: module.ProfilePage })));
const ManagerPage = lazy(() => import("./pages/ManagerPage").then((module) => ({ default: module.ManagerPage })));
const ResearchPage = lazy(() => import("./pages/ResearchPage").then((module) => ({ default: module.ResearchPage })));

const DEFAULT_MEMBER_GYM_ID = "gym_008";
const SELECTED_GYM_STORAGE_KEY = "gymflow-selected-gym-id";

// Keep the app shell thin: authentication, shared data loading, and role routing live here.
function App() {
  const savedUser = localStorage.getItem("gymflow-user");
  const [user, setUser] = useState<AuthUser | null>(savedUser ? JSON.parse(savedUser) : null);
  const [token, setToken] = useState(localStorage.getItem("gymflow-token") ?? "");
  const [activeView, setActiveView] = useState<View>(user?.role === "manager" ? "manager" : "overview");
  const [data, setData] = useState<DashboardData>(emptyData);
  const [apiState, setApiState] = useState<"loading" | "ready" | "offline">("loading");
  const [forecastState, setForecastState] = useState<"idle" | "loading">("idle");
  const [selectedGymId, setSelectedGymIdState] = useState(() => localStorage.getItem(SELECTED_GYM_STORAGE_KEY) ?? DEFAULT_MEMBER_GYM_ID);
  const [horizonDays, setHorizonDays] = useState(7);
  const didApplyPreferredGym = useRef(false);

  function setSelectedGymId(value: string) {
    setSelectedGymIdState(value);
    localStorage.setItem(SELECTED_GYM_STORAGE_KEY, value);
  }

  useEffect(() => {
    if (!user) {
      return;
    }
    if (user.role === "manager" && activeView !== "manager" && activeView !== "research") {
      setActiveView("manager");
    }
    if (user.role !== "manager" && (activeView === "manager" || activeView === "research")) {
      setActiveView("overview");
    }
    const currentUser = user;

    async function loadDashboard() {
      setApiState("loading");
      try {
        // Load shared product state in one burst so page modules can stay presentation-focused.
        const isManager = currentUser.role === "manager";
        const managerOverviewRequest = isManager ? getJson<ManagerOverview>("/manager/overview") : Promise.resolve(null);
        const managerLocationsRequest = isManager ? getJson<ManagerLocation[]>("/manager/locations") : Promise.resolve([]);
        const campaignsRequest = isManager ? getJson<CampaignSuggestion[]>("/manager/campaigns") : Promise.resolve([]);
        const promotionsRequest = isManager ? getJson<Promotion[]>("/manager/promotions") : Promise.resolve([]);
        const notificationsRequest = isManager ? getJson<ManagerNotification[]>("/manager/notifications") : Promise.resolve([]);

        const [
          summary,
          gyms,
          metrics,
          progress,
          nextSession,
          preferences,
          gamification,
          visits,
          templates,
          achievements,
          activityDashboard,
          exercises,
          scheduledWorkouts,
          managerOverview,
          managerLocations,
          campaigns,
          promotions,
          notifications,
        ] = await Promise.all([
          getJson<Summary>("/summary"),
          getJson<Gym[]>("/gyms"),
          getJson<MetricRow[]>("/models/ml-metrics"),
          getJson<ProgressSummary>(`/users/${currentUser.user_id}/progress`),
          getJson<NextSession>(`/users/${currentUser.user_id}/next-session?exercise=Barbell%20Bench%20Press`),
          getJson<UserPreference>(`/users/${currentUser.user_id}/preferences`),
          getJson<GamificationSummary>(`/users/${currentUser.user_id}/gamification`),
          getJson<Visit[]>(`/users/${currentUser.user_id}/visits`),
          getJson<WorkoutTemplate[]>(`/users/${currentUser.user_id}/workout-templates`),
          getJson<Achievement[]>(`/users/${currentUser.user_id}/achievements`),
          getJson<ActivityDashboard>(`/users/${currentUser.user_id}/activity-dashboard`),
          getJson<Exercise[]>("/exercise-library"),
          getJson<ScheduledWorkout[]>(`/users/${currentUser.user_id}/scheduled-workouts`),
          managerOverviewRequest,
          managerLocationsRequest,
          campaignsRequest,
          promotionsRequest,
          notificationsRequest,
        ]);
        const fallbackGymId = gyms.find((gym) => gym.city === "Львів" && gym.address === "Стрийська")?.gym_id ?? DEFAULT_MEMBER_GYM_ID;
        const storedGymId = localStorage.getItem(SELECTED_GYM_STORAGE_KEY);
        let preferredGymId = fallbackGymId;
        if (storedGymId && gyms.some((gym) => gym.gym_id === storedGymId)) {
          preferredGymId = storedGymId;
        }
        if (!didApplyPreferredGym.current) {
          setSelectedGymId(preferredGymId);
          didApplyPreferredGym.current = true;
        }
        setData((current) => ({
          ...current,
          summary,
          gyms,
          metrics,
          progress,
          nextSession,
          preferences,
          gamification,
          visits,
          templates,
          achievements,
          activityDashboard,
          exercises,
          scheduledWorkouts,
          managerOverview,
          managerLocations,
          campaigns,
          promotions,
          notifications,
        }));
        setApiState("ready");
      } catch {
        setApiState("offline");
      }
    }

    loadDashboard();
  }, [user]);

  useEffect(() => {
    if (!token) {
      return;
    }
    fetch(`${API_URL}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => (response.ok ? response.json() as Promise<AuthUser> : null))
      .then((nextUser) => {
        if (!nextUser) {
          logoutLocal();
          return;
        }
        setUser(nextUser);
        localStorage.setItem("gymflow-user", JSON.stringify(nextUser));
      })
      .catch(() => undefined);
  }, [token]);

  useEffect(() => {
    if (!user || apiState !== "ready" || !selectedGymId) {
      return;
    }
    const currentUser = user;

    async function loadForecast() {
      setForecastState("loading");
      try {
        // Forecast data is refreshed separately from the slower coach response path.
        const [forecast, slots, futureForecast, futureSlots, trainingPlan] = await Promise.all([
          getJsonOr<ForecastPoint[]>(`/gyms/${selectedGymId}/forecast?model=hist_gradient_boosting&limit=2000`, []),
          getJsonOr<SlotRecommendation[]>(`/recommendations/slots?gym_id=${selectedGymId}&max_results=3`, []),
          getJsonOr<FutureForecastPoint[]>(`/gyms/${selectedGymId}/forecast/future?model=hist_gradient_boosting&days=${horizonDays}`, []),
          getJsonOr<SlotRecommendation[]>(`/users/${currentUser.user_id}/recommendations/future-slots?gym_id=${selectedGymId}&days=${horizonDays}&max_results=3`, []),
          getJsonOr<TrainingPlan | null>(`/users/${currentUser.user_id}/training-plan?gym_id=${selectedGymId}`, null),
        ]);
        setData((current) => ({ ...current, forecast, slots, futureForecast, futureSlots, trainingPlan }));
      } finally {
        setForecastState("idle");
      }

    }

    loadForecast();
  }, [apiState, horizonDays, selectedGymId, user]);

  const selectedGym = useMemo(() => data.gyms.find((gym) => gym.gym_id === selectedGymId), [data.gyms, selectedGymId]);

  function onLogin(nextUser: AuthUser, nextToken: string) {
    setUser(nextUser);
    setToken(nextToken);
    setActiveView(nextUser.role === "manager" ? "manager" : "overview");
  }

  function logoutLocal() {
    localStorage.removeItem("gymflow-token");
    localStorage.removeItem("gymflow-user");
    setUser(null);
    setToken("");
    setData(emptyData);
  }

  function logout() {
    const currentToken = token || localStorage.getItem("gymflow-token");
    if (currentToken) {
      fetch(`${API_URL}/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${currentToken}` } }).catch(() => undefined);
    }
    logoutLocal();
  }

  function patchDashboard(patch: DashboardPatch) {
    setData((current) => ({ ...current, ...patch }));
  }

  if (!user || !token) {
    return <LoginPage onLogin={onLogin} />;
  }

  return (
    <main className="app-shell">
      <Sidebar user={user} activeView={activeView} setActiveView={setActiveView} onLogout={logout} />
      <section className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">GymFlow AI workspace</p>
            <h2>{activeView === "manager" ? "Network manager console" : "Member training app"}</h2>
          </div>
        </header>

        <Suspense fallback={<section className="panel page-loading">Loading workspace...</section>}>
          {activeView === "overview" && (
            <OverviewPage
              data={data}
              user={user}
              selectedGym={selectedGym}
              selectedGymId={selectedGymId}
              isForecastLoading={forecastState === "loading"}
              setSelectedGymId={setSelectedGymId}
              setActiveView={setActiveView}
            />
          )}
          {activeView === "planner" && (
            <PlannerPage
              data={data}
              userId={user.user_id}
              selectedGymId={selectedGymId}
              horizonDays={horizonDays}
              isForecastLoading={forecastState === "loading"}
              setHorizonDays={setHorizonDays}
              setSelectedGymId={setSelectedGymId}
              onDashboardPatch={patchDashboard}
            />
          )}
          {activeView === "workouts" && <WorkoutsPage data={data} userId={user.user_id} onDashboardPatch={patchDashboard} />}
          {activeView === "coach" && (
            <CoachPage
              data={data}
              userId={user.user_id}
              selectedGymId={selectedGymId}
              onDashboardPatch={patchDashboard}
            />
          )}
          {activeView === "profile" && (
            <ProfilePage
              data={data}
              userId={user.user_id}
              selectedGymId={selectedGymId}
              horizonDays={horizonDays}
              setSelectedGymId={setSelectedGymId}
              onDashboardPatch={patchDashboard}
            />
          )}
          {activeView === "manager" && <ManagerPage data={data} onDashboardPatch={patchDashboard} />}
          {activeView === "research" && <ResearchPage data={data} />}
        </Suspense>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
