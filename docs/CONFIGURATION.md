# Configuration Reference: Telecom Customer Churn System

This document outlines all configurable parameters, environment variables, defaults, and operational settings for the ML training pipeline, Flask REST API, Streamlit dashboard, and batch processing engine.

---

## 1. Environment Variables

| Variable Name | Default Value | Description |
|---|---|---|
| `CHURN_ACTIVE_MODEL` | `auto` | Selected model from artifact ("auto", "XGBoost", "Logistic Regression") |
| `CHURN_RISK_LOW_THRESH` | `0.30` | Upper bound for Low Risk categorization (≤ 30%) |
| `CHURN_RISK_MED_THRESH` | `0.60` | Upper bound for Medium Risk categorization (≤ 60%) |
| `MODEL_PATH` | `Models/churn_model.pkl` | Path to the active primary scikit-learn pipeline |
| `ARTIFACT_PATH` | `Models/churn_models.joblib` | Path to the multi-model dictionary artifact |
| `DATA_PATH` | `Data/processed_data.csv` | Path to the source training dataset |
| `METRICS_PATH` | `Models/model_metrics.json` | Path to the serialized model evaluation metrics |
| `FLASK_HOST` | `127.0.0.1` | Network interface for the Flask server |
| `FLASK_PORT` | `5000` | Port for the Flask server |
| `MAX_CONTENT_LENGTH` | `16777216` (16 MB) | Maximum permitted request payload / file upload size |

---

## 2. Centralized System Configuration (`src/config.py`)

All risk thresholds, prioritization weights, and financial horizon constants are centralized in `src/config.py`:

```python
RISK_CONFIG = {
    "low_threshold": 0.30,       # Configurable via CHURN_RISK_LOW_THRESH
    "medium_threshold": 0.60,    # Configurable via CHURN_RISK_MED_THRESH
    "low_label": "Low Risk",
    "medium_label": "Medium Risk",
    "high_label": "High Risk",
    "low_color": "#22c55e",      # Green
    "medium_color": "#f59e0b",   # Amber/Gold
    "high_color": "#ef4444"      # Red
}

FINANCIAL_CONFIG = {
    "baseline_horizon_months": 36.0,
    "tenure_deduction_cap_months": 24.0,
    "minimum_horizon_floor_months": 12.0,
    "retention_budget_cap_rate": 0.15,  # 15% heuristic policy cap
}

PRIORITIZATION_CONFIG = {
    "default_weight_churn": 0.60,      # Weight on churn probability
    "default_weight_clv": 0.40,        # Weight on normalized customer lifetime value
    "high_value_clv_quantile": 0.75,   # Top 25% CLV qualifies as High Value
    "urgent_risk_threshold": 0.60,     # Probability > 60% with high value qualifies as Urgent
}
```

---

## 2. Machine Learning Pipeline Settings (`train_model.py`)

Configured in `train_model.py`:

```python
TEST_SIZE = 0.20           # 20% held-out test split
RANDOM_STATE = 42          # Seed for reproducibility
CV_FOLDS = 5               # 5-fold Stratified CV on training set
THRESHOLD_SEARCH_BOUNDS = (0.15, 0.85)  # Permitted range for optimal threshold
```

### Candidate Estimators & Hyperparameters
- **Logistic Regression:** `max_iter=1500, random_state=42`
- **Decision Tree:** `max_depth=6, min_samples_split=10, random_state=42`
- **Random Forest:** `n_estimators=200, max_depth=8, min_samples_split=5, random_state=42`
- **XGBoost:** `n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, eval_metric='logloss'`

---

## 3. Decision Threshold & Risk Tiers (`src/predictor.py`, `src/config.py`)

- **Default Active Model & Threshold:**
  - Runtime default is **XGBoost** with out-of-fold CV-tuned optimal threshold = **`0.3236`**.
  - Alternative estimators (`Logistic Regression` with threshold `0.3081`, `Random Forest` with threshold `0.3255`) remain available via `CHURN_ACTIVE_MODEL` environment variable.
  - Can be overridden programmatically per prediction via `threshold` argument in `predict_customer_churn(model, df, threshold=0.40)`.
- **Operational Risk Categorization:**
  - 🟢 **Low Risk:** Churn Probability $\le 30.0\%$ (Color: `#22c55e`, env: `CHURN_RISK_LOW_THRESH`)
  - 🟡 **Medium Risk:** $30.0\% <$ Churn Probability $\le 60.0\%$ (Color: `#f59e0b`, env: `CHURN_RISK_MED_THRESH`)
  - 🔴 **High Risk:** Churn Probability $> 60.0\%$ (Color: `#ef4444`)

---

## 4. Financial Simulator Configuration (`src/predictor.py`)

- **Lifespan Horizon Formula:**
  $$\text{horizon\_months} = \max(12.0, 36.0 - \min(\text{tenure}, 24.0))$$
- **Retention Offer Cap:**
  $$\text{budget\_cap\_rate} = 0.15 \quad (15\% \text{ of Revenue at Risk})$$

---

## 5. Flask API Configuration (`flask_app.py`)

- `MAX_CONTENT_LENGTH = 16 * 1024 * 1024` (16 Megabytes).
- Swagger UI route: `/apidocs/`
- OpenAPI schema endpoint: `/apispec_1.json`
- Model caching: Singleton pattern via `get_model()`, prevents re-reading disk on requests.
