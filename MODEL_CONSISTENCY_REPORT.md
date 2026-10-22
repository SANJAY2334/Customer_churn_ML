# Model Consistency & Interface Alignment Report

**Project:** Telecom Customer Churn Prediction & Risk Analysis  
**Review Type:** Independent Engineering Audit & Release Gate (Phase 1.5)  
**Status:** **PASS** (Resolved & Fully Verified)  

---

## 1. Executive Summary

An audit was conducted across the Streamlit analytics application (`app.py`), Flask REST API (`flask_app.py`), inference engine (`src/predictor.py`), batch scoring engine (`src/batch_processor.py`), serialized artifacts, and documentation.

### Initial Defect Discovered
Prior to this review, **Streamlit and Flask were running different models with different decision thresholds**:
- **Streamlit (`app.py`):** Loaded `Models/churn_models.joblib`, selected `artifact["best_model"]` (**XGBoost**), and applied a decision threshold of **0.3236**.
- **Flask REST API (`flask_app.py`):** Loaded `Models/churn_model.pkl` directly, which contained **Logistic Regression**, and applied a decision threshold of **0.3081**.
- **Consequence:** Identical customer input data yielded different probability scores ($87.6\%$ in Streamlit vs $83.9\%$ in Flask) and potentially divergent classifications.

### Resolution Implemented
1. Centralized model configuration was established in [`src/config.py`](file:///c:/Users/Sanjay%20R/Downloads/Telecom_Churn_ML-main/src/config.py) (`ACTIVE_MODEL_NAME = os.environ.get("CHURN_ACTIVE_MODEL", "auto")`).
2. Both `Models/churn_models.joblib` and `Models/churn_model.pkl` were synchronized to the canonical top-performing pipeline (**XGBoost**, optimal threshold **0.3236**).
3. Both `app.py` and `flask_app.py` now invoke `load_churn_model()` respecting `ACTIVE_MODEL_NAME`, guaranteeing 100% identical outputs for identical customer records across all web and API interfaces.
4. Comprehensive integration tests in [`tests/test_model_consistency.py`](file:///c:/Users/Sanjay%20R/Downloads/Telecom_Churn_ML-main/tests/test_model_consistency.py) verify identical outputs across all interfaces.

---

## 2. Interface Consistency Matrix

| Prediction Interface | Active Estimator | Decision Threshold | Model Version | Output Parity Test | Audit Status |
|---|---|---|---|---|---|
| **Flask API (`/predict`)** | `XGBClassifier` | `0.3236` | `1.0.0` | [`tests/test_model_consistency.py::test_identical_predictions_across_interfaces`](file:///c:/Users/Sanjay%20R/Downloads/Telecom_Churn_ML-main/tests/test_model_consistency.py#L64) | **PASS** |
| **Streamlit (`app.py` Single Check)** | `XGBClassifier` | `0.3236` | `1.0.0` | [`tests/test_model_consistency.py::test_model_artifact_parity`](file:///c:/Users/Sanjay%20R/Downloads/Telecom_Churn_ML-main/tests/test_model_consistency.py#L49) | **PASS** |
| **Batch CSV Processor (`src/batch_processor.py`)** | `XGBClassifier` | `0.3236` | `1.0.0` | [`tests/test_batch_processor.py::test_batch_individual_consistency`](file:///c:/Users/Sanjay%20R/Downloads/Telecom_Churn_ML-main/tests/test_batch_processor.py#L74) | **PASS** |
| **Direct Predictor (`src/predictor.py`)** | `XGBClassifier` | `0.3236` | `1.0.0` | [`tests/test_predictor.py::test_prediction_output_structure`](file:///c:/Users/Sanjay%20R/Downloads/Telecom_Churn_ML-main/tests/test_predictor.py#L20) | **PASS** |

---

## 3. Artifact Parity & Documentation Alignment

| Artifact / Document | File Path | Designated Active Model | Documented Threshold | Verification Evidence | Audit Status |
|---|---|---|---|---|---|
| Multi-Model Artifact | `Models/churn_models.joblib` | `XGBoost` | `0.3236` | Inspect `artifact["best_model"]`, `artifact["pipeline"]`, `artifact["threshold"]` | **PASS** |
| Primary Pipeline | `Models/churn_model.pkl` | `XGBClassifier` | `0.3236` | `type(pipeline.named_steps['classifier']).__name__ == "XGBClassifier"`, `pipeline.threshold_ == 0.3236` | **PASS** |
| Evaluation Metrics JSON | `Models/model_metrics.json` | `XGBoost` | `0.3236` | `data["best_model"] == "XGBoost"`, `data["metrics"]["XGBoost"]["Optimal Threshold"] == 0.3236` | **PASS** |
| Model Card | `docs/MODEL_CARD.md` | `XGBoost` | `0.3236` | Sections 1 & 5 document XGBoost F1=0.6389, AUC=0.8572, Thresh=0.3236 | **PASS** |

---

## 4. Controlled Model Switching Verification

The system supports transparent model switching via configuration (`CHURN_ACTIVE_MODEL` environment variable or `load_churn_model(model_name="...")`):

- **Default Mode (`auto` or `XGBoost`):**
  - Estimator: `XGBClassifier(learning_rate=0.05, max_depth=5, n_estimators=100)`
  - Active Threshold: `0.3236`
  - Attribution Engine: Tree-based feature importance attribution
- **Interpretable Mode (`Logistic Regression`):**
  - Estimator: `LogisticRegression(max_iter=1500, random_state=42)`
  - Active Threshold: `0.3081`
  - Attribution Engine: Scaled log-odds coefficient attribution
  - Saved reference artifact: `Models/churn_model_logistic_regression.pkl`

Tested and verified in [`tests/test_model_consistency.py::test_explicit_model_selection_override`](file:///c:/Users/Sanjay%20R/Downloads/Telecom_Churn_ML-main/tests/test_model_consistency.py#L97).

---

## 5. Verification Verdict

**Finding:** Model choice, decision threshold, and prediction semantics are explicit, synchronized, and verified across all application interfaces.  
**Verdict:** **PASS**
