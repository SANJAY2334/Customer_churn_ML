# Model Card: Telecom Customer Churn Prediction Pipeline

## 1. Model Details

- **Model Name:** Telecom Customer Churn Classifier & Risk Estimator
- **Model Version:** 1.0.0
- **Model Date:** October 2026
- **Model Type:** Supervised Binary Classification with Scikit-Learn Pipeline (`ColumnTransformer` + Estimator)
- **Active Production Estimator:** XGBoost Classifier (`XGBClassifier`, `n_estimators=100`, `learning_rate=0.05`, `max_depth=5`, `threshold_ = 0.3236`) loaded by default in both standalone `.pkl` and multi-model `.joblib`.
- **Alternative Baseline & Ensemble Estimators:** Logistic Regression (`threshold_ = 0.3081`), Random Forest (`threshold_ = 0.3255`), Decision Tree (`threshold_ = 0.3571`), Most Frequent Baseline (`DummyClassifier`).
- **Serialization Format:** `joblib` (.joblib and .pkl)
- **License / Usage:** Internal telecom analytics & customer success operations

---

## 2. Intended Use & Target Audience

### Primary Intended Uses
- Estimating the probability of individual customer attrition within a 12-to-24 month operational planning horizon.
- Categorizing customers into operational risk tiers (Low Risk: $\le 30\%$, Medium Risk: $31-60\%$, High Risk: $> 60\%$).
- Identifying the primary feature drivers associated with churn probability for targeted retention campaigns.
- Estimating financial exposure (Customer Lifetime Value and Revenue at Risk) to prioritize high-value retention interventions.

### Out-of-Scope & Prohibited Uses
- Automated termination of customer accounts.
- Credit scoring, identity verification, or external creditworthiness assessments.
- Using predictions as proof of contractual breach.
- Guaranteeing retention outcomes without treatment-effect intervention trials.

---

## 3. Training & Evaluation Data

- **Source Dataset:** IBM Telco Customer Churn Dataset (`Data/processed_data.csv`)
- **Total Dataset Size:** 7,043 customer records
- **Class Distribution:**
  - `0` (Stayed / Retained): 5,174 rows (73.46%)
  - `1` (Churned / Left): 1,869 rows (26.54%)
- **Data Partitions:**
  - **Training Set:** 80% (5,634 rows), stratified by target class.
  - **Held-Out Test Set:** 20% (1,409 rows), stratified by target class.
- **Leakage Prevention:**
  - Target column (`Churn Value`) and identical alias (`Churn Label_Yes`) strictly separated before preprocessing.
  - Preprocessing parameters (medians, scaling means, variances) fitted strictly on `X_train`.

---

## 4. Input Features Schema (30 Features)

| Feature Name | Type | Processing | Description |
|---|---|---|---|
| `Tenure Months` | Continuous (float) | `SimpleImputer(median)` + `StandardScaler` | Months customer has stayed with company |
| `Monthly Charges` | Continuous (float) | `SimpleImputer(median)` + `StandardScaler` | Monthly recurring subscription fee ($) |
| `Total Charges` | Continuous (float) | `SimpleImputer(median)` + `StandardScaler` | Total charges accumulated over tenure ($) |
| Demographics (4) | Binary (0/1) | Categorical imputation / passthrough | `Gender_Male`, `Senior Citizen_Yes`, `Partner_Yes`, `Dependents_Yes` |
| Phone Services (3) | Binary (0/1) | Categorical imputation / passthrough | `Phone Service_Yes`, `Multiple Lines_No phone service`, `Multiple Lines_Yes` |
| Internet Services (2) | Binary (0/1) | Categorical imputation / passthrough | `Internet Service_Fiber optic`, `Internet Service_No` |
| Add-on Services (12) | Binary (0/1) | Categorical imputation / passthrough | Security, Backup, Protection, Support, TV, Movies |
| Contract & Billing (3) | Binary (0/1) | Categorical imputation / passthrough | `Contract_One year`, `Contract_Two year`, `Paperless Billing_Yes` |
| Payment Methods (3) | Binary (0/1) | Categorical imputation / passthrough | `Payment Method_Credit card (automatic)`, `Electronic check`, `Mailed check` |

