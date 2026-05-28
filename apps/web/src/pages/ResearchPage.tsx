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

type RagSearchHit = {
  chunk_id: string;
  title: string;
  source_type: string;
  score: number;
  matched_terms: string[];
  source_url: string;
  license: string;
  preview: string;
};

type RagEvaluationSummary = {
  status: string;
  queries?: number;
  hit_at_1?: number;
  hit_at_3?: number;
  hit_at_6?: number;
  mrr?: number;
  retrieval_method?: string;
  note?: string;
  artifact?: string;
};

type ExerciseMediaCoverageSummary = {
  status: string;
  target_rich_media_coverage?: number;
  member_visible_exercises?: number;
  rich_media_exercises?: number;
  rich_media_coverage?: number;
  external_demo_media_coverage?: number;
  generated_reference_coverage?: number;
  fallback_link_coverage?: number;
  missing_rich_media?: number;
  note?: string;
  artifact?: string;
  missing_sample?: { slug: string; name: string; muscle_group: string; category: string; source_name: string }[];
};

type FineTuningReadinessSummary = {
  status: string;
  train_examples?: number;
  eval_examples?: number;
  format?: string;
  intended_provider?: string;
  not_executed?: string;
  quality_gate?: string;
  artifact?: string;
  fine_tuning_executed?: boolean;
};

