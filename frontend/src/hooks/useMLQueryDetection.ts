/**
 * Heuristic to detect if user query is about ML performance analysis.
 * Used to enforce Trinity file upload requirement.
 */

const ML_KEYWORDS = [
  "ml",
  "machine learning",
  "model performance",
  "accuracy",
  "precision",
  "recall",
  "f1",
  "auc",
  "drift",
  "datadrift",
  "data drift",
  "observability",
  "bias",
  "fairness",
  "deployment",
  "risk assessment",
  "trinity",
  "feature importance",
  "shap",
  "calibration",
];

export function isMLPerformanceQuery(query: string): boolean {
  const lower = query.toLowerCase().trim();
  return ML_KEYWORDS.some((kw) => lower.includes(kw));
}
