"""
test_security.py
----------------
Unit and integration tests for production security controls,
API key authentication, rate limiting, security headers, and sanitized errors.
"""
import json
import os
import pytest
from flask_app import app
from src.security import SlidingWindowRateLimiter, RATE_LIMITER


@pytest.fixture
def auth_client():
    """Client with authentication enabled in test mode."""
    os.environ["API_AUTH_ENABLED"] = "true"
    os.environ["CHURN_API_KEY"] = "secret_test_key_123"
    yield app.test_client()
    os.environ["API_AUTH_ENABLED"] = "false"
    os.environ.pop("CHURN_API_KEY", None)


def test_liveness_probe(client):
    response = client.get("/api/live")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "alive"
    assert "uptime_seconds" in data
    assert "timestamp" in data


def test_readiness_probe(client):
    response = client.get("/api/ready")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["ready"] is True
    assert "latency_ms" in data
    assert data["model_name"] == "XGBoost"
    assert data["threshold"] == 0.3236


def test_auth_enforcement_missing_key(auth_client):
    response = auth_client.post("/predict", json={"tenure": 12, "monthly_charges": 70.0})
    assert response.status_code == 401
    data = json.loads(response.data)
    assert data["status"] == "error"
    assert data["code"] == "UNAUTHORIZED"


def test_auth_enforcement_invalid_key(auth_client):
    headers = {"X-API-Key": "wrong_key_999"}
    response = auth_client.post("/predict", json={"tenure": 12, "monthly_charges": 70.0}, headers=headers)
    assert response.status_code == 403
    data = json.loads(response.data)
    assert data["code"] == "INVALID_API_KEY"


def test_auth_enforcement_valid_x_api_key(auth_client):
    headers = {"X-API-Key": "secret_test_key_123"}
    response = auth_client.post("/predict", json={"tenure": 12, "monthly_charges": 70.0}, headers=headers)
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"


def test_auth_enforcement_valid_bearer_token(auth_client):
    headers = {"Authorization": "Bearer secret_test_key_123"}
    response = auth_client.post("/predict", json={"tenure": 12, "monthly_charges": 70.0}, headers=headers)
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"


def test_rate_limiter_logic():
    limiter = SlidingWindowRateLimiter(default_limit_per_minute=3, window_seconds=60.0)
    test_ip = "192.168.1.100"

    # First 3 requests allowed
    ok1, rem1, _ = limiter.is_allowed(test_ip)
    ok2, rem2, _ = limiter.is_allowed(test_ip)
    ok3, rem3, _ = limiter.is_allowed(test_ip)
    assert ok1 and ok2 and ok3
    assert rem3 == 0

    # 4th request rejected
    ok4, rem4, reset = limiter.is_allowed(test_ip)
    assert not ok4
    assert rem4 == 0
    assert reset > 0


def test_security_headers_present(client):
    response = client.get("/api/live")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in response.headers


def test_sanitized_error_handlers_no_stack_traces(client):
    # Non-existent route
    response = client.get("/api/non_existent_route_404")
    assert response.status_code == 404
    data = json.loads(response.data)
    assert data["status"] == "error"
    assert data["code"] == "NOT_FOUND"
    assert "Traceback" not in response.get_data(as_text=True)


def test_shared_sqlite_rate_limiter_across_workers(tmp_path):
    """Verifies that multiple worker processes/instances share state via SQLite backend."""
    db_file = str(tmp_path / "shared_rate_limits.sqlite3")
    worker1 = SlidingWindowRateLimiter(default_limit_per_minute=2, window_seconds=60.0, db_path=db_file)
    worker2 = SlidingWindowRateLimiter(default_limit_per_minute=2, window_seconds=60.0, db_path=db_file)

    ip = "192.168.10.50"
    # Request 1 via worker 1 -> allowed (1 remaining)
    allowed, rem, _ = worker1.is_allowed(ip, limit=2)
    assert allowed is True
    assert rem == 1

    # Request 2 via worker 2 -> allowed (0 remaining)
    allowed, rem, _ = worker2.is_allowed(ip, limit=2)
    assert allowed is True
    assert rem == 0

    # Request 3 via worker 1 -> rejected across both workers!
    allowed, rem, reset_secs = worker1.is_allowed(ip, limit=2)
    assert allowed is False
    assert rem == 0
    assert reset_secs > 0

    # Request 4 via worker 2 -> also rejected!
    allowed, rem, _ = worker2.is_allowed(ip, limit=2)
    assert allowed is False
    assert rem == 0
