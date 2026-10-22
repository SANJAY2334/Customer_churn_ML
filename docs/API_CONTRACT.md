# API Contract Specification: Telecom Customer Churn Service

This document defines the REST API endpoints, request/response schemas, validation rules, and HTTP status codes for `flask_app.py`.

---

## 1. Endpoints Overview

| Method | Path | Summary | Success Status | Error Statuses |
|---|---|---|---|---|
| `GET` | `/` | Renders Web Dashboard HTML UI | 200 OK | - |
| `GET` | `/api/health` | Service health status, model readiness, threshold | 200 OK | 503 Service Unavailable |
| `GET` | `/api/metrics` | Model comparison metrics & ROC/PR curve points | 200 OK | 404 Not Found |
| `POST` | `/predict` | Single-customer churn prediction & risk analysis | 200 OK | 400 Bad Request, 500 Internal Error |
| `POST` | `/api/batch_predict` | Multipart CSV customer batch scoring | 200 OK | 400 Bad Request, 500 Internal Error |
| `POST` | `/api/prioritize` | Customer cohort ranking & multi-criteria prioritization | 200 OK | 400 Bad Request, 500 Internal Error |
| `POST` | `/api/simulate_retention` | Retention campaign portfolio scenario simulation | 200 OK | 400 Bad Request, 500 Internal Error |
| `GET` | `/apidocs/` | Interactive Swagger / Flasgger Documentation UI | 200 OK | - |
| `GET` | `/apispec_1.json` | OpenAPI / Swagger JSON Specification | 200 OK | - |

---

## 2. Endpoint Details

> [!NOTE]
> **Active Model & Threshold:** The default deployed model is **XGBoost** with CV-tuned decision threshold **`0.3236`**.
> Response payloads documented below are **illustrative schema examples** showing JSON fields and structure; live numeric outputs are dynamically generated from customer profiles.

### 2.1 Health Check (`GET /api/health`)

#### Illustrative Response (200 OK)
```json
{
  "status": "healthy",
  "uptime_seconds": 45.2,
  "model_loaded": true,
  "model_path": "Models/churn_model.pkl",
  "active_threshold": 0.3236
}
```

#### Illustrative Response (503 Service Unavailable)
```json
{
  "status": "degraded",
  "uptime_seconds": 1.2,
  "model_loaded": false,
  "model_path": "Models/churn_model.pkl",
  "active_threshold": null
}
```

---

### 2.2 Model Metrics (`GET /api/metrics`)

#### Illustrative Response (200 OK)
```json
{
  "best_model": "XGBoost",
  "primary_model_name": "XGBoost",
  "model_version": "1.0.0",
  "training_timestamp": "2026-10-21T13:54:55Z",
  "metrics": {
    "XGBoost": {
      "Accuracy": 0.7779,
      "Precision": 0.5654,
      "Recall": 0.7701,
      "F1-score": 0.6389,
      "ROC-AUC": 0.8572,
      "Optimal Threshold": 0.3236,
      "Confusion matrix": [[808, 227], [86, 288]]
    },
    "Logistic Regression": {
      "Accuracy": 0.7715,
      "Precision": 0.5358,
      "Recall": 0.7406,
      "F1-score": 0.6218,
      "ROC-AUC": 0.8489,
      "Optimal Threshold": 0.3081,
      "Confusion matrix": [[810, 225], [97, 277]]
    }
  }
}
```

---

### 2.3 Single Customer Prediction (`POST /predict`)

**Headers:** `Content-Type: application/json`

#### Request Payload
```json
{
  "tenure": 2,
  "monthly_charges": 95.5,
  "total_charges": 191.0,
  "gender": "Female",
  "senior_citizen": "Yes",
  "partner": "No",
  "dependents": "No",
  "phone_service": "Yes",
  "multiple_lines": "Yes",
  "internet_service": "Fiber optic",
  "online_security": "No",
  "online_backup": "No",
  "device_protection": "No",
  "tech_support": "No",
  "streaming_tv": "Yes",
  "streaming_movies": "Yes",
  "contract": "Month-to-month",
  "paperless_billing": "Yes",
  "payment_method": "Electronic check"
}
```

#### Illustrative Response (200 OK)
```json
{
  "status": "success",
  "prediction": "Churn (Likely to leave)",
  "churn_probability": 72.4,
  "retain_probability": 27.6,
  "risk_level": "High Risk",
  "risk_color": "#ef4444",
  "risk_action": "🔴 Retention offer - Immediate Customer Success contact within 24 hours",
  "active_model": "XGBoost",
  "threshold_applied": 0.3236,
  "model_version": "1.0.0",
  "financial_impact": {
    "clv": 3247.0,
    "monthly_charges": 95.5,
    "revenue_at_risk": 2350.83,
    "recommended_retention_budget": 352.62,
    "horizon_months": 34,
    "disclaimer": "Revenue at risk is a statistical estimate based on churn probability, not realized loss."
  },
  "recommendations": [
    "🚨 **Immediate Retention Trigger**: Assign a dedicated Customer Success agent to contact this customer within 24 hours with a personalized retention offer.",
    "📜 **Contract Upgrade Offer**: Month-to-month contracts have 4x higher churn risk. Offer a **15% annual discount** for switching to a 1-year or 2-year contract."
  ],
  "top_drivers": [
    {
      "Feature": "Contract_Month-to-month",
      "Coefficient": 0.824,
      "Value": 1.0,
      "Contribution": 0.824
    }
  ],
  "disclaimer": "Statistical risk prediction. Model explanations show statistical correlation and do not imply causal mechanisms."
}
```

