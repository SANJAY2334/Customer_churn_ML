# Customer Churn Prediction & Risk Analysis

An enterprise-ready, leakage-free machine learning system for predicting telecom customer churn, quantifying financial risk exposure, and recommending targeted customer retention actions.

Provides both an interactive **Streamlit Analytics Dashboard** and a high-performance **Flask REST API & Swagger UI**.

---

## 1. System Architecture

```text
Telecom_Churn_ML-main/
├── app.py                      # Streamlit interactive analytics dashboard
├── flask_app.py                # Hardened Flask REST API with OpenAPI / Swagger UI
├── run_app.py                  # One-click desktop launcher
├── run.bat                     # Windows batch script launcher
├── train_model.py              # Canonical ML training, CV threshold tuning & serialization
├── train_models.py             # Backward-compatible wrapper for train_model.py
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Hardened production container image (unprivileged appuser)
├── docker-compose.yml          # Multi-container orchestration (NGINX + Flask + Streamlit)
├── .env.example                # Production environment template
├── .github/workflows/ci.yml    # CI/CD pipeline for tests and artifact verification
├── nginx/
│   └── nginx.conf              # NGINX reverse proxy, TLS termination & edge rate limiting
├── Data/
│   └── processed_data.csv       # IBM Telco Customer Churn dataset (7,043 rows, 30 features)
├── Models/
│   ├── churn_model.pkl          # Active deployed scikit-learn pipeline (XGBoost, threshold = 0.3236)
│   ├── churn_models.joblib      # Canonical multi-model artifact (LR, DT, RF, XGBoost)
│   ├── model_metrics.json       # Standardized model evaluation metrics & ROC/PR curves
│   └── backup_original/         # Safety backup of initial artifacts
├── src/
│   ├── config.py                # Centralized risk tiers, model choice, security & drift settings
│   ├── security.py              # Auth middleware, sliding-window rate limiter, error sanitizers
│   ├── artifact_validator.py    # SHA-256 cryptographic verification & readiness probes
│   ├── monitoring.py            # Population Stability Index (PSI) & drift evaluation
│   ├── batch_processor.py       # Vectorized batch scoring & aggregate reconciliation
│   ├── prioritization.py        # Composite multi-criteria customer ranking & cohort filtering
│   ├── simulator.py             # Retention campaign portfolio scenario simulator
│   ├── predictor.py             # Inference, risk categorization, SHAP/log-odds, financial logic
│   └── preprocessing.py         # 30-feature defensive customer input encoder
├── docs/
│   ├── PHASE_6_DEPLOYMENT_PREPARATION.md # Production readiness verification & deployment preparation
│   ├── PHASE_5_PRODUCTION_READINESS.md # Production readiness, cloud architecture & governance
│   ├── PHASE_4_2_PERFORMANCE_AND_RELEASE_GATE.md # Latency remediation & staging release gate
│   ├── PHASE_4_1_INDEPENDENT_RELEASE_AUDIT.md # Independent staging acceptance & security audit
│   ├── PHASE_4_STAGING_ACCEPTANCE.md # Staging release verification & production acceptance
│   ├── PHASE_3_1_DEPLOYMENT_ACCEPTANCE.md # Multi-tier Docker Compose deployment acceptance
│   ├── PHASE_3_COMPLETION_REPORT.md # Production deployment & MLOps readiness report
│   ├── DEPLOYMENT.md            # Production deployment guide (Docker, systemd, cloud)
│   ├── SECURITY.md              # Threat model, authentication, CORS, rate limiting
│   ├── MONITORING_AND_DRIFT.md  # PSI drift monitoring, degradation alerts, synthetic probes
│   ├── INCIDENT_RESPONSE.md     # On-call triage playbooks, rollback runbook & PIR
│   ├── PHASE_2_1_RELEASE_AUDIT.md # Release integrity & security audit report
│   ├── PHASE_2_KPI_RECONCILIATION.md # Mathematical KPI reconciliation report
│   ├── MODEL_CARD.md            # Detailed model card & performance metrics
│   ├── CONFIGURATION.md         # System configuration & environment variables
│   └── API_CONTRACT.md          # REST API schemas, endpoints, and error codes
├── templates/
│   └── index.html               # Flask web interface
├── static/
│   ├── script.js                # Frontend client logic
│   └── style.css                # CSS styles
└── tests/
    ├── conftest.py              # Pytest fixtures and mock customers
    ├── test_api.py              # Flask API integration tests (14 tests)
    ├── test_security.py         # Auth, headers, rate limiting & error sanitization (9 tests)
    ├── test_mlops_reliability.py # Artifact SHA-256, PSI drift & performance tests (8 tests)
    ├── test_batch_processor.py  # Batch prediction & aggregate tests (4 tests)
    ├── test_financial.py        # Financial horizon & revenue-at-risk tests (5 tests)
    ├── test_model_consistency.py # Cross-interface model consistency tests (4 tests)
    ├── test_predictor.py        # Inference, threshold & financial tests (11 tests)
    ├── test_preprocessing.py    # Feature encoding & edge-case tests (10 tests)
    ├── test_prioritization.py   # Multi-criteria ranking & filtering tests (9 tests)
    └── test_simulator.py        # Scenario simulator & budget tests (7 tests)
```

