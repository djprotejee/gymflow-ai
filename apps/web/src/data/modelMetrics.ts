import type { MetricRow } from "../types";

export const fallbackMetrics: MetricRow[] = [
  { model: "hist_gradient_boosting", scope: "all_gyms_pooled", train_rows: 13269, test_rows: 3328, mae: 6.5723, rmse: 9.7546, wape: 0.1497 },
  { model: "random_forest", scope: "all_gyms_pooled", train_rows: 13269, test_rows: 3328, mae: 7.1203, rmse: 10.522, wape: 0.1622 },
  { model: "transformer_sequence_torch", scope: "all_gyms_pooled_sequence", train_rows: 11476, test_rows: 3286, mae: 7.5006, rmse: 11.2579, wape: 0.172 },
];