export function ResearchPage({ data }: { data: DashboardData }) {
  const [ragQuery, setRagQuery] = useState("bench press next target");
  const [ragHits, setRagHits] = useState<RagSearchHit[]>([]);
  const [ragSummary, setRagSummary] = useState<RagEvaluationSummary | null>(null);
  const [mediaCoverage, setMediaCoverage] = useState<ExerciseMediaCoverageSummary | null>(null);
  const [fineTuningReadiness, setFineTuningReadiness] = useState<FineTuningReadinessSummary | null>(null);
  const [ragStatus, setRagStatus] = useState<"idle" | "loading" | "error">("idle");

  useEffect(() => {
    let cancelled = false;
    async function loadRagStatus() {
      setRagStatus("loading");
      try {
        const [summary, hits] = await Promise.all([
          getJson<RagEvaluationSummary>("/rag/evaluation-summary"),
          getJson<RagSearchHit[]>(`/rag/search?q=${encodeURIComponent(ragQuery)}&user_id=demo&gym_id=gym_008&max_results=5`),
        ]);
        if (!cancelled) {
          setRagSummary(summary);
          setRagHits(hits);
          setRagStatus("idle");
        }
      } catch {
        if (!cancelled) {
          setRagStatus("error");
        }
      }
    }
    void loadRagStatus();
    return () => {
      cancelled = true;
    };
  }, [ragQuery]);

  useEffect(() => {
    let cancelled = false;
    async function loadResearchArtifacts() {
      try {
        const [media, fineTuning] = await Promise.all([
          getJson<ExerciseMediaCoverageSummary>("/research/exercise-media-coverage"),
          getJson<FineTuningReadinessSummary>("/research/fine-tuning-readiness"),
        ]);
        if (!cancelled) {
          setMediaCoverage(media);
          setFineTuningReadiness(fineTuning);
        }
      } catch {
        if (!cancelled) {
          setMediaCoverage({ status: "error", note: "Research artifacts are unavailable." });
          setFineTuningReadiness({ status: "error", fine_tuning_executed: false });
        }
      }
    }
    void loadResearchArtifacts();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="page-grid">
      <article className="panel wide-panel">
        <p className="eyebrow">Forecasting research</p>
        <h3>Model registry snapshot</h3>
        <table>
          <thead><tr><th>Model</th><th>Scope</th><th>MAE</th><th>RMSE</th><th>WAPE</th></tr></thead>
          <tbody>
            {(data.metrics.length ? data.metrics : fallbackMetrics).slice(0, 8).map((row) => (
              <tr key={`${row.model}-${row.scope}`}>
                <td>{prettyModelName(row.model)}</td>
                <td>{row.scope}</td>
                <td>{row.mae}</td>
                <td>{row.rmse}</td>
                <td>{(row.wape * 100).toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
      <article className="panel">
        <p className="eyebrow">Dataset</p>
        <h3>{data.summary?.rows.toLocaleString() ?? "16,597"} observations</h3>
        <p>Normalized 2026 observation window plus separately documented synthetic scenario extension.</p>
      </article>
      <article className="panel">
        <p className="eyebrow">Exercise media audit</p>
        <h3>{mediaCoverage?.rich_media_coverage !== undefined ? `${(mediaCoverage.rich_media_coverage * 100).toFixed(1)}% rich media` : "Run coverage check"}</h3>
        <div className="kpi-grid compact-kpis">
          <div className="kpi-card"><span>Target</span><strong>{mediaCoverage?.target_rich_media_coverage !== undefined ? `${(mediaCoverage.target_rich_media_coverage * 100).toFixed(0)}%` : "-"}</strong></div>
          <div className="kpi-card"><span>Exercises</span><strong>{mediaCoverage?.member_visible_exercises ?? "-"}</strong></div>
          <div className="kpi-card"><span>Missing</span><strong>{mediaCoverage?.missing_rich_media ?? "-"}</strong></div>
        </div>
        <small>
          External demos: {mediaCoverage?.external_demo_media_coverage !== undefined ? `${(mediaCoverage.external_demo_media_coverage * 100).toFixed(1)}%` : "-"}
          {" "}· Generated references removed: {mediaCoverage?.generated_reference_coverage !== undefined ? `${(mediaCoverage.generated_reference_coverage * 100).toFixed(1)}%` : "-"}
        </small>
        <small>{mediaCoverage?.note ?? "Rich media counts only reviewed image, GIF, video, or embedded YouTube media."}</small>
        {mediaCoverage?.artifact && <small>Artifact: {mediaCoverage.artifact}</small>}
      </article>
      <article className="panel">
        <p className="eyebrow">Fine-tuning readiness</p>
        <h3>{fineTuningReadiness?.fine_tuning_executed ? "Tuned model available" : "Dataset candidate only"}</h3>
        <div className="kpi-grid compact-kpis">
          <div className="kpi-card"><span>Train</span><strong>{fineTuningReadiness?.train_examples ?? "-"}</strong></div>
          <div className="kpi-card"><span>Eval</span><strong>{fineTuningReadiness?.eval_examples ?? "-"}</strong></div>
        </div>
        <small>{fineTuningReadiness?.not_executed ?? "No fine-tuning job has been launched from the product yet."}</small>
        {fineTuningReadiness?.artifact && <small>Artifact: {fineTuningReadiness.artifact}</small>}
      </article>
      <article className="panel wide-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Assistant retrieval diagnostics</p>
            <h3>Current non-vector RAG status</h3>
          </div>
          <ShieldCheck className="accent-icon" size={22} />
        </div>
        <div className="rag-debug-grid">
          <div className="rag-debug-summary">
            <span>{ragSummary?.retrieval_method ?? "BM25-style lexical retrieval over GymFlow chunks"}</span>
            <div className="kpi-grid compact-kpis">
              <div className="kpi-card"><span>Queries</span><strong>{ragSummary?.queries ?? "-"}</strong></div>
              <div className="kpi-card"><span>Hit@3</span><strong>{ragSummary?.hit_at_3?.toFixed(2) ?? "-"}</strong></div>
              <div className="kpi-card"><span>MRR</span><strong>{ragSummary?.mrr?.toFixed(2) ?? "-"}</strong></div>
            </div>
            <small>{ragSummary?.note ?? "This panel is manager/research-only and does not appear in the member chat."}</small>
            {ragSummary?.artifact && <small>Artifact: {ragSummary.artifact}</small>}
          </div>
          <div className="rag-debug-search">
            <label>
              Retrieval query
              <input value={ragQuery} onChange={(event) => setRagQuery(event.target.value)} />
            </label>
            {ragStatus === "loading" && <span className="form-success">Loading retrieval context...</span>}
            {ragStatus === "error" && <span className="form-error">RAG diagnostics are unavailable.</span>}
          </div>
        </div>
        <div className="rag-hit-list">
          {ragHits.map((hit) => (
            <article key={hit.chunk_id} className="rag-hit-card">
              <div>
                <strong>{hit.title}</strong>
                <span>{hit.source_type.replace(/_/g, " ")} - score {hit.score.toFixed(2)}</span>
              </div>
              <p>{hit.preview}</p>
              <small>
                Matched: {hit.matched_terms.length ? hit.matched_terms.join(", ") : "none"}
                {hit.license ? ` - ${hit.license}` : ""}
              </small>
            </article>
          ))}
        </div>
      </article>
    </section>
  );
}