---

## 5. Decision Threshold Optimization Methodology

**Anti-Leakage Guarantee:** The classification decision threshold is optimized strictly via **5-fold Stratified Cross-Validation on the training fold (`X_train`)**, selecting the threshold that maximizes the validation F1 score. The threshold is never tuned on or exposed to the held-out test split.

| Model Candidate | CV Optimal Threshold | Held-Out Test F1 | Held-Out Test Recall | Held-Out Test Precision | Held-Out Test ROC-AUC |
|---|---|---|---|---|---|
| **Baseline (Most Frequent)** | 0.5000 | 0.0000 | 0.0000 | 0.0000 | 0.5000 |
| **Logistic Regression** | **0.3081** | **0.6218** | **0.7406** | **0.5358** | **0.8489** |
| **Decision Tree** | 0.3571 | 0.6265 | 0.7086 | 0.5614 | 0.8373 |
| **Random Forest** | 0.3255 | 0.6374 | 0.7567 | 0.5507 | 0.8522 |
| **XGBoost** | **0.3236** | **0.6389** | **0.7594** | **0.5515** | **0.8572** |

*Key finding:* Applying the CV-tuned optimal threshold (0.3081 for Logistic Regression, 0.3236 for XGBoost) improves churner recall on the untouched test set from 57.2% to 74.1-75.9%, capturing nearly 76% of at-risk customers compared to standard 0.50 cutoff.

---

## 6. Financial Calculations & Assumptions

1. **Customer Lifetime Value (CLV):**
   $$\text{CLV} = \text{Monthly Charges} \times \max(12.0, 36.0 - \min(\text{Tenure}, 24.0))$$
   *Assumption:* Expected lifespan horizon baseline is 36 months, decreasing as tenure accumulates, bounded by a 12-month minimum floor.
2. **Revenue at Risk:**
   $$\text{Revenue at Risk} = \text{CLV} \times P(\text{Churn})$$
   *Assumption:* Expected probabilistic financial exposure, not guaranteed lost revenue.
3. **Recommended Retention Budget:**
   $$\text{Budget} = \text{Revenue at Risk} \times 15\%$$
   *Assumption:* 15% maximum commercial allowance policy for retention offers.

---

## 7. Retention Prioritization & Scenario Simulation (Phase 2)

### Composite Retention Priority Score
$$\text{Priority Score} = 100 \times \left( w_{\text{churn}} \times P(\text{Churn}) + w_{\text{clv}} \times \min\left(1.0, \frac{\text{CLV}}{\text{CLV}_{\max}}\right) \right)$$
- Defaults: $w_{\text{churn}} = 0.60$, $w_{\text{clv}} = 0.40$, $\text{CLV}_{\max} = \$3,000$ (or cohort 95th percentile).
- Prioritization Tiers:
  - **Urgent:** High Risk ($P \ge 0.60$) AND High Value (CLV $\ge$ 75th percentile), or Priority Score $\ge 75$.
  - **High:** Priority Score $\ge 50$.
  - **Medium:** Priority Score $\ge 30$.
  - **Low:** Priority Score $< 30$.

### Retention Campaign Scenario Simulator
$$\text{Campaign Cost} = \min(N_{\text{targeted}} \times \text{Cost per Intervention}, \text{Budget Cap})$$
$$\text{Gross Exposure Saved} = \sum_{i \in \text{Targeted}} \text{Revenue\_At\_Risk}_i \times \text{Assumed Churn Reduction Rate}$$
$$\text{Net Scenario Return} = \text{Gross Exposure Saved} - \text{Campaign Cost}$$

---

## 8. Limitations & Caveats

1. **Static Historical Data:** The dataset reflects a single snapshot. Temporal drift, seasonal changes, or macro-economic pricing changes will degrade model calibration over time.
2. **Correlation vs. Causation:** Identified feature drivers (e.g., Electronic Check payment or Month-to-month contracts) reflect empirical correlation with churn, not proof of causation.
3. **Counterfactual Simulation:** What-if scenario simulations estimate model sensitivity under hypothetical input modifications; they do not replace A/B testing or randomized controlled trials.