---

## 2. Quickstart & Installation

### Step 1: Set up Virtual Environment
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

### Step 2: Install Dependencies
```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Step 3: Run the Test Suite
```powershell
python -m pytest -v
```
*(All 85 tests execute and pass in ~2.6s).*

---

## 3. Model Training & Evaluation

To train the candidate classifiers (Baseline, Logistic Regression, Decision Tree, Random Forest, XGBoost), run:

```powershell
python train_model.py
```

### ML Pipeline Safeguards:
1. **Target & Leakage Isolation:** Separates `Churn Value` and aliases (`Churn Label_Yes`) before preprocessing.
2. **Train/Test Stratification:** 80% train (5,634 rows) / 20% test (1,409 rows) stratified by class.
3. **Out-of-Fold Threshold Tuning:** Optimal decision thresholds are tuned exclusively via **5-fold Stratified Cross-Validation on the training split**, avoiding test-set leakage.
4. **Held-out Evaluation:** Evaluates both default (0.50) and CV-tuned thresholds on the untouched test partition.

---

## 4. Running the Applications

### Option A: Flask REST API & Web Dashboard
```powershell
python flask_app.py
```
- **Web UI:** [http://127.0.0.1:5000/](http://127.0.0.1:5000/)
- **Interactive Swagger Docs:** [http://127.0.0.1:5000/apidocs/](http://127.0.0.1:5000/apidocs/)
- **Health Check:** [http://127.0.0.1:5000/api/health](http://127.0.0.1:5000/api/health)
- **Model Metrics:** [http://127.0.0.1:5000/api/metrics](http://127.0.0.1:5000/api/metrics)

Or use the one-click desktop launcher:
```powershell
python run_app.py
```

### Option B: Streamlit Analytics Dashboard
```powershell
streamlit run app.py
```
Opens the Streamlit dashboard on [http://localhost:8501](http://localhost:8501) for interactive model inspection, single prediction, and CSV batch scoring.

---

### Option C: Production Docker Compose Stack
```powershell
docker compose up --build -d
```
Starts NGINX (terminating TLS on port 443 with HTTP redirect on port 80), Gunicorn Flask API (port 5000 internally), and Streamlit (port 8501 internally under `/dashboard/`).

---

## 5. Technical Documentation

- [Phase 3.1 Deployment Acceptance](PHASE_3_1_DEPLOYMENT_ACCEPTANCE.md) — Live container verification, TLS audit & SRE release report.
- [Phase 3 Completion Report](PHASE_3_COMPLETION_REPORT.md) — Comprehensive production security & MLOps readiness audit.
- [Production Deployment Guide](docs/DEPLOYMENT.md) — Containerization, orchestration, and systemd deployment.
- [Security Architecture & Threat Model](docs/SECURITY.md) — Authentication, rate limiting, and defensive controls.
- [Model Monitoring & Drift Guide](docs/MONITORING_AND_DRIFT.md) — PSI drift calculation and performance degradation tracking.
- [Incident Response Runbook](docs/INCIDENT_RESPONSE.md) — On-call triage, playbooks, and rollback procedures.
- [Phase 2.1 Release Audit](docs/PHASE_2_1_RELEASE_AUDIT.md) — Release integrity & security audit report.
- [Phase 2 KPI Reconciliation](docs/PHASE_2_KPI_RECONCILIATION.md) — Mathematical KPI reconciliation report.
- [Model Card](docs/MODEL_CARD.md) — Model architecture, evaluation metrics, and ethics.
- [API Contract](docs/API_CONTRACT.md) — OpenAPI request/response schema specifications.
- [Configuration Reference](docs/CONFIGURATION.md) — Environment variables and system thresholds.

---

## 6. Financial Logic & Disclaimer

- **Customer Lifetime Value (CLV):** Estimated over a tenure-adjusted horizon: $\max(12.0, 36.0 - \min(\text{tenure}, 24.0)) \times \text{Monthly Charges}$.
- **Revenue at Risk:** Probabilistic exposure: $\text{CLV} \times P(\text{Churn})$.
- **Recommended Retention Budget:** Capped at 15% of Revenue at Risk.
- *Disclaimer:* Revenue at risk and scenario simulations represent statistical risk estimates based on model sensitivity; they do not guarantee future retention outcomes without empirical intervention trial data.
