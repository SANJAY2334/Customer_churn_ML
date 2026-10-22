# Model Monitoring & Data Drift Architecture

## 1. Overview

In production telecom environments, customer demographics, tariff plans, and competitive dynamics change over time, leading to **covariate shift** (feature drift) and **concept drift** (relationship between features and churn). 

The Telecom Churn ML platform provides native data drift monitoring using the **Population Stability Index (PSI)**, synthetic readiness probing, and production performance evaluation in `src/monitoring.py`.

---

## 2. Population Stability Index (PSI)

### 2.1 Mathematical Formulation
PSI measures the divergence between a baseline reference distribution $P$ (e.g., training or historical dataset) and a target production distribution $Q$ (e.g., monthly inference batch):

$$\text{PSI} = \sum_{b=1}^{B} \left( Q_b - P_b \right) \times \ln\left( \frac{Q_b}{P_b} \right)$$

where:
- $B$ is the number of bins (default: 10 quantile bins for continuous features).
- $P_b$ is the proportion of reference observations in bin $b$.
- $Q_b$ is the proportion of target observations in bin $b$.
- To prevent division by zero or undefined logarithms, a smoothing epsilon ($\epsilon = 10^{-4}$) is applied.

### 2.2 Alert Severity Tiers

| PSI Range | Status Level | Severity | Recommended Operational Action |
| :--- | :--- | :--- | :--- |
| $\text{PSI} < 0.10$ | `GREEN` | Low / Negligible | Baseline distributions match closely. No action required. |
| $0.10 \le \text{PSI} < 0.25$ | `YELLOW` | Moderate Drift | Mild distributional shift detected. Monitor trends and queue retraining evaluation. |
| $\text{PSI} \ge 0.25$ | `RED` | Significant Drift | Critical distributional divergence. Alert on-call ML engineer, investigate data pipeline changes, and trigger retrain/rollback review. |

---

## 3. Drift Monitoring Implementation

### 3.1 Monitored Features
By default, `detect_dataset_drift()` monitors high-impact numeric features and predicted outputs:
1. `tenure`: Customer duration in months.
2. `MonthlyCharges`: Current monthly recurring billing.
3. `TotalCharges`: Cumulative spend.
4. `predicted_probability`: Model-assigned risk score distribution.

Categorical features (e.g. `Contract`, `InternetService`, `PaymentMethod`) are evaluated using relative category frequency histograms.

### 3.2 REST API Monitoring Endpoint

The Flask service exposes `GET /api/monitoring/drift` to query drift status against the reference baseline (`Data/processed_data.csv`).

#### Query Parameters:
- `target_path` (optional): Path to latest production batch CSV (defaults to baseline reference).
- `sample_size` (optional): Subsample size for rapid evaluation.

#### Response Structure:
```json
{
  "status": "success",
  "data": {
    "overall_status": "GREEN",
    "features_monitored": 3,
    "metrics": {
      "tenure": {
        "psi": 0.0000,
        "status": "GREEN"
      },
      "MonthlyCharges": {
        "psi": 0.0000,
        "status": "GREEN"
      },
      "TotalCharges": {
        "psi": 0.0000,
        "status": "GREEN"
      }
    },
    "recommendations": [
      "Distributions are stable. No immediate retraining action required."
    ],
    "evaluated_at": "2026-10-21T15:20:00Z"
  }
}
```

---

## 4. Production Performance Tracking & Degradation Alerts

When actual customer churn outcomes are delayed (e.g., 30–90 days post-prediction), batch evaluation reconciles predictions with ground-truth labels via `evaluate_production_performance()`:

### 4.1 Tracked Metrics & Baseline Degradation Thresholds
- **ROC-AUC**: Degradation alert triggered if ROC-AUC drops by $\ge 0.05$ below the baseline ($0.8449$).
- **F1-Score**: Alert triggered if F1 drops by $\ge 0.08$ below the baseline ($0.6309$).
- **Brier Score**: Alert triggered if calibration error increases by $\ge 0.05$ above baseline ($0.1378$).

### 4.2 Automated Alert Output Example
```json
{
  "alert_level": "RED",
  "action_required": true,
  "degradation_summary": [
    "ROC-AUC degraded by 0.0721 (threshold: 0.0500)",
    "F1-score degraded by 0.0950 (threshold: 0.0800)"
  ],
  "current_metrics": {
    "roc_auc": 0.7728,
    "f1_score": 0.5359,
    "brier_score": 0.1742
  }
}
```

---

## 5. Automated CI/CD & Test Verification

All monitoring logic is tested and verified by `tests/test_mlops_reliability.py`:
- `test_psi_identical_distribution`: Asserts $\text{PSI} \approx 0.0000$ for identical samples.
- `test_psi_shifted_distribution`: Asserts $\text{PSI} \ge 0.25$ and `RED` alert for synthetic +50% distribution shifts.
- `test_detect_dataset_drift_alert_level`: Tests end-to-end dataset drift evaluation across reference and shifted cohorts.
- `test_evaluate_production_performance_stable_and_degraded`: Verifies metric comparison, threshold checks, and alert flag generation.
