"""
config.py
---------
Centralized configuration module for the Telecom Customer Churn application.
Ensures uniform model selection, threshold configuration, risk categorization,
retention prioritization, and financial simulator parameters across the entire platform.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any, Tuple

ROOT = Path(__file__).resolve().parent.parent

# Model Paths
DEFAULT_ARTIFACT_PATH = ROOT / "Models" / "churn_models.joblib"
DEFAULT_PKL_PATH = ROOT / "Models" / "churn_model.pkl"
DEFAULT_METRICS_PATH = ROOT / "Models" / "model_metrics.json"
DEFAULT_DATA_PATH = ROOT / "Data" / "processed_data.csv"

# Model Selection Configuration:
# "auto" (default): Selects the top-performing estimator from artifact metadata ("XGBoost").
# Other explicit choices: "XGBoost", "Logistic Regression", "Random Forest", "Decision Tree".
DEFAULT_ACTIVE_MODEL = "auto"
ACTIVE_MODEL_NAME = os.environ.get("CHURN_ACTIVE_MODEL", DEFAULT_ACTIVE_MODEL)

# Centralized Risk Categorization Configuration
RISK_CONFIG = {
    "low_threshold": float(os.environ.get("CHURN_RISK_LOW_THRESH", 0.30)),
    "medium_threshold": float(os.environ.get("CHURN_RISK_MED_THRESH", 0.60)),
    "low_label": "Low Risk",
    "medium_label": "Medium Risk",
    "high_label": "High Risk",
    "low_color": "#22c55e",       # Green
    "medium_color": "#f59e0b",    # Amber/Gold
    "high_color": "#ef4444"       # Red
}

# Production Environment & Security Configuration
ENVIRONMENT = os.environ.get("ENVIRONMENT", os.environ.get("FLASK_ENV", os.environ.get("APP_ENV", "development"))).lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# Authentication: disabled by default in development/testing, required in production
API_AUTH_ENABLED = os.environ.get("API_AUTH_ENABLED", "true" if IS_PRODUCTION else "false").lower() in ("true", "1", "yes")
API_KEY = os.environ.get("CHURN_API_KEY", "")

# Rate Limiting & Networking
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", 60))
CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "*")

# Model Integrity & Verification
EXPECTED_ARTIFACT_SHA256 = os.environ.get(
    "CHURN_ARTIFACT_SHA256",
    "a9f0053a700de50daab7c453f4bd690d7cd09ad0c10927240234a4895d791363"  # Default for Models/churn_model.pkl
)

def get_risk_tier(
    churn_proba: float,
    low_thresh: float | None = None,
    medium_thresh: float | None = None
) -> Tuple[str, str]:
    """
    Classifies a churn probability into a standardized operational risk category.
    Returns: (risk_level_label, risk_color_hex)
    """
    low = low_thresh if low_thresh is not None else RISK_CONFIG["low_threshold"]
    med = medium_thresh if medium_thresh is not None else RISK_CONFIG["medium_threshold"]

    p = max(0.0, min(1.0, float(churn_proba)))
    if p <= low:
        return RISK_CONFIG["low_label"], RISK_CONFIG["low_color"]
    elif p <= med:
        return RISK_CONFIG["medium_label"], RISK_CONFIG["medium_color"]
    else:
        return RISK_CONFIG["high_label"], RISK_CONFIG["high_color"]

# Financial Simulator Parameters
FINANCIAL_CONFIG = {
    "baseline_horizon_months": 36.0,
    "tenure_deduction_cap_months": 24.0,
    "minimum_horizon_floor_months": 12.0,
    "retention_budget_cap_rate": 0.15,  # 15% heuristic policy cap
}

# Retention Prioritization Configuration
PRIORITIZATION_CONFIG = {
    "default_weight_churn": 0.60,      # Weight on churn probability
    "default_weight_clv": 0.40,        # Weight on normalized customer lifetime value
    "high_value_clv_quantile": 0.75,   # Top 25% CLV qualifies as High Value
    "urgent_risk_threshold": 0.60,     # Probability > 60% with high value qualifies as Urgent
}
