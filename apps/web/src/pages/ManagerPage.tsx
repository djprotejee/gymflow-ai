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
import { FutureForecastChart, ChartSkeleton, SkeletonRows } from "../components/ForecastCharts";
import { MessageText } from "../components/MessageText";
import { MuscleAnatomy } from "../components/MuscleAnatomy";
import { fallbackMetrics } from "../data/modelMetrics";
import { API_URL, authHeaders, getJson } from "../lib/api";
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
  FutureForecastPoint,
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

type ManagerForecastPoint = FutureForecastPoint & { gym_id: string };

export function ManagerPage({ data, onDashboardPatch }: { data: DashboardData; onDashboardPatch: (patch: DashboardPatch) => void }) {
  const [discountPercent, setDiscountPercent] = useState("15");
  const [promotionTitle, setPromotionTitle] = useState("Off-peak training bonus");
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [selectedGymId, setSelectedGymId] = useState("all");
  const [horizonDays, setHorizonDays] = useState(7);
  const [selectedWeekday, setSelectedWeekday] = useState<string | null>(null);
  const [selectedHour, setSelectedHour] = useState<number | null>(null);
  const [showKpiReport, setShowKpiReport] = useState(false);
  const [managerInsight, setManagerInsight] = useState("Peak hour forecast updated");
  const [managerForecastRows, setManagerForecastRows] = useState<ManagerForecastPoint[]>([]);
  const peakLocation = data.managerOverview?.peak_location;
  const horizonStart = new Date(managerForecastRows[0]?.timestamp ?? data.futureForecast[0]?.timestamp ?? new Date().toISOString());
  const horizonEnd = new Date(horizonStart.getTime() + horizonDays * 24 * 60 * 60 * 1000);
  const selectedLocation = data.managerLocations.find((location) => location.gym_id === selectedGymId) ?? null;
  const scopedLocations = selectedGymId === "all" ? data.managerLocations : data.managerLocations.filter((location) => location.gym_id === selectedGymId);
  const activeForecastRows = managerForecastRows.length
    ? managerForecastRows
    : data.futureForecast.map((point) => ({ ...point, gym_id: selectedGymId === "all" ? "network" : selectedGymId }));
  const scopedFutureForecast = activeForecastRows.filter((point) => {
    const timestamp = new Date(point.timestamp);
    const matchesScope = selectedGymId === "all" || point.gym_id === selectedGymId;
    return matchesScope && timestamp >= horizonStart && timestamp < horizonEnd;
  });
  const networkLineChartData = Array.from(scopedFutureForecast.reduce((map, point) => {
    const current = map.get(point.timestamp) ?? {
      timestamp: point.timestamp,
      prediction: 0,
      prediction_interval_low: 0,
      prediction_interval_high: 0,
      model: point.model,
      is_weekend: point.is_weekend,
      is_public_holiday_ua: point.is_public_holiday_ua,
      count: 0,
    };
    current.prediction += point.prediction;
    current.prediction_interval_low += point.prediction_interval_low;
    current.prediction_interval_high += point.prediction_interval_high;
    current.count += 1;
    map.set(point.timestamp, current);
    return map;
  }, new Map<string, FutureForecastPoint & { count: number }>()).values()).map((point) => ({
    timestamp: point.timestamp,
    prediction: point.prediction / Math.max(1, point.count),
    prediction_interval_low: point.prediction_interval_low / Math.max(1, point.count),
    prediction_interval_high: point.prediction_interval_high / Math.max(1, point.count),
    model: point.model,
    is_weekend: point.is_weekend,
    is_public_holiday_ua: point.is_public_holiday_ua,
  }));
  const lineChartData = selectedGymId === "all"
    ? networkLineChartData
    : scopedFutureForecast.length ? scopedFutureForecast : data.futureForecast;
  const futureAvg = Math.round(
    scopedFutureForecast.length
      ? scopedFutureForecast.reduce((sum, point) => sum + point.prediction, 0) / scopedFutureForecast.length
      : data.managerOverview?.future_avg_prediction ?? 0,
  );
  const lowTrafficSlots = data.managerOverview?.low_traffic_slots ?? 0;
  const networkForecastRows = Math.max(1, scopedFutureForecast.length * Math.max(1, data.managerLocations.length));
  const offPeakShare = Math.min(100, Math.round((lowTrafficSlots / networkForecastRows) * 100));
  const averageByGym = scopedFutureForecast.reduce((map, point) => {
    const current = map.get(point.gym_id) ?? { total: 0, count: 0 };
    current.total += point.prediction;
    current.count += 1;
    map.set(point.gym_id, current);
    return map;
  }, new Map<string, { total: number; count: number }>());
  const locationBars = (selectedGymId === "all" ? data.managerLocations : scopedLocations).slice(0, 8).map((location) => {
    const aggregate = averageByGym.get(location.gym_id);
    return {
      ...location,
      scoped_avg_prediction: aggregate ? aggregate.total / Math.max(1, aggregate.count) : location.future_avg_prediction,
    };
  });
  const maxLocationLoad = Math.max(1, ...locationBars.map((location) => location.scoped_avg_prediction));
  const weeklyBars = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((label, index) => {
    const values = scopedFutureForecast.filter((point) => new Date(point.timestamp).getDay() === ((index + 1) % 7));
    const avg = values.length ? Math.round(values.reduce((sum, point) => sum + point.prediction, 0) / values.length) : 0;
    return { label, avg };
  });
  const maxWeeklyLoad = Math.max(1, ...weeklyBars.map((item) => item.avg));
  const weeklyAxisTicks = [maxWeeklyLoad, Math.round(maxWeeklyLoad * 0.66), Math.round(maxWeeklyLoad * 0.33), 0];
  const selectedWeekdayLoad = selectedWeekday ? weeklyBars.find((item) => item.label === selectedWeekday)?.avg ?? 0 : null;
  const selectedCampaigns = data.campaigns
    .filter((campaign) => selectedGymId === "all" || campaign.gym_id === selectedGymId)
    .filter((campaign) => {
      const timestamp = new Date(campaign.timestamp);
      const matchesHorizon = timestamp >= horizonStart && timestamp < horizonEnd;
      const matchesWeekday = !selectedWeekday || ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][timestamp.getDay()] === selectedWeekday;
      const matchesHour = selectedHour === null || timestamp.getHours() === selectedHour;
      return matchesHorizon && matchesWeekday && matchesHour;
    })
    .slice(0, 6);
  const selectedBestCampaign = selectedCampaigns[0] ?? data.campaigns[0];
  const selectedNotifications = data.notifications
    .filter((notification) => selectedGymId === "all" || notification.gym_id === selectedGymId)
    .slice(0, 6);
  const hourlyBars = Array.from({ length: 16 }, (_, index) => index + 7).map((hour) => {
    const campaigns = data.campaigns.filter((campaign) => {
      const timestamp = new Date(campaign.timestamp);
      const matchesScope = selectedGymId === "all" || campaign.gym_id === selectedGymId;
      const matchesHorizon = timestamp >= horizonStart && timestamp < horizonEnd;
      const matchesWeekday = !selectedWeekday || ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][timestamp.getDay()] === selectedWeekday;
      return matchesScope && matchesHorizon && matchesWeekday && timestamp.getHours() === hour;
    });
    const avg = campaigns.length ? Math.round(campaigns.reduce((sum, campaign) => sum + campaign.expected_people, 0) / campaigns.length) : 0;
    return { hour, avg, count: campaigns.length };
  });
  const maxHourlyLoad = Math.max(1, ...hourlyBars.map((item) => item.avg));
  const monthBars = Array.from(scopedFutureForecast.reduce((map, point) => {
    const month = new Date(point.timestamp).toLocaleDateString("en-US", { month: "short" });
    const current = map.get(month) ?? { month, total: 0, count: 0 };
    current.total += point.prediction;
    current.count += 1;
    map.set(month, current);
    return map;
  }, new Map<string, { month: string; total: number; count: number }>()).values()).map((item) => ({
    month: item.month,
    avg: Math.round(item.total / Math.max(1, item.count)),
  }));
  const maxMonthLoad = Math.max(1, ...monthBars.map((item) => item.avg));

  useEffect(() => {
    let cancelled = false;
    const targetLocations = (selectedGymId === "all" ? data.managerLocations.slice(0, 8) : scopedLocations).filter(Boolean);
    if (!targetLocations.length) {
      setManagerForecastRows([]);
      return;
    }
    Promise.all(
      targetLocations.map((location) =>
        fetch(`${API_URL}/gyms/${location.gym_id}/forecast/future?model=hist_gradient_boosting&days=${horizonDays}`)
          .then((response) => (response.ok ? response.json() as Promise<FutureForecastPoint[]> : Promise.resolve([])))
          .then((rows) => rows.map((row) => ({ ...row, gym_id: location.gym_id }))),
      ),
    )
      .then((groups) => {
        if (!cancelled) {
          setManagerForecastRows(groups.flat());
        }
      })
      .catch(() => {
        if (!cancelled) {
          setManagerForecastRows([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [data.managerLocations, horizonDays, selectedGymId]);

  async function launchPromotion() {
    if (!selectedBestCampaign) {
      return;
    }
    setStatus("saving");
    try {
      const response = await fetch(`${API_URL}/manager/promotions`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          gym_id: selectedBestCampaign.gym_id,
          title: promotionTitle,
          starts_at: selectedBestCampaign.timestamp,
          discount_percent: Number(discountPercent),
          expected_people: selectedBestCampaign.expected_people,
          notification_copy: `${promotionTitle}: ${discountPercent}% bonus for training at ${formatSlot(selectedBestCampaign.timestamp)}.`,
        }),
      });
      if (!response.ok) {
        throw new Error("Promotion launch failed");
      }
      const [promotions, notifications] = await Promise.all([
        getJson<Promotion[]>("/manager/promotions"),
        getJson<ManagerNotification[]>("/manager/notifications"),
      ]);
      onDashboardPatch({ promotions, notifications });
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  return (
    <section className="manager-grid">
      <article className="panel manager-command-center">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">SmartGym AI</p>
            <h3>Network manager dashboard</h3>
          </div>
          <Building2 className="accent-icon" size={26} />
        </div>
        <div className="manager-filterbar">
          <label>
            <Building2 size={16} />
            <select value={selectedGymId} onChange={(event) => setSelectedGymId(event.target.value)}>
              <option value="all">All locations</option>
              {data.managerLocations.map((location) => (
                <option key={location.gym_id} value={location.gym_id}>{location.city}, {location.address}</option>
              ))}
            </select>
          </label>
          {[1, 3, 7].map((days) => (
            <button
              type="button"
              className={horizonDays === days ? "active" : ""}
              key={days}
              onClick={() => setHorizonDays(days)}
            >
              <CalendarClock size={16} /> {days === 1 ? "Today" : `Next ${days} days`}
            </button>
          ))}
          <button type="button" onClick={() => { setSelectedWeekday(null); setSelectedHour(null); }}><Activity size={16} /> Clear drilldown</button>
        </div>
        <div className="manager-actionbar">
          <button className="primary-action" onClick={launchPromotion} disabled={status === "saving" || !selectedBestCampaign}>
            <Megaphone size={17} /> Launch promotion
          </button>
          <button className="secondary-action" onClick={() => setShowKpiReport((current) => !current)}><BookOpen size={17} /> {showKpiReport ? "Hide KPI report" : "View KPI report"}</button>
          <button className="secondary-action" onClick={() => setManagerInsight("AI recommendations refreshed for selected filters")}><Sparkles size={17} /> Adjust AI recommendations</button>
        </div>
        <div className="kpi-grid">
          <div className="kpi-card"><Clock size={18} /><span>Peak hours</span><strong>{peakLocation ? `${peakLocation.active_people} people` : "No peak"}</strong><small>{peakLocation ? `${peakLocation.city}, ${peakLocation.address}` : "Waiting for observations"}</small></div>
          <div className="kpi-card"><Users size={18} /><span>Off-peak utilization</span><strong>{offPeakShare}%</strong><small>{lowTrafficSlots} campaign-ready slots</small></div>
          <div className="kpi-card"><ShieldCheck size={18} /><span>Forecast average</span><strong>{futureAvg}</strong><small>Expected people across selected horizon</small></div>
        </div>
        <div className="manager-toast">
          <Sparkles size={18} />
          <div>
            <strong>Peak hour forecast updated</strong>
            <span>{managerInsight}. Scope: {selectedLocation ? `${selectedLocation.city}, ${selectedLocation.address}` : "all locations"} · {horizonDays} day horizon.</span>
          </div>
        </div>
        {showKpiReport && (
          <div className="manager-kpi-report">
            <div><span>Selected scope</span><strong>{selectedLocation ? `${selectedLocation.city}, ${selectedLocation.address}` : "Network"}</strong></div>
            <div><span>Forecast average</span><strong>{futureAvg}</strong></div>
            <div><span>Campaign candidates</span><strong>{selectedCampaigns.length}</strong></div>
            <div><span>{selectedWeekday ? `${selectedWeekday} load` : "Selected day"}</span><strong>{selectedWeekdayLoad ?? "All"}</strong></div>
            <div><span>Selected hour</span><strong>{selectedHour === null ? "All" : `${String(selectedHour).padStart(2, "0")}:00`}</strong></div>
          </div>
        )}
        <div className="manager-note">
          <span>Peak location</span>
          <strong>
            {data.managerOverview?.peak_location
              ? `${data.managerOverview.peak_location.city}, ${data.managerOverview.peak_location.address}: ${data.managerOverview.peak_location.active_people} people`
              : "No live peak detected"}
          </strong>
        </div>
        <div className="manager-dashboard-charts">
          <div className="manager-chart-card manager-forecast-card">
            <div className="mini-chart-heading">
              <strong>Selected gym forecast</strong>
              <span>{selectedLocation ? `${selectedLocation.city}, ${selectedLocation.address}` : "network sample"}</span>
            </div>
            <FutureForecastChart data={lineChartData} />
          </div>
          <div className="manager-chart-card">
            <div className="mini-chart-heading">
              <strong>Forecasted load by gym location</strong>
              <span>{horizonDays === 1 ? "today" : `next ${horizonDays} days`}</span>
            </div>
            <div className="manager-bar-list">
              {locationBars.map((location) => (
                <button
                  className={`manager-bar-row ${selectedGymId === location.gym_id ? "active" : ""}`}
                  key={location.gym_id}
                  onClick={() => setSelectedGymId((current) => current === location.gym_id ? "all" : location.gym_id)}
                  title={`${location.city}, ${location.address}`}
                >
                  <span>{location.city}, {location.address}</span>
                  <div><i style={{ width: `${Math.max(6, Math.round((location.scoped_avg_prediction / maxLocationLoad) * 100))}%` }} /></div>
                  <b>{Math.round(location.scoped_avg_prediction)}</b>
                </button>
              ))}
            </div>
            <small className="manager-chart-note">Each row is one gym branch, not a city aggregate. Click the selected branch again to return to all locations.</small>
          </div>
          <div className="manager-chart-card">
            <div className="mini-chart-heading">
              <strong>Weekly average occupancy</strong>
              <span>{selectedLocation ? selectedLocation.address : "network horizon"}</span>
            </div>
            <div className="weekly-chart-frame">
              <svg className="weekly-axis" viewBox="0 0 42 210" aria-label="Occupancy axis">
                {weeklyAxisTicks.map((tick, tickIndex) => (
                  <text key={`${tick}-${tickIndex}`} x="38" y={14 + tickIndex * 62} textAnchor="end">{tick}</text>
                ))}
              </svg>
              <div className="weekly-bar-chart">
                {weeklyBars.map((item) => (
                  <button
                    className={selectedWeekday === item.label ? "active" : ""}
                    key={item.label}
                    onClick={() => setSelectedWeekday((current) => current === item.label ? null : item.label)}
                    title={`${item.label}: ${item.avg} avg people`}
                  >
                    <i style={{ height: `${Math.max(8, Math.round((item.avg / maxWeeklyLoad) * 100))}%` }} />
                    <span>{item.label}</span>
                    <b>{item.avg}</b>
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="manager-chart-card manager-hour-card">
            <div className="mini-chart-heading">
              <strong>Campaign-ready hours</strong>
              <span>{selectedWeekday ?? "all days"}</span>
            </div>
            <div className="hour-bar-chart">
              {hourlyBars.map((item) => (
                <button className={selectedHour === item.hour ? "active" : ""} key={item.hour} onClick={() => setSelectedHour((current) => current === item.hour ? null : item.hour)}>
                  <i style={{ height: `${Math.max(8, Math.round((item.avg / maxHourlyLoad) * 100))}%` }} />
                  <span>{item.hour}</span>
                  <b>{item.count}</b>
                </button>
              ))}
            </div>
          </div>
          <div className="manager-chart-card">
            <div className="mini-chart-heading">
              <strong>Monthly distribution</strong>
              <span>{horizonDays} day horizon</span>
            </div>
            <div className="month-bar-chart">
              {monthBars.map((item) => (
                <div key={item.month}>
                  <i style={{ height: `${Math.max(8, Math.round((item.avg / maxMonthLoad) * 100))}%` }} />
                  <span>{item.month}</span>
                  <b>{item.avg}</b>
                </div>
              ))}
              {!monthBars.length && <div className="empty-chart">Select a gym to load monthly distribution.</div>}
            </div>
          </div>
        </div>
        <div className="manager-drilldown">
          <div>
            <span>Current drilldown</span>
            <strong>{selectedLocation ? `${selectedLocation.city}, ${selectedLocation.address}` : "Network"} · {selectedWeekday ?? "all days"} · {selectedHour === null ? "all hours" : `${String(selectedHour).padStart(2, "0")}:00`}</strong>
          </div>
          <div>
            <span>Best candidate</span>
            <strong>{selectedCampaigns[0] ? `${selectedCampaigns[0].city}, ${formatSlot(selectedCampaigns[0].timestamp)} · ${Math.round(selectedCampaigns[0].expected_people)} people` : "No candidate in this slice"}</strong>
          </div>
        </div>
        <div className="manager-assistant-card">
          <Bot size={18} />
          <div>
            <strong>Manager assistant</strong>
            <span>{selectedCampaigns[0] ? `Best action: prepare ${discountPercent}% off-peak push for ${selectedCampaigns[0].city} at ${formatSlot(selectedCampaigns[0].timestamp)}.` : "No campaign candidates for the current filter."}</span>
          </div>
          <button className="secondary-action" onClick={launchPromotion} disabled={status === "saving" || !selectedBestCampaign}>Draft campaign</button>
        </div>
      </article>
      <article className="panel">
        <p className="eyebrow">Multi-location comparison</p>
        <h3>Forecasted load by gym</h3>
        <table>
          <thead><tr><th>Location</th><th>Now</th><th>Future avg</th><th>Campaign slots</th></tr></thead>
          <tbody>
            {scopedLocations.slice(0, 8).map((location) => (
              <tr className={selectedGymId === location.gym_id ? "active-row" : ""} key={location.gym_id} onClick={() => setSelectedGymId((current) => current === location.gym_id ? "all" : location.gym_id)}>
                <td>{location.city}, {location.address}</td>
                <td>{location.latest_people}</td>
                <td>{Math.round(location.future_avg_prediction)}</td>
                <td>{location.campaign_candidate_slots}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
      <article className="panel campaign-panel">
        <p className="eyebrow">Dynamic off-peak campaigns</p>
        <h3>Suggested actions</h3>
        <div className="promotion-controls">
          <input value={promotionTitle} onChange={(event) => setPromotionTitle(event.target.value)} />
          <input type="number" min="1" max="90" value={discountPercent} onChange={(event) => setDiscountPercent(event.target.value)} />
          <button className="primary-action" onClick={launchPromotion} disabled={status === "saving" || !selectedBestCampaign}>
            <Megaphone size={17} /> Launch
          </button>
        </div>
        {status === "saved" && <span className="form-success">Promotion scheduled and notification copy generated.</span>}
        {status === "error" && <span className="form-error">Could not launch promotion.</span>}
        <div className="campaign-list">
          {selectedCampaigns.map((campaign) => (
            <div className="campaign-card" key={`${campaign.gym_id}-${campaign.timestamp}`}>
              <div><strong>{campaign.city}, {campaign.address}</strong><span>{formatSlot(campaign.timestamp)}</span></div>
              <b>{Math.round(campaign.expected_people)} people</b>
            </div>
          ))}
        </div>
      </article>
      <article className="panel wide-panel">
        <p className="eyebrow">Promotion center</p>
        <h3>Scheduled discounts and push copy</h3>
        <div className="promotion-list">
          {data.promotions.map((promotion) => (
            <div className="promotion-card" key={promotion.id}>
              <div>
                <span>{promotion.gym_id} · {formatSlot(promotion.starts_at)} · {promotion.status}</span>
                <strong>{promotion.title}</strong>
                <small>{promotion.notification_copy}</small>
              </div>
              <b>{promotion.discount_percent}%</b>
            </div>
          ))}
        </div>
      </article>
      <article className="panel">
        <p className="eyebrow">Member notifications</p>
        <h3>{data.notifications.length} notification drafts</h3>
        <div className="slot-list">
          {selectedNotifications.map((notification) => (
            <div className="slot-card" key={notification.promotion_id}>
              <span>{notification.channel} · {formatSlot(notification.send_at)}</span>
              <strong>{notification.status}</strong>
            </div>
          ))}
        </div>
      </article>
    </section>
  );
}
