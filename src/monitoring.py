"""
monitoring.py
-------------
Data drift detection, Population Stability Index (PSI) analysis,
prediction distribution tracking, and production model performance evaluation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, brier_score_loss

from src.config import DEFAULT_DATA_PATH, DEFAULT_METRICS_PATH, ROOT
from src.preprocessing import FEATURE_ORDER, NUMERICAL_COLS


def calculate_psi(
    expected_series: pd.Series,
    actual_series: pd.Series,
    num_bins: int = 10,
    epsilon: float = 1e-4
) -> float:
    """
    Calculates the Population Stability Index (PSI) between a baseline (expected)
    and a production (actual) distribution.

    Formula:
        PSI = sum((Actual_% - Expected_%) * ln(Actual_% / Expected_%))

    Interpretation:
        PSI < 0.10: Stable / No significant distribution change.
        0.10 <= PSI < 0.25: Moderate drift / Requires monitoring.
        PSI >= 0.25: Significant drift / Model retraining recommended.
    """
    exp = pd.to_numeric(expected_series, errors='coerce').dropna()
    act = pd.to_numeric(actual_series, errors='coerce').dropna()

    if len(exp) == 0 or len(act) == 0:
        return 0.0

    # Determine quantile bins based on baseline distribution
    percentiles = np.linspace(0, 100, num_bins + 1)
    try:
        bin_edges = np.percentile(exp, percentiles)
        bin_edges = np.unique(bin_edges)  # remove duplicate edges
        if len(bin_edges) < 2:
            return 0.0
    except Exception:
        return 0.0

    # Include bounds
    bin_edges[0] = -np.inf
    bin_edges[-1] = np.inf

    exp_counts, _ = np.histogram(exp, bins=bin_edges)
    act_counts, _ = np.histogram(act, bins=bin_edges)

    exp_pct = exp_counts / len(exp)
    act_pct = act_counts / len(act)

    # Avoid zero division with small epsilon
    exp_pct = np.where(exp_pct == 0, epsilon, exp_pct)
    act_pct = np.where(act_pct == 0, epsilon, act_pct)

    psi_val = np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct))
    return float(max(0.0, round(psi_val, 4)))


def detect_dataset_drift(
    current_df: pd.DataFrame,
    baseline_df: Optional[pd.DataFrame] = None,
    features_to_check: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Compares feature distributions of a production batch against baseline training data.
    Computes PSI per feature and assigns overall alert level (GREEN, YELLOW, RED).
    """
    if current_df is None or current_df.empty:
        return {
            "status": "error",
            "message": "Current dataset is empty. Cannot evaluate drift.",
            "overall_alert": "UNKNOWN"
        }

    if baseline_df is None:
        if not DEFAULT_DATA_PATH.is_file():
            return {
                "status": "error",
                "message": f"Baseline dataset not found at {DEFAULT_DATA_PATH}",
                "overall_alert": "UNKNOWN"
            }
        baseline_df = pd.read_csv(DEFAULT_DATA_PATH)

    features = features_to_check if features_to_check is not None else [
        f for f in FEATURE_ORDER if f in current_df.columns and f in baseline_df.columns
    ]

    feature_psi = {}
    drifted_features = []
    moderate_drift_features = []

    for feat in features:
        psi = calculate_psi(baseline_df[feat], current_df[feat])
        feature_psi[feat] = psi
        if psi >= 0.25:
            drifted_features.append({"feature": feat, "psi": psi, "severity": "HIGH"})
        elif psi >= 0.10:
            moderate_drift_features.append({"feature": feat, "psi": psi, "severity": "MODERATE"})

    max_psi = max(feature_psi.values()) if feature_psi else 0.0

    if drifted_features:
        alert_level = "RED"
        recommendation = "Significant feature drift detected. Review customer acquisition source and evaluate model retraining."
    elif moderate_drift_features:
        alert_level = "YELLOW"
        recommendation = "Moderate feature drift detected. Continue monitoring and evaluate calibration."
    else:
        alert_level = "GREEN"
        recommendation = "Distributions are stable. No immediate intervention required."

    return {
        "status": "success",
        "overall_alert": alert_level,
        "max_psi": round(float(max_psi), 4),
        "total_features_evaluated": len(features),
        "critical_drift_count": len(drifted_features),
        "moderate_drift_count": len(moderate_drift_features),
        "drifted_features": drifted_features,
        "moderate_drift_features": moderate_drift_features,
        "feature_psi": feature_psi,
        "recommendation": recommendation
    }


def evaluate_production_performance(
    y_true: Optional[Union[pd.Series, np.ndarray, list]] = None,
    y_pred: Optional[Union[pd.Series, np.ndarray, list]] = None,
    y_prob: Optional[Union[pd.Series, np.ndarray, list]] = None,
    metrics_path: Union[str, Path] = DEFAULT_METRICS_PATH
) -> Dict[str, Any]:
    """
    Evaluates real performance once ground-truth churn outcomes are observed.
    Compares against baseline test metrics and flags performance degradation.
    Gracefully handles cases where ground-truth labels are delayed or unavailable.
    """
    if y_true is None or len(y_true) == 0:
        return {
            "status": "PENDING_LABELS",
            "message": "Ground-truth churn outcomes are delayed or unavailable. PSI drift monitoring remains active.",
            "sample_size": 0,
            "current_metrics": None,
            "baseline_metrics": None,
            "f1_drop": 0.0,
            "degradation_alert": False
        }

    if y_pred is None or len(y_pred) == 0:
        raise ValueError("Prediction vector y_pred must not be empty when ground-truth labels are present.")

    yt = np.array(y_true)
    yp = np.array(y_pred)

    acc = float(round(accuracy_score(yt, yp), 4))
    prec = float(round(precision_score(yt, yp, zero_division=0), 4))
    rec = float(round(recall_score(yt, yp, zero_division=0), 4))
    f1 = float(round(f1_score(yt, yp, zero_division=0), 4))

    auc = None
    brier = None
    if y_prob is not None:
        yprob_arr = np.array(y_prob)
        try:
            auc = float(round(roc_auc_score(yt, yprob_arr), 4))
            brier = float(round(brier_score_loss(yt, yprob_arr), 4))
        except Exception:
            pass

    current_metrics = {
        "Accuracy": acc,
        "Precision": prec,
        "Recall": rec,
        "F1-score": f1,
        "ROC-AUC": auc,
        "Brier_Score": brier
    }

    # Compare with reference baseline metrics
    baseline_metrics = {}
    f1_drop = 0.0
    status = "STABLE"

    p_metrics = Path(metrics_path)
    if p_metrics.is_file():
        try:
            with open(p_metrics, "r", encoding="utf-8") as f:
                data = json.load(f)
                best_m = data.get("best_model", "XGBoost")
                baseline_metrics = data.get("metrics", {}).get(best_m, {})
                base_f1 = baseline_metrics.get("F1-score", 0.6389)
                f1_drop = round(float(base_f1 - f1), 4)
                if f1_drop >= 0.05:
                    status = "DEGRADED"
        except Exception:
            pass

    return {
        "status": status,
        "sample_size": len(yt),
        "current_metrics": current_metrics,
        "baseline_metrics": baseline_metrics,
        "f1_drop": f1_drop,
        "degradation_alert": f1_drop >= 0.05
    }
