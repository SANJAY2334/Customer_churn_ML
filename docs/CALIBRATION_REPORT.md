# Probability Calibration & ML Correctness Report

**Project:** Telecom Customer Churn Prediction & Risk Analysis  
**Review Type:** Independent Engineering Audit & Release Gate (Phase 1.5)  
**Evaluation Partition:** Held-out test split (1,409 customers; 1,035 Retained, 374 Churned)  
**Status:** **PASS** (Empirically Measured & Verified)  

---

## 1. Methodology & Anti-Leakage Verification

To guarantee scientific validity and prevent optimistic bias:
1. **Preprocessing Isolation:** All numerical imputations, scalers (`StandardScaler`), and categorical handlers are fitted **exclusively on the training partition (`X_train`)**.
2. **Threshold Tuning Isolation:** Optimal decision thresholds are identified exclusively via **5-fold Stratified Cross-Validation on `X_train`**. The test partition is never evaluated during hyperparameter search or threshold selection.
3. **Unseen Test Evaluation:** Calibration metrics, Brier scores, log loss, and reliability curves are measured strictly on the **untouched held-out test partition (`X_test`, `y_test`)**.

---

## 2. Quantitative Calibration Benchmark

| Model Candidate | Brier Score $\downarrow$ | Log Loss $\downarrow$ | 10-Bin ECE $\downarrow$ | Calibration Quality Assessment |
|---|---|---|---|---|
| **Baseline (Most Frequent)** | 0.2654 | 9.1679 | 0.2654 | Uninformative (outputs constant zero probability) |
| **Logistic Regression** | 0.1357 | 0.4123 | 0.0490 | Well-calibrated sigmoidal curve |
| **Decision Tree** | 0.1387 | 0.5353 | 0.0526 | Coarse step-function probabilities |
| **Random Forest** | 0.1335 | 0.4094 | 0.0362 | Well-calibrated ensemble probabilities |
| **XGBoost (Active Model)** | **0.1318** | **0.4014** | **0.0230** | **Superior calibration across all bins (ECE: 2.3%)** |

*Note on metrics:*
- **Brier Score:** Mean squared difference between predicted probability and actual binary label ($0.0$ is perfect calibration; random guessing at prior class balance is $\approx 0.195$).
- **Log Loss:** Cross-entropy penalty reflecting probability confidence.
- **Expected Calibration Error (ECE):** Weighted average deviation between bin-predicted probabilities and empirical observed frequencies across 10 uniform probability intervals $[0, 1]$.

---

## 3. Reliability Curve Data (XGBoost vs. Logistic Regression)

### Active Model: XGBoost (10 Uniform Bins)

| Probability Bin | Mean Predicted Probability ($P_{pred}$) | Empirical Observed Churn Fraction ($P_{true}$) | Absolute Bin Error $|P_{pred} - P_{true}|$ |
|---|---|---|---|
| Bin 1 ($0.0 - 0.1$) | 0.0320 (3.2%) | 0.0357 (3.6%) | 0.0037 (0.4%) |
| Bin 2 ($0.1 - 0.2$) | 0.1468 (14.7%) | 0.1506 (15.1%) | 0.0038 (0.4%) |
| Bin 3 ($0.2 - 0.3$) | 0.2446 (24.5%) | 0.2593 (25.9%) | 0.0147 (1.5%) |
| Bin 4 ($0.3 - 0.4$) | 0.3465 (34.7%) | 0.3496 (35.0%) | 0.0031 (0.3%) |
| Bin 5 ($0.4 - 0.5$) | 0.4502 (45.0%) | 0.4065 (40.7%) | 0.0437 (4.4%) |
| Bin 6 ($0.5 - 0.6$) | 0.5512 (55.1%) | 0.5294 (52.9%) | 0.0218 (2.2%) |
| Bin 7 ($0.6 - 0.7$) | 0.6453 (64.5%) | 0.6627 (66.3%) | 0.0174 (1.7%) |
| Bin 8 ($0.7 - 0.8$) | 0.7459 (74.6%) | 0.7541 (75.4%) | 0.0082 (0.8%) |
| Bin 9 ($0.8 - 0.9$) | 0.8439 (84.4%) | 0.8200 (82.0%) | 0.0239 (2.4%) |
| Bin 10 ($0.9 - 1.0$) | 0.9099 (91.0%) | 1.0000 (100.0%) | 0.0901 (9.0%) |

**Finding:** The reliability curve closely tracks the ideal diagonal ($y = x$). In 8 out of 10 bins, the error between predicted probability and actual churn rate is under 2.5 percentage points.

---

## 4. Classification Metrics vs. Calibrated Probabilities

A critical engineering distinction must be maintained between classification metrics and calibrated probabilities:

1. **Classification Performance (F1, Precision, Recall):**
   - Depends strictly on the chosen **decision boundary** (e.g. $\tau = 0.3236$).
   - A model can have high classification F1-score even if its raw probabilities are poorly scaled, as long as ranking order is preserved.
2. **Probability Calibration:**
   - Evaluates whether the numerical value $P(\text{Churn}) = 0.70$ truly corresponds to a $70\%$ empirical attrition rate.
   - **Why this matters for Telecom Churn:** The financial simulator calculates:
     $$\text{Revenue at Risk} = \text{CLV} \times P(\text{Churn})$$
     If probabilities were systematically overconfident (e.g., predicting $90\%$ when actual risk is $50\%$), the business would vastly over-estimate financial exposure and over-allocate retention budgets.
   - **Conclusion:** Because XGBoost achieves an ECE of $2.30\%$ and Brier score of $0.1318$, its probability outputs are statistically trustworthy for proportional financial risk modeling.

---

## 5. Dataset Limitations & Scope Boundaries

1. **Cross-Sectional Static Observation:**
   - The IBM Telco dataset provides a single retrospective snapshot without event timestamps or longitudinal usage intervals.
   - Survival analysis with time-varying covariates is not possible from this data.
2. **Survivorship & Censoring:**
   - Active customers with high tenure may represent surviving cohorts who have already passed early churn friction periods.
3. **Causal Attribution Disclaimer:**
   - Feature importances and scenario adjustments reflect predictive association, not causal mechanics. For example, offering a discount does not guarantee churn prevention without intervention trial data.

---

## 6. Verification Verdict

**Finding:** Preprocessing and threshold tuning are strictly isolated to training folds; held-out evaluation shows strong probability calibration (Brier score: $0.1318$, ECE: $2.3\%$).  
**Verdict:** **PASS**
