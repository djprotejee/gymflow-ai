import { useEffect, useRef } from "react";
import { BodyChart, ViewSide } from "body-muscles";

type ExerciseForAnatomy = {
  name: string;
  muscle_group: string;
  primary_muscles: string[];
  secondary_muscles: string[];
};

const muscleLabels: Record<string, string> = {
  "chest-upper-left": "Upper chest",
  "chest-upper-right": "Upper chest",
  "chest-lower-left": "Lower chest",
  "chest-lower-right": "Lower chest",
  "shoulder-front-left": "Front deltoid",
  "shoulder-front-right": "Front deltoid",
  "deltoid-rear-left": "Rear deltoid",
  "deltoid-rear-right": "Rear deltoid",
  "biceps-left": "Biceps",
  "biceps-right": "Biceps",
  "triceps-long-left": "Triceps",
  "triceps-long-right": "Triceps",
  "triceps-lateral-left": "Triceps",
  "triceps-lateral-right": "Triceps",
  "forearm-left": "Forearms",
  "forearm-right": "Forearms",
  "traps-upper-left": "Upper traps",
  "traps-upper-right": "Upper traps",
  "traps-mid-left": "Mid traps",
  "traps-mid-right": "Mid traps",
  "lats-upper-left": "Upper lats",
  "lats-upper-right": "Upper lats",
  "lats-mid-left": "Mid lats",
  "lats-mid-right": "Mid lats",
  "lats-lower-left": "Lower lats",
  "lats-lower-right": "Lower lats",
  "quads-left": "Quads",
  "quads-right": "Quads",
  "adductors-left": "Adductors",
  "adductors-right": "Adductors",
  "glutes-left": "Glutes",
  "glutes-right": "Glutes",
  "gluteus-medius-left": "Glutes",
  "gluteus-medius-right": "Glutes",
  "gluteus-maximus-left": "Glutes",
  "gluteus-maximus-right": "Glutes",
  "hamstrings-left": "Hamstrings",
  "hamstrings-right": "Hamstrings",
  "hamstrings-medial-left": "Hamstrings",
  "hamstrings-medial-right": "Hamstrings",
  "hamstrings-lateral-left": "Hamstrings",
  "hamstrings-lateral-right": "Hamstrings",
  "calves-left": "Calves",
  "calves-right": "Calves",
  "calves-gastroc-medial-left": "Calves",
  "calves-gastroc-medial-right": "Calves",
  "calves-gastroc-lateral-left": "Calves",
  "calves-gastroc-lateral-right": "Calves",
  "calves-soleus-left": "Calves",
  "calves-soleus-right": "Calves",
  "abs-upper-left": "Upper abs",
  "abs-upper-right": "Upper abs",
  "abs-lower-left": "Lower abs",
  "abs-lower-right": "Lower abs",
  "obliques-left": "Obliques",
  "obliques-right": "Obliques",
  "serratus-anterior-left": "Serratus",
  "serratus-anterior-right": "Serratus",
};

const chartMuscleAliases: Record<string, string[]> = {
  "glutes-left": ["gluteus-medius-left", "gluteus-maximus-left"],
  "glutes-right": ["gluteus-medius-right", "gluteus-maximus-right"],
  "hamstrings-left": ["hamstrings-medial-left", "hamstrings-lateral-left"],
  "hamstrings-right": ["hamstrings-medial-right", "hamstrings-lateral-right"],
  "calves-left": ["calves-gastroc-medial-left", "calves-gastroc-lateral-left", "calves-soleus-left"],
  "calves-right": ["calves-gastroc-medial-right", "calves-gastroc-lateral-right", "calves-soleus-right"],
};

function expandChartMuscles(ids: string[]) {
  return ids.flatMap((id) => chartMuscleAliases[id] ?? [id]);
}

export function uniqueMuscleLabels(ids: string[]) {
  return Array.from(new Set(ids.map((item) => muscleLabels[item] ?? item))).join(", ");
}

export function buildBodyState(primary: string[], secondary: string[]) {
  const state: Record<string, { intensity: number; selected: boolean }> = {};
  for (const muscleId of expandChartMuscles(secondary)) {
    state[muscleId] = { intensity: 4, selected: true };
  }
  // Primary muscles intentionally win on overlap so compound lifts do not look washed out on the chart.
  for (const muscleId of expandChartMuscles(primary)) {
    state[muscleId] = { intensity: 8, selected: true };
  }
  return state;
}

export function BodyMuscleFigure({
  view,
  bodyState,
  label,
}: {
  view: ViewSide;
  bodyState: Record<string, { intensity: number; selected: boolean }>;
  label: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<BodyChart | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }
    chartRef.current = new BodyChart(containerRef.current, {
      view,
      bodyState,
      ariaLabel: label,
      showViewLabel: false,
      onMuscleClick: () => {},
      onMuscleHover: () => {},
    });
    return () => chartRef.current?.destroy();
  }, [label, view]);

  useEffect(() => {
    chartRef.current?.update({ bodyState });
  }, [bodyState]);

  return <div className="body-muscle-figure" ref={containerRef} />;
}

export function MuscleAnatomy({ exercise }: { exercise: ExerciseForAnatomy }) {
  // The backend now sends explicit anatomy ids per exercise, so the UI only formats and renders them.
  const primaryLabels = exercise.primary_muscles.length ? uniqueMuscleLabels(exercise.primary_muscles) : exercise.muscle_group;
  const secondaryLabels = exercise.secondary_muscles.length ? uniqueMuscleLabels(exercise.secondary_muscles) : "Minimal";
  const bodyState = buildBodyState(exercise.primary_muscles, exercise.secondary_muscles);

  return (
    <div className="muscle-anatomy-card">
      <div className="muscle-copy">
        <span>Muscle map</span>
        <strong>{primaryLabels}</strong>
        <small>Secondary: {secondaryLabels}</small>
      </div>
      <div className="muscle-views-grid">
        <div className="muscle-view-panel">
          <div className="muscle-view-label">Front</div>
          <BodyMuscleFigure view={ViewSide.FRONT} bodyState={bodyState} label={`${exercise.name} front muscle map`} />
        </div>
        <div className="muscle-view-panel">
          <div className="muscle-view-label">Back</div>
          <BodyMuscleFigure view={ViewSide.BACK} bodyState={bodyState} label={`${exercise.name} back muscle map`} />
        </div>
      </div>
      <div className="muscle-legend">
        <span><i className="primary-dot" />Primary</span>
        <span><i className="secondary-dot" />Secondary</span>
      </div>
    </div>
  );
}
