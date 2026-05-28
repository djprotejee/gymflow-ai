import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart as RechartsLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatPredictionSlot } from "../lib/format";
import type { ForecastPoint, FutureForecastPoint } from "../types";

function isGymOpenAt(value: string) {
  const date = new Date(value);
  const day = date.getDay();
  const hour = date.getHours();
  const isWeekend = day === 0 || day === 6;
  return isWeekend ? hour >= 9 && hour < 18 : hour >= 7 && hour < 22;
}

function loadColor(value: number, isOpen: boolean) {
  if (!isOpen) {
    return "rgba(255,255,255,0.16)";
  }
  if (value >= 85) {
    return "#ff4d55";
  }
  if (value >= 65) {
    return "#ff9f2d";
  }
  if (value >= 45) {
    return "#ffd05a";
  }
  return "#00d9a4";
}

export function ForecastChart({ data }: { data: ForecastPoint[] }) {
  const chartData = data.slice(-48).map((point) => ({
    time: new Date(point.timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }),
    actual: Math.round(point.actual),
    prediction: Math.round(point.prediction),
  }));

  if (!chartData.length) {
    return <div className="empty-chart">Run the API to load forecast data.</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <RechartsLineChart data={chartData} margin={{ top: 12, right: 18, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
        <XAxis dataKey="time" tick={{ fill: "#9f9488", fontSize: 12 }} tickLine={false} axisLine={false} minTickGap={26} />
        <YAxis tick={{ fill: "#9f9488", fontSize: 12 }} tickLine={false} axisLine={false} width={34} />
        <Tooltip contentStyle={{ background: "#151311", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8 }} labelStyle={{ color: "#f7f2ea" }} itemStyle={{ color: "#f7f2ea" }} />
        <Line type="monotone" dataKey="actual" stroke="#00d9a4" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="prediction" stroke="#ff7a2d" strokeWidth={2} dot={false} />
      </RechartsLineChart>
    </ResponsiveContainer>
  );
}

export function FutureForecastChart({ data }: { data: FutureForecastPoint[] }) {
  const chartData = data.map((point) => ({
    time: formatPredictionSlot(point.timestamp),
    status: isGymOpenAt(point.timestamp) ? "Open" : "Closed",
    prediction: Math.round(point.prediction),
    barValue: isGymOpenAt(point.timestamp) ? Math.round(point.prediction) : 0,
    low: Math.round(point.prediction_interval_low ?? point.prediction),
    high: Math.round(point.prediction_interval_high ?? point.prediction),
    fill: loadColor(point.prediction, isGymOpenAt(point.timestamp)),
  }));

  if (!chartData.length) {
    return <div className="empty-chart">Run future forecast generation.</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
        <XAxis dataKey="time" tick={{ fill: "#9f9488", fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={26} />
        <YAxis tick={{ fill: "#9f9488", fontSize: 11 }} tickLine={false} axisLine={false} width={30} />
        <Tooltip
          contentStyle={{ background: "#151311", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8 }}
          labelStyle={{ color: "#f7f2ea" }}
          itemStyle={{ color: "#f7f2ea" }}
          cursor={{ fill: "rgba(255,255,255,0.04)" }}
          formatter={(value, name, item) => {
            const payload = item.payload as { status?: string; prediction?: number };
            if (name === "barValue" && payload.status === "Closed") {
              return ["Closed", "Status"];
            }
            if (name === "barValue") {
              return [`${payload.prediction ?? value} people`, "Prediction"];
            }
            if (name === "high") {
              return [`${value} people`, "High"];
            }
            if (name === "low") {
              return [`${value} people`, "Low"];
            }
            return [value, name];
          }}
        />
        <Bar dataKey="barValue" radius={[8, 8, 2, 2]}>
          {chartData.map((entry) => <Cell key={`${entry.time}-${entry.status}`} fill={entry.fill} />)}
        </Bar>
        <Line type="monotone" dataKey="high" stroke="rgba(255, 122, 45, 0.38)" strokeWidth={1} dot={false} strokeDasharray="4 4" />
        <Line type="monotone" dataKey="low" stroke="rgba(255, 122, 45, 0.38)" strokeWidth={1} dot={false} strokeDasharray="4 4" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function SkeletonRows({ count = 4 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, index) => (
        <div className="skeleton-row" key={`skeleton-${index}`}>
          <span />
          <i />
          <small />
        </div>
      ))}
    </>
  );
}

export function ChartSkeleton() {
  return (
    <div className="chart-skeleton">
      <span />
      <span />
      <span />
      <span />
    </div>
  );
}