#### Illustrative Response (400 Bad Request)
```json
{
  "status": "error",
  "message": "Invalid numerical value: could not convert string to float: 'not_a_number'"
}
```

---

### 2.4 Batch Customer Scoring (`POST /api/batch_predict`)

**Headers:** `Content-Type: multipart/form-data`  
**Body Field:** `file`: uploaded `.csv` file (Max size: 16 MB).

#### Illustrative Response (200 OK)
```json
{
  "status": "success",
  "summary": {
    "total_records": 100,
    "valid_records": 100,
    "churn_count": 36,
    "churn_rate": 36.0,
    "high_risk_count": 18,
    "urgent_priority_count": 14,
    "high_priority_count": 25,
    "total_clv_$": 142500.0,
    "total_revenue_at_risk_$": 44850.0,
    "applied_threshold": 0.3236
  },
  "preview": [
    {
      "Tenure Months": 1,
      "Monthly Charges": 70.5,
      "Predicted_Status": "Churn",
      "Churn_Probability_%": 68.2,
      "Risk_Level": "High Risk",
      "Estimated_CLV_$": 2467.5,
      "Revenue_At_Risk_$": 1682.84,
      "Recommended_Budget_$": 252.43,
      "Priority_Score": 73.5,
      "Priority_Tier": "Urgent",
      "Priority_Rank": 1
    }
  ]
}
```

#### Response (400 Bad Request)
```json
{
  "status": "error",
  "message": "Unsupported file format. Only CSV files are supported."
}
```

---

### 2.5 Customer Prioritization (`POST /api/prioritize`)

Scores and ranks a cohort of customers using a composite index of churn probability and customer lifetime value (CLV).

**Headers:** `Content-Type: application/json`

#### Request Payload
```json
{
  "customers": [
    {
      "customerID": "CUST-001",
      "tenure": 2,
      "monthly_charges": 95.0,
      "contract": "Month-to-month",
      "internet_service": "Fiber optic"
    }
  ],
  "weight_churn": 0.60,
  "weight_clv": 0.40,
  "sort_by": "Priority_Score",
  "ascending": false,
  "filters": {
    "priority_tiers": ["Urgent", "High"],
    "risk_levels": ["High Risk"]
  }
}
```

#### Response (200 OK)
```json
{
  "status": "success",
  "total_customers": 1,
  "tier_counts": {
    "Urgent": 1
  },
  "total_revenue_at_risk_$": 2448.0,
  "applied_weights": {
    "churn": 0.60,
    "clv": 0.40
  },
  "prioritized_customers": [
    {
      "customerID": "CUST-001",
      "Priority_Score": 84.5,
      "Priority_Tier": "Urgent",
      "Priority_Rank": 1,
      "Churn_Probability_%": 85.0,
      "Risk_Level": "High Risk",
      "Estimated_CLV_$": 2880.0,
      "Revenue_At_Risk_$": 2448.0
    }
  ],
  "disclaimer": "Prioritization combines statistical churn risk and expected customer value. It does not guarantee intervention success."
}
```

---

### 2.6 Retention Campaign Scenario Simulator (`POST /api/simulate_retention`)

Models portfolio-level retention scenarios under user-defined budget and effectiveness parameters.

**Headers:** `Content-Type: application/json`

#### Request Payload
```json
{
  "assumed_reduction_rate": 0.20,
  "cost_per_intervention": 25.0,
  "budget_cap": 15000.0,
  "target_cohort": ["Urgent", "High"]
}
```

#### Response (200 OK)
```json
{
  "status": "success",
  "eligible_customers": 885,
  "targeted_customers": 600,
  "total_campaign_cost_$": 15000.0,
  "remaining_budget_$": 0.0,
  "baseline_revenue_at_risk_$": 1824500.0,
  "simulated_revenue_at_risk_$": 1459600.0,
  "gross_exposure_reduction_$": 364900.0,
  "net_scenario_return_$": 349900.0,
  "return_on_retention_spend_ratio": 24.33,
  "parameters": {
    "assumed_reduction_rate": 0.20,
    "cost_per_intervention": 25.0,
    "budget_cap": 15000.0,
    "target_cohort": ["Urgent", "High"]
  },
  "disclaimer": "Hypothetical simulation based on user-defined assumptions. Model predictions describe statistical correlations and do not guarantee causal retention outcomes. Retention campaigns should be validated through randomized controlled A/B experiments."
}
```
