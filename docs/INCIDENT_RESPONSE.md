# Production Incident Response & Rollback Runbook

## 1. Overview & Severity Definitions

This runbook guides on-call engineers, MLOps personnel, and backend developers in diagnosing and resolving production incidents affecting the Telecom Customer Churn Prediction platform.

| Severity | Definition | Target MTTR | Example Triggers |
| :--- | :--- | :--- | :--- |
| **SEV-1 (Critical)** | Complete service outage or prediction failure | < 30 minutes | `/api/live` failing, container crashloop, corrupt model artifact |
| **SEV-2 (High)** | Severe degradation or critical model drift | < 2 hours | `/api/ready` 503, RED drift alert ($\text{PSI} \ge 0.25$), auth bypass attempt |
| **SEV-3 (Medium)** | Non-blocking degradation or minor feature drift | < 24 hours | Rate limit burst, YELLOW drift alert, non-critical log warning |

---

## 2. Common Incident Playbooks

### Playbook A: Liveness Probe Failure (`/api/live` returns non-200 or times out)
1. **Check Container Status**:
   ```bash
   docker compose ps
   ```
2. **Inspect Gunicorn / Flask Logs**:
   ```bash
   docker compose logs --tail=100 -f flask_api
   ```
3. **Common Root Causes**:
   - Out-of-memory (OOM) killed by kernel: check `dmesg -T | grep -i oom`.
   - Port collision on host port 5000: verify `netstat -ano | findstr :5000` or `lsof -i :5000`.
4. **Resolution**:
   - Restart container: `docker compose restart flask_api`.
   - If persistent, review memory limits in `docker-compose.yml` or check for leaked worker processes.

---

### Playbook B: Readiness Probe Failure (`/api/ready` returns 503 Service Unavailable)
1. **Inspect Readiness JSON Output**:
   ```bash
   curl -s -H "X-API-Key: $API_KEY" http://localhost:5000/api/ready
   ```
2. **Interpret Failure Details**:
   - `artifact_integrity.status: false`: Model file missing, corrupted, or SHA-256 mismatch.
   - `synthetic_inference.status: false`: Model deserialized, but inference crashed or output dimensions were invalid.
3. **Immediate Mitigation**:
   - Verify file checksum on disk:
     ```bash
     sha256sum Models/churn_model.pkl
     ```
   - Expected SHA-256: `a9f0053a700de50daab7c453f4bd690d7cd09ad0c10927240234a4895d791363`.
   - If corrupted, restore artifact from verified backup (see Section 3).

---

### Playbook C: RED Drift Alert ($\text{PSI} \ge 0.25$)
1. **Query Active Drift Metrics**:
   ```bash
   curl -s -H "X-API-Key: $API_KEY" "http://localhost:5000/api/monitoring/drift"
   ```
2. **Identify Impacted Feature**:
   - Check which feature exhibits high PSI (e.g. `TotalCharges` or `tenure`).
   - Determine if source telemetry format changed (e.g. currency conversion, scaling factor, or new plan structure).
3. **Decision Matrix**:
   - If data pipeline defect: Fix upstream pipeline; model behavior remains valid.
   - If genuine customer behavior shift: Initiate model retraining run on new cohort.

---

## 3. Rollback Runbook

### Scenario 1: Model Artifact Rollback (Hot-Swap without Redeployment)
If a newly deployed model artifact exhibits poor predictions or fails verification:

1. **Switch to Fallback Estimator via Environment Variable**:
   Set `ACTIVE_MODEL_KEY=logistic_regression` or `random_forest` in `.env`:
   ```bash
   ACTIVE_MODEL_KEY=logistic_regression
   ```
2. **Restart Services to Pick Up Fallback Model**:
   ```bash
   docker compose up -d --no-deps flask_api streamlit_dashboard
   ```
3. **Verify Restored Operation**:
   ```bash
   curl -s -H "X-API-Key: $API_KEY" http://localhost:5000/api/ready
   ```

### Scenario 2: Restoring Model Artifact from Git / Backup
If `Models/churn_model.pkl` is damaged:
```bash
# Checkout verified artifact from git history
git checkout HEAD -- Models/churn_model.pkl Models/churn_models.joblib

# Verify checksum
python -c "from src.artifact_validator import verify_artifact_integrity; print(verify_artifact_integrity())"

# Restart application
docker compose restart flask_api
```

### Scenario 3: Full Container Rollback to Previous Release Tag
```bash
# Stop current stack
docker compose down

# Check out previous release commit or git tag
git checkout v2.1.0

# Rebuild and start clean containers
docker compose up --build -d
```

---

## 4. Post-Incident Review (PIR) Checklist

Within 48 hours of any SEV-1 or SEV-2 resolution, complete the following:
1. **Timeline of Events**: Exact timestamps of alert firing, page acknowledgment, diagnostic actions, and mitigation.
2. **Root Cause Analysis (RCA)**: Identify the 5 Whys behind the failure.
3. **Impact Assessment**: Number of impacted API calls, 5xx errors served, and customer predictions delayed.
4. **Action Items**: Preventative measures (new unit tests, tighter health check timeouts, enhanced rate limit tuning).
