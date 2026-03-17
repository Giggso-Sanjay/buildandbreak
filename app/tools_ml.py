"""
AI Deployment Safety Engine — ML Domain Tools
===============================================
7 tools that read ml_knowledge_base.json and return structured intelligence.
The star tool is assess_deployment_risk() — the Risk Engine.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Resolve knowledge base path relative to project root
_KB_PATH = Path(__file__).resolve().parent / "ml_knowledge_base.json"


def _load_kb() -> Dict[str, Any]:
    """Load the ML knowledge base."""
    with open(_KB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ─── METRIC DEFINITIONS (plain-language) ─────────────────────────────────────

METRIC_DEFINITIONS = {
    "accuracy": {
        "name": "Accuracy",
        "definition": "The percentage of correct predictions out of all predictions made. If the model says 'yes' or 'no' 100 times, accuracy tells you how many of those it got right.",
        "good_range": "Above 0.85 is generally good, but depends on the problem.",
        "caveat": "Can be misleading with imbalanced classes — a model that always predicts the majority class can still have high accuracy."
    },
    "precision": {
        "name": "Precision",
        "definition": "When the model predicts 'positive', how often is it actually correct? High precision means few false alarms.",
        "good_range": "Above 0.80 for most applications.",
        "caveat": "High precision can come at the cost of missing real positives (low recall)."
    },
    "recall": {
        "name": "Recall (Sensitivity)",
        "definition": "Out of all actual positive cases, how many did the model catch? High recall means the model rarely misses real cases.",
        "good_range": "Above 0.70 for critical applications.",
        "caveat": "High recall can mean more false alarms (low precision)."
    },
    "f1": {
        "name": "F1 Score",
        "definition": "The harmonic mean of precision and recall — it balances both into a single number. Think of it as: how well does the model catch real cases WITHOUT crying wolf?",
        "good_range": "Above 0.75 is solid.",
        "caveat": "F1 treats precision and recall equally. If one matters more, use F-beta instead."
    },
    "auc": {
        "name": "AUC (Area Under ROC Curve)",
        "definition": "Measures the model's ability to distinguish between classes across all thresholds. An AUC of 1.0 means perfect separation; 0.5 means random guessing.",
        "good_range": "Above 0.80 is good; above 0.90 is excellent.",
        "caveat": "Can be optimistic with imbalanced datasets."
    },
    "specificity": {
        "name": "Specificity",
        "definition": "Out of all actual negative cases, how many did the model correctly identify as negative? It's recall for the negative class.",
        "good_range": "Above 0.85 for most applications.",
        "caveat": "High specificity may come at the cost of missing positives."
    },
    "false_positive_rate": {
        "name": "False Positive Rate",
        "definition": "How often does the model incorrectly flag a negative case as positive? These are false alarms that waste time and resources.",
        "good_range": "Below 0.10 (10%).",
        "caveat": "In some domains (like fraud detection), some false positives are acceptable to catch more real cases."
    },
    "false_negative_rate": {
        "name": "False Negative Rate",
        "definition": "How often does the model miss a real positive case? These are missed detections — the most dangerous errors in critical applications.",
        "good_range": "Below 0.20 (20%) for critical applications.",
        "caveat": "This is the opposite of recall. A high FNR means the model is 'blind' to real events."
    },
    "data_drift": {
        "name": "Data Drift",
        "definition": "When the distribution of incoming production data changes compared to the training data. Like a weather model trained on summer data being used in winter.",
        "good_range": "Drift below 10% of features is acceptable.",
        "caveat": "Even small drift in key features can severely impact predictions."
    },
    "statistical_parity_difference": {
        "name": "Statistical Parity Difference",
        "definition": "The difference in favorable outcome rates between unprivileged and privileged groups. A value of 0 means equal rates.",
        "good_range": "Between -0.1 and 0.1.",
        "caveat": "Doesn't account for legitimate differences between groups."
    },
    "disparate_impact": {
        "name": "Disparate Impact",
        "definition": "The ratio of favorable outcome rates for unprivileged vs privileged groups. A value of 1.0 means equal treatment.",
        "good_range": "Between 0.8 and 1.25.",
        "caveat": "Legal threshold in some jurisdictions is 0.8 (the 80% rule)."
    },
    "calibration_error": {
        "name": "Calibration Error",
        "definition": "How well the model's predicted probabilities match actual outcomes. If the model says '70% chance', it should be right about 70% of the time.",
        "good_range": "Below 0.05.",
        "caveat": "Poorly calibrated models give overconfident or underconfident predictions."
    },
    "shap": {
        "name": "SHAP Values",
        "definition": "SHapley Additive exPlanations — a game-theory approach to explain which features contribute most to predictions. Higher absolute SHAP value = more influence.",
        "good_range": "No single good range — look for reasonable distribution across features.",
        "caveat": "Concentration of influence in few features may indicate overfitting or bias."
    }
}


# ─── TOOL 1: Model Performance ───────────────────────────────────────────────

def get_model_performance() -> str:
    """Return current and reference model performance metrics with deltas."""
    kb = _load_kb()
    perf = kb.get("performance_metrics", {})
    cm = kb.get("confusion_matrix", {})

    current = perf.get("current", {})
    reference = perf.get("reference", {})

    # Compute deltas
    deltas = {}
    for key in ["accuracy", "precision", "recall", "f1"]:
        curr_val = current.get(key)
        ref_val = reference.get(key)
        if isinstance(curr_val, (int, float)) and isinstance(ref_val, (int, float)):
            delta = curr_val - ref_val
            deltas[key] = round(delta, 4)

    result = {
        "model_name": kb.get("model_info", {}).get("name", "Unknown"),
        "model_type": kb.get("model_info", {}).get("type", "Unknown"),
        "current_metrics": {k: (round(v, 4) if v is not None else "data not provided") for k, v in current.items()},
        "reference_metrics": {k: (round(v, 4) if v is not None else "data not provided") for k, v in reference.items()},
        "deltas": deltas,
        "confusion_matrix": cm.get("labels", {}),
        "false_positive_rate": round(cm.get("derived", {}).get("false_positive_rate", 0), 4) if cm.get("derived", {}).get("false_positive_rate") is not None else "data not provided",
        "false_negative_rate": round(cm.get("derived", {}).get("false_negative_rate", 0), 4) if cm.get("derived", {}).get("false_negative_rate") is not None else "data not provided",
        "severity": perf.get("severity", "info"),
        "message": perf.get("performance_message", "No performance message available.")
    }
    return json.dumps(result, indent=2)


# ─── TOOL 2: Drift Report ────────────────────────────────────────────────────

def get_drift_report(drift_type: str = "data") -> str:
    """Return data drift or target drift details.
    
    Args:
        drift_type: Either 'data' for feature drift or 'target' for target drift.
    """
    kb = _load_kb()

    if drift_type == "target":
        td = kb.get("target_drift", {})
        result = {
            "drift_type": "target",
            "drift_detected": td.get("drift_detected", False),
            "severity": td.get("severity", "info"),
            "p_value": td.get("target_pvalue", "data not provided"),
            "message": td.get("message", "No target drift message available.")
        }
    else:
        dd = kb.get("data_drift", {})
        result = {
            "drift_type": "data",
            "drift_detected": dd.get("drift_detected", False),
            "severity": dd.get("severity", "info"),
            "drifted_features_count": dd.get("drifted_features_count", 0),
            "total_features_count": dd.get("total_features_count", 0),
            "drift_percentage": dd.get("drift_percentage", 0),
            "drifted_features": dd.get("drifted_features", []),
            "message": dd.get("message", "No data drift message available.")
        }

    return json.dumps(result, indent=2)


# ─── TOOL 3: Bias Report ─────────────────────────────────────────────────────

def get_bias_report() -> str:
    """Return fairness and bias metrics with verdicts."""
    kb = _load_kb()
    bias = kb.get("bias_report", {})

    result = {
        "bias_detected": bias.get("bias_detected", False),
        "severity": bias.get("severity", "info"),
        "biased_columns": bias.get("biased_columns", []),
        "protected_attribute": bias.get("protected_attribute", "Unknown"),
        "privileged_group": bias.get("privileged_group", "Unknown"),
        "unprivileged_group": bias.get("unprivileged_group", "Unknown"),
        "accuracy_without_mitigation": bias.get("accuracy_without_mitigation", "data not provided"),
        "message": bias.get("message", "No bias message available."),
        "metrics": []
    }

    for m in bias.get("metrics", []):
        result["metrics"].append({
            "name": m.get("name", "Unknown"),
            "value": round(m["value"], 4) if m.get("value") is not None else "data not provided",
            "fair_range": m.get("fair_range", []),
            "is_biased": m.get("is_biased", False),
            "verdict": "BIASED" if m.get("is_biased") else "FAIR",
            "explanation": m.get("info", "")
        })

    biased_count = sum(1 for m in bias.get("metrics", []) if m.get("is_biased"))
    result["summary"] = f"{biased_count} of {len(bias.get('metrics', []))} fairness metrics flag bias."

    return json.dumps(result, indent=2)


# ─── TOOL 4: Data Quality Report ─────────────────────────────────────────────

def get_data_quality_report() -> str:
    """Return data quality check summary with severity and recommendations."""
    kb = _load_kb()
    dq = kb.get("data_quality", {})
    df = kb.get("data_freshness", {})
    di = kb.get("data_integrity", {})
    ds = kb.get("data_schema", {})

    result = {
        "quality_checks": {
            "total": dq.get("total_checks", 0),
            "passed": dq.get("passed", 0),
            "failed": dq.get("failed", 0),
            "pass_percentage": dq.get("pass_percentage", 0),
            "severity": dq.get("severity", "info"),
            "message": dq.get("message", "No quality message available."),
            "recommended_action": dq.get("recommended_action", "No recommendation.")
        },
        "data_freshness": {
            "is_fresh": df.get("is_fresh", False),
            "message": df.get("message", "No freshness message available.")
        },
        "data_integrity": {
            "report_generated": di.get("report_generated", False),
            "message": di.get("message", "No integrity message available.")
        },
        "data_schema": {
            "records": ds.get("records_count", "data not provided"),
            "columns": ds.get("columns_count", "data not provided"),
            "size_mb": ds.get("dataset_size_mb", "data not provided"),
            "column_names": ds.get("column_names", [])
        }
    }
    return json.dumps(result, indent=2)


# ─── TOOL 5: Feature Importance ──────────────────────────────────────────────

def get_feature_importance(method: str = "shap") -> str:
    """Return feature importance rankings.
    
    Args:
        method: Either 'shap' for SHAP values or 'importance' for permutation importance.
    """
    kb = _load_kb()
    fi = kb.get("feature_importance", {})

    if method == "importance":
        data = fi.get("permutation", {})
        method_name = "Permutation Importance"
    else:
        data = fi.get("shap", {})
        method_name = "SHAP Global Attribution"

    # Sort by absolute value descending
    sorted_features = sorted(data.items(), key=lambda x: abs(x[1]) if isinstance(x[1], (int, float)) else 0, reverse=True)

    result = {
        "method": method_name,
        "model_name": kb.get("model_info", {}).get("name", "Unknown"),
        "rankings": [
            {"rank": i + 1, "feature": feat, "score": round(score, 6) if isinstance(score, (int, float)) else score}
            for i, (feat, score) in enumerate(sorted_features)
        ],
        "top_3": [feat for feat, _ in sorted_features[:3]],
        "insight": f"Top 3 most influential features: {', '.join(f for f, _ in sorted_features[:3])}" if sorted_features else "No feature importance data available."
    }
    return json.dumps(result, indent=2)


# ─── TOOL 6: DEPLOYMENT RISK ENGINE ⭐ ───────────────────────────────────────

def assess_deployment_risk() -> str:
    """
    THE CORE TOOL — Computes deployment risk score across 6 dimensions,
    makes a go/no-go decision, and generates recommended actions.
    """
    kb = _load_kb()
    perf = kb.get("performance_metrics", {})
    cm = kb.get("confusion_matrix", {})
    bias = kb.get("bias_report", {})
    drift = kb.get("data_drift", {})
    quality = kb.get("data_quality", {})
    cal = kb.get("calibration", {})

    # ─── Compute risk dimensions ───

    # 1. Operational cost risk (false negative rate)
    fnr = cm.get("derived", {}).get("false_negative_rate", 0)
    operational_risk = min(fnr, 1.0)

    # 2. Predictive reliability (1 - AUC)
    auc = perf.get("current", {}).get("auc", 0.5)  # Assume 0.5 (random) if missing
    predictive_risk = 1.0 - auc

    # 3. Confidence reliability (calibration error)
    calibration_risk = min(cal.get("calibration_error", 0) * 5, 1.0)  # scale up, cap at 1

    # 4. Fairness/Bias risk
    biased_count = sum(1 for m in bias.get("metrics", []) if m.get("is_biased"))
    total_bias_metrics = len(bias.get("metrics", []))
    bias_risk = biased_count / total_bias_metrics if total_bias_metrics > 0 else 0

    # 5. Data drift risk
    drift_risk = drift.get("drift_percentage", 0) / 100.0

    # 6. Data quality risk
    quality_risk = 1.0 - (quality.get("pass_percentage", 100) / 100.0)

    # ─── Weighted risk score ───
    risk_score = (
        0.25 * operational_risk +
        0.20 * predictive_risk +
        0.15 * calibration_risk +
        0.15 * bias_risk +
        0.15 * drift_risk +
        0.10 * quality_risk
    )
    risk_score = round(min(risk_score, 1.0), 4)

    # ─── Deployment decision ───
    if risk_score > 0.60:
        decision = "DO_NOT_DEPLOY"
    elif risk_score > 0.35:
        decision = "CAUTION"
    else:
        decision = "SAFE"

    # ─── Identify primary risks ───
    primary_risks = []
    if fnr > 0.3:
        primary_risks.append("high_false_negative_rate")
    if auc < 0.75:
        primary_risks.append("low_auc_score")
    if bias_risk > 0.5:
        primary_risks.append("bias_in_protected_features")
    if drift.get("drift_detected"):
        primary_risks.append("data_drift_detected")
    if quality.get("pass_percentage", 100) < 50:
        primary_risks.append("data_quality_failures")
    
    cur_acc = perf.get("current", {}).get("accuracy")
    ref_acc = perf.get("reference", {}).get("accuracy")
    if cur_acc is not None and ref_acc is not None and cur_acc < ref_acc - 0.05:
        primary_risks.append("significant_accuracy_degradation")
    
    if cal.get("calibration_error", 0) > 0.05:
        primary_risks.append("poor_calibration")

    # ─── Recommended actions ───
    actions = []
    if cur_acc is not None and ref_acc is not None and cur_acc < ref_acc - 0.05:
        drop = round((ref_acc - cur_acc) * 100, 1)
        actions.append(f"Retrain model — accuracy dropped {drop}% from reference ({round(ref_acc*100,1)}% → {round(cur_acc*100,1)}%)")

    cur_recall = perf.get("current", {}).get("recall")
    if cur_recall is not None and cur_recall < 0.7:
        actions.append("Adjust classification threshold to improve recall — currently missing too many positive cases")

    if fnr > 0.3:
        actions.append(f"Reduce false negative rate (currently {round(fnr*100,1)}%) — collect more positive-class training samples")

    if bias_risk > 0.5:
        actions.append(f"Run fairness audit — bias detected in {biased_count}/{total_bias_metrics} metrics against unprivileged group")

    if drift.get("drift_detected"):
        features = ", ".join(drift.get("drifted_features", []))
        actions.append(f"Investigate drifted features before deployment: {features}")

    pass_pct = quality.get("pass_percentage")
    if pass_pct is not None and pass_pct < 50:
        actions.append(f"Fix data quality — only {pass_pct}% of {quality.get('total_checks', 0)} checks passing")

    if cal.get("calibration_error", 0) > 0.05:
        actions.append("Recalibrate model predictions — probability estimates are unreliable")

    # ─── Plain language summary ───
    if decision == "DO_NOT_DEPLOY":
        summary = f"This model is NOT safe to deploy. Risk score: {risk_score}/1.0. "
    elif decision == "CAUTION":
        summary = f"Deployment requires caution. Risk score: {risk_score}/1.0. "
    else:
        summary = f"Model is safe to deploy. Risk score: {risk_score}/1.0. "

    risk_details = []
    if fnr > 0.3:
        risk_details.append(f"a {round(fnr*100,1)}% false negative rate (missing real cases)")
    if bias_risk > 0.5:
        risk_details.append(f"bias detected in {biased_count}/{total_bias_metrics} fairness metrics")
    if pass_pct is not None and pass_pct < 50:
        risk_details.append(f"only {pass_pct}% of data quality checks passing")
    if cur_acc is not None and ref_acc is not None and cur_acc < ref_acc - 0.05:
        risk_details.append(f"accuracy degraded from {round(ref_acc*100,1)}% to {round(cur_acc*100,1)}%")

    if risk_details:
        summary += "Key concerns: " + "; ".join(risk_details) + "."

    # ─── Build output ───
    result = {
        "deployment_decision": decision,
        "risk_score": risk_score,
        "risk_dimensions": {
            "operational_cost_risk": {
                "score": round(operational_risk, 4),
                "severity": "critical" if operational_risk > 0.3 else "warning" if operational_risk > 0.15 else "info",
                "detail": f"False negative rate: {round(fnr*100,1)}%"
            },
            "model_strength": {
                "score": round(predictive_risk, 4),
                "severity": "critical" if predictive_risk > 0.3 else "warning" if predictive_risk > 0.15 else "info",
                "detail": f"AUC: {round(auc, 4)}"
            },
            "confidence_risk": {
                "score": round(calibration_risk, 4),
                "severity": "critical" if calibration_risk > 0.3 else "warning" if calibration_risk > 0.15 else "info",
                "detail": f"Calibration error: {round(cal.get('calibration_error', 0), 4)}"
            },
            "bias_risk": {
                "score": round(bias_risk, 4),
                "severity": "critical" if bias_risk > 0.5 else "warning" if bias_risk > 0.2 else "info",
                "detail": f"{biased_count}/{total_bias_metrics} metrics flag bias"
            },
            "drift_risk": {
                "score": round(drift_risk, 4),
                "severity": "critical" if drift_risk > 0.3 else "warning" if drift_risk > 0.1 else "info",
                "detail": f"Drift in {drift.get('drifted_features_count', 0)}/{drift.get('total_features_count', 0)} features ({drift.get('drift_percentage', 0)}%)"
            },
            "data_quality_risk": {
                "score": round(quality_risk, 4),
                "severity": "critical" if quality_risk > 0.5 else "warning" if quality_risk > 0.2 else "info",
                "detail": f"Quality checks: {quality.get('passed', 0)}/{quality.get('total_checks', 0)} passed ({quality.get('pass_percentage', 0)}%)"
            }
        },
        "primary_risks": primary_risks,
        "recommended_actions": actions,
        "plain_language_summary": summary
    }

    return json.dumps(result, indent=2)


# ─── TOOL 7: Explain Metric ──────────────────────────────────────────────────

def explain_metric(metric_name: str) -> str:
    """Explain an ML metric in plain language with context from the current model.
    
    Args:
        metric_name: Name of the metric to explain (e.g., 'accuracy', 'f1', 'auc', 
                     'recall', 'precision', 'data_drift', 'shap', etc.)
    """
    kb = _load_kb()
    key = metric_name.lower().strip().replace(" ", "_").replace("-", "_")

    definition = METRIC_DEFINITIONS.get(key)

    if not definition:
        # Try fuzzy match
        for k, v in METRIC_DEFINITIONS.items():
            if key in k or k in key:
                definition = v
                key = k
                break

    if not definition:
        available = ", ".join(METRIC_DEFINITIONS.keys())
        return json.dumps({
            "error": f"Unknown metric: '{metric_name}'",
            "available_metrics": available
        })

    result = {
        "metric": definition["name"],
        "definition": definition["definition"],
        "good_range": definition["good_range"],
        "caveat": definition["caveat"]
    }

    # Add current value if available
    perf = kb["performance_metrics"]["current"]
    cm = kb["confusion_matrix"]["derived"]
    ref = kb["performance_metrics"].get("reference", {})

    value_map = {
        "accuracy": perf.get("accuracy"),
        "precision": perf.get("precision"),
        "recall": perf.get("recall"),
        "f1": perf.get("f1"),
        "auc": perf.get("auc"),
        "specificity": perf.get("specificity"),
        "false_positive_rate": cm.get("false_positive_rate"),
        "false_negative_rate": cm.get("false_negative_rate"),
        "calibration_error": kb["calibration"]["calibration_error"],
    }

    if key in value_map and value_map[key] is not None:
        result["current_value"] = round(value_map[key], 4)

    if key in ref:
        result["reference_value"] = round(ref[key], 4)
        delta = value_map.get(key, 0) - ref[key]
        direction = "improved" if delta > 0 else "degraded"
        if key in ("false_positive_rate", "false_negative_rate", "calibration_error"):
            direction = "improved" if delta < 0 else "degraded"
        result["change"] = f"{direction} by {abs(round(delta, 4))}"

    return json.dumps(result, indent=2)


# ─── TOOL 8: Query Orchestrator ──────────────────────────────────────────────

# Keyword → tool mapping for the orchestrator
_QUERY_ROUTING = {
    "deploy": "assess_deployment_risk",
    "safe": "assess_deployment_risk",
    "risk": "assess_deployment_risk",
    "should i": "assess_deployment_risk",
    "ready": "assess_deployment_risk",
    "go live": "assess_deployment_risk",
    "production": "assess_deployment_risk",
    "gatekeeper": "assess_deployment_risk",

    "accuracy": "get_model_performance",
    "precision": "get_model_performance",
    "recall": "get_model_performance",
    "f1": "get_model_performance",
    "auc": "get_model_performance",
    "performance": "get_model_performance",
    "confusion": "get_model_performance",
    "how well": "get_model_performance",
    "metrics": "get_model_performance",

    "drift": "get_drift_report",
    "shift": "get_drift_report",
    "distribution": "get_drift_report",
    "stale": "get_drift_report",

    "bias": "get_bias_report",
    "fair": "get_bias_report",
    "discriminat": "get_bias_report",
    "parity": "get_bias_report",
    "disparate": "get_bias_report",
    "equit": "get_bias_report",

    "quality": "get_data_quality_report",
    "freshness": "get_data_quality_report",
    "integrity": "get_data_quality_report",
    "schema": "get_data_quality_report",
    "data health": "get_data_quality_report",

    "feature": "get_feature_importance",
    "shap": "get_feature_importance",
    "important": "get_feature_importance",
    "influence": "get_feature_importance",
    "explain model": "get_feature_importance",

    "what is": "explain_metric",
    "what does": "explain_metric",
    "define": "explain_metric",
    "meaning": "explain_metric",
}

# Risk mitigation playbook
_MITIGATION_PLAYBOOK = {
    "high_false_negative_rate": {
        "risk": "High False Negative Rate",
        "impact": "The model is missing real positive cases — critical events go undetected",
        "mitigations": [
            "Lower the classification threshold to catch more positives",
            "Collect more positive-class training samples to balance the dataset",
            "Use cost-sensitive learning to penalize false negatives more heavily",
            "Consider ensemble methods that prioritize recall"
        ]
    },
    "low_auc_score": {
        "risk": "Low AUC Score",
        "impact": "The model struggles to distinguish between positive and negative classes",
        "mitigations": [
            "Engineer more discriminative features",
            "Try more complex model architectures",
            "Check for label noise in training data",
            "Increase training data volume"
        ]
    },
    "bias_in_protected_features": {
        "risk": "Bias Against Protected Groups",
        "impact": "The model treats privileged and unprivileged groups inequitably",
        "mitigations": [
            "Apply pre-processing bias mitigation (reweighting, sampling)",
            "Use in-processing fairness constraints during training",
            "Apply post-processing calibration across groups",
            "Conduct adversarial debiasing",
            "Document and disclose bias in model cards"
        ]
    },
    "data_drift_detected": {
        "risk": "Data Drift Detected",
        "impact": "Production data distribution has shifted from training data",
        "mitigations": [
            "Retrain the model on recent production data",
            "Set up continuous monitoring for feature distributions",
            "Investigate root cause of drift in specific features",
            "Consider online learning or periodic retraining pipeline"
        ]
    },
    "data_quality_failures": {
        "risk": "Data Quality Issues",
        "impact": "Input data failing quality checks undermines prediction reliability",
        "mitigations": [
            "Implement data validation at ingestion pipeline",
            "Set up automated data quality gates in CI/CD",
            "Fix schema violations and missing value handling",
            "Establish data quality SLAs with upstream teams"
        ]
    },
    "significant_accuracy_degradation": {
        "risk": "Model Accuracy Degradation",
        "impact": "Current model performs significantly worse than the reference baseline",
        "mitigations": [
            "Retrain with recent data reflecting current distribution",
            "Perform hyperparameter tuning on updated dataset",
            "Compare against alternative model architectures",
            "Roll back to reference model if degradation is critical"
        ]
    },
    "poor_calibration": {
        "risk": "Poor Probability Calibration",
        "impact": "Model confidence scores don't match actual probabilities",
        "mitigations": [
            "Apply Platt scaling or isotonic regression post-hoc",
            "Use temperature scaling for neural network models",
            "Retrain with calibration-aware loss functions",
            "Avoid using raw probabilities for business decisions"
        ]
    }
}


def orchestrate_query(user_query: str) -> str:
    """
    Decompose a complex user query into sub-queries, map each to the right tool,
    execute them, and build a structured response with risk mitigations.

    Args:
        user_query: The user's natural language question about the ML model.
    """
    query_lower = user_query.lower()

    # ─── Step 1: Identify relevant tools ───
    matched_tools = set()
    matched_keywords = []

    for keyword, tool_name in _QUERY_ROUTING.items():
        if keyword in query_lower:
            matched_tools.add(tool_name)
            matched_keywords.append(keyword)

    # Default: if nothing matched, run risk assessment + performance
    if not matched_tools:
        matched_tools.add("assess_deployment_risk")
        matched_tools.add("get_model_performance")

    # ─── Step 2: Build sub-queries with args ───
    tool_descriptions = {
        "assess_deployment_risk": "Full deployment risk assessment (score + decision + actions)",
        "get_model_performance": "Current vs reference model performance metrics",
        "get_drift_report": "Data drift and target drift analysis",
        "get_bias_report": "Fairness and bias across protected attributes",
        "get_data_quality_report": "Data quality, freshness, and integrity",
        "get_feature_importance": "Feature importance rankings (SHAP/permutation)",
        "explain_metric": "Plain-language metric explanation",
    }

    sub_queries = []
    for tool_name in matched_tools:
        sub_queries.append({
            "tool": tool_name,
            "purpose": tool_descriptions.get(tool_name, tool_name),
            "args": _infer_tool_args(tool_name, query_lower)
        })

    # ─── Step 3: Execute tools and collect results ───
    tool_results = {}
    for sq in sub_queries:
        tool_name = sq["tool"]
        args = sq["args"]
        try:
            if tool_name == "get_model_performance":
                tool_results[tool_name] = json.loads(get_model_performance())
            elif tool_name == "get_drift_report":
                tool_results[tool_name] = json.loads(get_drift_report(args.get("drift_type", "data")))
            elif tool_name == "get_bias_report":
                tool_results[tool_name] = json.loads(get_bias_report())
            elif tool_name == "get_data_quality_report":
                tool_results[tool_name] = json.loads(get_data_quality_report())
            elif tool_name == "get_feature_importance":
                tool_results[tool_name] = json.loads(get_feature_importance(args.get("method", "shap")))
            elif tool_name == "assess_deployment_risk":
                tool_results[tool_name] = json.loads(assess_deployment_risk())
            elif tool_name == "explain_metric":
                tool_results[tool_name] = json.loads(explain_metric(args.get("metric_name", "")))
        except Exception as e:
            tool_results[tool_name] = {"error": str(e)}

    # ─── Step 4: Build risk mitigations ───
    mitigations = []
    risk_result = tool_results.get("assess_deployment_risk", {})
    primary_risks = risk_result.get("primary_risks", [])

    for risk_key in primary_risks:
        playbook_entry = _MITIGATION_PLAYBOOK.get(risk_key)
        if playbook_entry:
            mitigations.append(playbook_entry)

    # ─── Step 5: Compose structured response ───
    result = {
        "original_query": user_query,
        "query_decomposition": {
            "matched_keywords": matched_keywords,
            "sub_queries": sub_queries,
            "tools_called": list(tool_results.keys())
        },
        "tool_results": tool_results,
        "risk_mitigations": mitigations,
        "response_plan": _build_response_plan(tool_results, mitigations)
    }

    return json.dumps(result, indent=2)


def _infer_tool_args(tool_name: str, query_lower: str) -> Dict[str, str]:
    """Infer tool arguments from the query context."""
    args: Dict[str, str] = {}
    if tool_name == "get_drift_report":
        args["drift_type"] = "target" if "target" in query_lower else "data"
    elif tool_name == "get_feature_importance":
        args["method"] = "shap" if "shap" in query_lower else "importance"
    elif tool_name == "explain_metric":
        for metric in METRIC_DEFINITIONS:
            if metric.replace("_", " ") in query_lower or metric in query_lower:
                args["metric_name"] = metric
                break
    return args


def _build_response_plan(tool_results: Dict, mitigations: List) -> Dict:
    """Build a structured response plan for the LLM to compose its answer."""
    risk_data = tool_results.get("assess_deployment_risk", {})
    perf_data = tool_results.get("get_model_performance", {})

    plan: Dict[str, Any] = {
        "suggested_structure": [
            "1. Lead with the deployment decision and risk score",
            "2. Summarize key findings from each area",
            "3. List primary risks with plain-language explanations",
            "4. Provide specific mitigation actions for each risk",
            "5. Close with a clear recommendation"
        ]
    }

    decision = risk_data.get("deployment_decision", "UNKNOWN")
    score = risk_data.get("risk_score", "N/A")
    plan["headline"] = f"Deployment Decision: {decision} (Risk Score: {score}/1.0)"

    findings = []
    if perf_data:
        cur = perf_data.get("current_metrics", {})
        findings.append(f"Accuracy: {cur.get('accuracy', 'N/A')} | F1: {cur.get('f1', 'N/A')} | AUC: {cur.get('auc', 'N/A')}")

    drift_data = tool_results.get("get_drift_report", {})
    if drift_data:
        findings.append(f"Data drift: {'Detected' if drift_data.get('drift_detected') else 'Not detected'}")

    bias_data = tool_results.get("get_bias_report", {})
    if bias_data:
        findings.append(f"Bias: {bias_data.get('summary', 'N/A')}")

    quality_data = tool_results.get("get_data_quality_report", {})
    if quality_data:
        qc = quality_data.get("quality_checks", {})
        findings.append(f"Data quality: {qc.get('pass_percentage', 'N/A')}% checks passing")

    plan["key_findings"] = findings
    plan["mitigation_count"] = len(mitigations)

    return plan
