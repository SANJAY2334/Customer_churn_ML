# Production Security Architecture & Threat Model

## 1. Security Overview

The Telecom Customer Churn Prediction platform handles sensitive customer telemetry and financial decision support data. The Phase 3 security hardening implements defense-in-depth across the transport, network, application, and model layers.

---

## 2. Security Controls & Mechanisms

### 2.1 Transport Layer Security (TLS/HTTPS)
- **Protocol Termination**: NGINX acts as the public reverse proxy, enforcing `TLSv1.2` and `TLSv1.3`. All legacy SSLv3, TLS 1.0, and TLS 1.1 protocols and weak ciphers are disabled.
- **HTTP Enforcement**: All requests to HTTP (Port 80) are redirected with HTTP 301 to HTTPS (Port 443).
- **HSTS**: `Strict-Transport-Security: max-age=31536000; includeSubDomains` is injected to mandate secure transport in client user agents.

### 2.2 Authentication & Authorization
- **Header Inspection**: Protected endpoints inspect both `X-API-Key` and `Authorization: Bearer <token>` headers.
- **Constant-Time Verification**: Comparison against the configured secret uses Python's `hmac.compare_digest()` to eliminate timing attack vectors.
- **Environment Gating**:
  - `development` / `testing`: Auth enforcement is disabled by default (`API_AUTH_ENABLED=false`) to ensure seamless local developer testing and CI pipeline execution.
  - `production`: Auth enforcement is mandatory (`API_AUTH_ENABLED=true`). Any request lacking a valid key receives `401 Unauthorized` (`AUTH_REQUIRED` or `INVALID_CREDENTIALS`).
- **Endpoint Exclusions**: Only the public documentation (`/`), OpenAPI specs (`/swagger.json`, `/docs`), and orchestrator liveness probes (`/api/live`) are unauthenticated. Model readiness (`/api/ready`), predictions, and monitoring endpoints require authentication in production.

### 2.3 Sliding-Window Rate Limiting
- **Edge Layer**: NGINX limits request bursts to 10 req/s with a burst allowance of 20 (`limit_req_zone`).
- **Application Layer**: In-memory, thread-safe sliding-window rate limiter in `src/security.py` restricts requests per API client key or client IP (default: 60 req/min).
- **HTTP 429 Responses**: Exhausted quotas return standard `429 Too Many Requests` with a compliant `Retry-After: 60` response header and structured JSON error code `RATE_LIMIT_EXCEEDED`.

### 2.4 Payload Caps & Input Validation
- **Upload Limit**: Enforced `MAX_CONTENT_LENGTH = 16 * 1024 * 1024` (16 MB). Oversized requests are rejected by NGINX and Flask with `413 Request Entity Too Large`.
- **Schema Validation**: Preprocessing modules validate feature count, data types, and numerical ranges, safely clamping negative values and imputing missing fields with validated defaults.

### 2.5 Security Headers & CORS
Every HTTP response emitted by the Flask API and NGINX includes:
- `X-Content-Type-Options: nosniff` (MIME confusion prevention)
- `X-Frame-Options: DENY` (Clickjacking prevention)
- `X-XSS-Protection: 1; mode=block` (Reflected XSS filter)
- `Referrer-Policy: strict-origin-when-cross-origin` (Referrer leakage prevention)
- `Access-Control-Allow-Origin`: Restricts allowable browser origins (configurable via `CORS_ALLOWED_ORIGINS`).

### 2.6 Error Sanitization & Non-PII Logging
- **Zero Stack Trace Leakage**: Custom error handlers intercept all exceptions (400, 401, 403, 404, 405, 413, 429, 500) and return sanitized JSON bodies. Python tracebacks and internal variable states are suppressed from external consumers.
- **Structured Non-PII Logging**:
  - Application logs emit JSON structures with timestamp, level, event, endpoint, client IP, and model key.
  - Customer identifiers (e.g. `customerID`), personal details, and raw financial values are excluded from standard audit logs.

### 2.7 Secrets Management
- Zero secrets are hardcoded in the codebase.
- `.env.example` provides an audited template with empty/placeholder keys.
- Production environments inject secrets via container runtime flags or cloud secret managers (e.g., AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault).

---

## 3. Threat Model & Residual Risks

| Threat Category | Potential Impact | Implemented Mitigation | Residual Risk & Future Hardening |
| :--- | :--- | :--- | :--- |
| **API Key Theft / Compromise** | Unauthorized invocation of prediction APIs | Constant-time auth, HTTPS-only transport, scoped API keys | Static shared keys lack rotation. Future: OAuth2/OIDC JWT tokens with short TTLs and mTLS. |
| **Denial of Service (DoS)** | Server exhaustion / memory depletion | Dual-layer rate limiting (NGINX + Flask sliding window), 16MB payload cap | Distributed DoS (DDoS) across thousands of IPs requires cloud WAF (e.g. AWS Shield, Cloudflare). |
| **Model Poisoning / Artifact Tampering** | Malicious predictions, backdoor execution | SHA-256 cryptographic checksum verified on application startup and readiness probes | If filesystem permissions are compromised, artifacts could be replaced alongside checksum. Requires read-only container rootfs. |
| **Data Poisoning / Adversarial Evasion** | Customers craft inputs to artificially mask churn risk | Out-of-fold calibration, feature distribution clipping, PSI drift detection | Subtle adversarial feature perturbation can still evade static tree models. Regular retraining required. |
| **Information Disclosure** | Leakage of proprietary ML architecture or customer data | Custom sanitized error handlers, removal of stack traces, non-PII audit logging | Model extraction attacks via high-volume synthetic queries. Mitigated by strict rate limits. |

---

## 4. Verification Evidence

Security controls are verified by automated tests in `tests/test_security.py`:
- `test_auth_enforcement_missing_key`: Validates `401 Unauthorized` when key is omitted in production mode.
- `test_auth_enforcement_invalid_key`: Validates constant-time rejection of incorrect keys.
- `test_auth_enforcement_valid_x_api_key`: Validates success with `X-API-Key`.
- `test_auth_enforcement_valid_bearer_token`: Validates success with `Authorization: Bearer <key>`.
- `test_rate_limiter_logic`: Validates sliding-window enforcement and `429` rejection with `Retry-After`.
- `test_security_headers_present`: Validates presence of HSTS, CSP, and X-Frame headers.
- `test_sanitized_error_handlers_no_stack_traces`: Validates suppression of internal tracebacks.
