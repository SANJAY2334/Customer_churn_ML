# Production Deployment Guide

## 1. Deployment Architecture Overview

The Telecom Customer Churn Prediction and Decision Support system is designed as a decoupled, multi-tier microservice architecture:

```
[ Client / Browser / API Consumer ]
                │
                │ HTTPS (TLS 1.2/1.3 on Port 443)
                ▼
       [ NGINX Reverse Proxy ]
         │                  │
         │ /                │ /dashboard/
         ▼                  ▼
[ Flask REST API ]   [ Streamlit UI ]
(Gunicorn WSGI:5000)   (Tornado:8501)
         │                  │
         └─────────┬────────┘
                   ▼
      [ Models/churn_model.pkl ]
         (SHA-256 Validated)
```

### Components
1. **Edge Reverse Proxy (NGINX)**:
   - Terminates TLS 1.2/1.3.
   - Enforces hardened HTTP security headers (`HSTS`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`).
   - Implements edge connection rate limiting (`limit_req_zone` 10 req/s, burst 20).
   - Routes traffic: `/` to Flask REST API, `/dashboard/` to Streamlit Business Intelligence UI.
2. **REST API Service (Flask + Gunicorn)**:
   - Production WSGI runtime with 4 worker processes.
   - Application-layer sliding-window rate limiting per API key / IP (default 60 req/min).
   - Constant-time API key authentication (`X-API-Key` or `Authorization: Bearer <key>`).
   - Model artifact SHA-256 integrity check and synthetic readiness probe.
   - Non-PII structured JSON audit logging.
3. **Analytics Dashboard (Streamlit)**:
   - Interactive business intelligence, customer ranking, and retention simulation UI.
   - Direct model loading and out-of-fold calibrated threshold integration ($\tau = 0.3236$).

---

## 2. Environment Configuration

The application strictly separates environments using environment variables:

| Variable | Development Default | Testing Default | Production Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | `development` | `testing` | `production` | Active runtime profile |
| `API_AUTH_ENABLED` | `false` | `false` | `true` | Enforces API key verification |
| `API_KEY` | *(None / Optional)* | *(None / Optional)* | **Required** (e.g. 64-char hex) | Cryptographic bearer/header secret |
| `RATE_LIMIT_PER_MINUTE` | `60` | `60` | `60` | Sliding-window request cap per key/IP |
| `ACTIVE_MODEL_KEY` | `xgboost` | `xgboost` | `xgboost` | Active model key (`xgboost`, `logistic_regression`, etc.) |
| `CHURN_DECISION_THRESHOLD` | `0.3236` | `0.3236` | `0.3236` | Calibrated decision threshold |
| `EXPECTED_ARTIFACT_SHA256` | *(Auto)* | *(Auto)* | `a9f0053a...` | SHA-256 integrity check |
| `MAX_CONTENT_LENGTH` | `16777216` | `16777216` | `16777216` | Max upload payload size (16 MB) |

A template is provided in `.env.example`.

---

## 3. Containerized Deployment with Docker Compose

### Prerequisites
- Docker Engine 20.10+
- Docker Compose 2.0+
- Valid TLS certificates in `nginx/certs/fullchain.pem` and `nginx/certs/privkey.pem`.

### Local Testing with Self-Signed Certificates
For local integration verification prior to obtaining CA-signed certificates:

```bash
mkdir -p nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/privkey.pem \
  -out nginx/certs/fullchain.pem \
  -subj "/C=US/ST=CA/L=SanFrancisco/O=Telecom/CN=localhost"
```

### Starting the Stack
1. Create and populate `.env` from template:
   ```bash
   cp .env.example .env
   # Edit .env and assign a strong API_KEY:
   # API_KEY=$(openssl rand -hex 32)
   ```
2. Build and run containers in detached mode:
   ```bash
   docker compose up --build -d
   ```
3. Verify running services:
   ```bash
   docker compose ps
   ```
4. Check service logs:
   ```bash
   docker compose logs -f flask_api
   ```

---

## 4. Standalone Deployment (Linux / VM / Virtualenv)

If deploying directly to virtual machines (e.g. AWS EC2, GCP Compute Engine, Ubuntu VM):

### 1. Create System User and Directories
```bash
sudo useradd -r -s /bin/false appuser
sudo mkdir -p /opt/telecom_churn /var/log/telecom_churn
sudo chown -R appuser:appuser /opt/telecom_churn /var/log/telecom_churn
```

### 2. Install Dependencies
```bash
cd /opt/telecom_churn
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt gunicorn
```

### 3. Systemd Service Definition (`/etc/systemd/system/churn_api.service`)
```ini
[Unit]
Description=Telecom Churn Flask API Gunicorn Service
After=network.target

[Service]
User=appuser
Group=appuser
WorkingDirectory=/opt/telecom_churn
EnvironmentFile=/opt/telecom_churn/.env
ExecStart=/opt/telecom_churn/.venv/bin/gunicorn \
    --workers 4 \
    --bind 127.0.0.1:5000 \
    --access-logfile /var/log/telecom_churn/access.log \
    --error-logfile /var/log/telecom_churn/error.log \
    flask_app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 4. Enable and Start
```bash
sudo systemctl daemon-reload
sudo systemctl enable churn_api
sudo systemctl start churn_api
sudo systemctl status churn_api
```

---

## 5. Health & Readiness Probes

The application provides dedicated probe endpoints for container orchestrators (Kubernetes, AWS ECS, GCP Cloud Run):

| Probe Endpoint | Purpose | Validation Checked | HTTP Return Codes |
| :--- | :--- | :--- | :--- |
| `GET /api/live` | **Liveness** | Process is alive and responding | `200 OK` |
| `GET /api/ready` | **Readiness** | Model artifact exists, SHA-256 matches, synthetic prediction succeeds | `200 OK` (Ready), `503 Service Unavailable` (Not Ready) |

### Kubernetes Deployment Spec Example
```yaml
livenessProbe:
  httpGet:
    path: /api/live
    port: 5000
  initialDelaySeconds: 10
  periodSeconds: 15
readinessProbe:
  httpGet:
    path: /api/ready
    port: 5000
  initialDelaySeconds: 15
  periodSeconds: 20
```

---

## 6. Pre-Flight Release Gate Checklist

Before exposing the service to external networks or customer traffic:

- [ ] `ENVIRONMENT=production` is set in the runtime environment.
- [ ] `API_AUTH_ENABLED=true` is set and verified.
- [ ] A cryptographically random `API_KEY` (minimum 32 bytes) is injected via secrets manager.
- [ ] Public TLS certificates from a trusted Certificate Authority (e.g., Let's Encrypt, DigiCert) are installed.
- [ ] Reverse proxy enforces TLS 1.2+ and redirects all HTTP port 80 traffic to HTTPS port 443.
- [ ] CORS is restricted to authorized frontend origins (`CORS_ALLOWED_ORIGINS`).
- [ ] Model artifact SHA-256 matches verified baseline `a9f0053a700de50daab7c453f4bd690d7cd09ad0c10927240234a4895d791363`.
- [ ] Automated CI test suite passes with 100% success rate (81/81 tests).
