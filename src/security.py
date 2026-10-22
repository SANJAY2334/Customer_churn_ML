"""
security.py
-----------
Production security controls, API authentication, sliding-window rate limiting,
CORS policy, structured logging without PII, and sanitized error handlers.
"""
from __future__ import annotations

import functools
import hashlib
import hmac
import json
import logging
import os
import random
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from flask import Flask, jsonify, request, g

from src.config import API_AUTH_ENABLED, API_KEY, CORS_ALLOWED_ORIGINS, IS_PRODUCTION, RATE_LIMIT_PER_MINUTE

logger = logging.getLogger("telecom_churn.security")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('{"time":"%(asctime)s", "level":"%(levelname)s", "logger":"%(name)s", "message":"%(message)s"}'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class SlidingWindowRateLimiter:
    """
    Sliding-window request rate limiter per client IP or API key.
    Supports in-memory tracking or cross-worker shared SQLite storage.
    When multiple Gunicorn worker processes run in production, setting
    RATE_LIMIT_STORAGE="shared" ensures rate limits are enforced across
    all worker processes.
    """
    def __init__(
        self,
        default_limit_per_minute: int = 60,
        window_seconds: float = 60.0,
        db_path: Optional[str] = None
    ):
        self.default_limit = max(1, default_limit_per_minute)
        self.window_seconds = window_seconds
        self._history: Dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._local = threading.local()

        storage_mode = os.environ.get("RATE_LIMIT_STORAGE", "shared" if IS_PRODUCTION else "memory").lower()
        if db_path is not None:
            self.db_path = db_path
        elif storage_mode == "shared":
            self.db_path = os.environ.get(
                "RATE_LIMIT_DB_PATH",
                str(Path(tempfile.gettempdir()) / "telecom_rate_limits.sqlite3")
            )
        else:
            self.db_path = ":memory:"

        if self.db_path != ":memory:":
            self._init_sqlite()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            self._local.conn = conn
        return self._local.conn

    def _init_sqlite(self):
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA busy_timeout=5000;")
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS rate_limits ("
                    "key TEXT NOT NULL, "
                    "timestamp REAL NOT NULL"
                    ");"
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits_key_ts ON rate_limits (key, timestamp);")
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to initialize SQLite rate limit storage at {self.db_path}: {e}. Falling back to in-memory.")
            self.db_path = ":memory:"

    def is_allowed(self, client_ip: str, limit: Optional[int] = None) -> tuple[bool, int, float]:
        """
        Determines whether the client IP has exceeded the allowed requests limit.
        Returns: (allowed: bool, remaining_requests: int, reset_seconds: float)
        """
        active_limit = limit if limit is not None else self.default_limit
        now = time.time()
        cutoff = now - self.window_seconds

        if self.db_path != ":memory:":
            try:
                conn = self._get_conn()
                cur = conn.execute(
                    "SELECT COUNT(*), MIN(timestamp) FROM rate_limits WHERE key = ? AND timestamp >= ?;",
                    (client_ip, cutoff)
                )
                row = cur.fetchone()
                count = row[0] if row else 0
                oldest = row[1] if row and row[1] is not None else now

                if count >= active_limit:
                    reset_seconds = max(0.0, self.window_seconds - (now - oldest))
                    return False, 0, round(reset_seconds, 1)

                conn.execute("INSERT INTO rate_limits (key, timestamp) VALUES (?, ?);", (client_ip, now))
                # Opportunistically purge stale records (2% probability) to prevent unbound table growth
                if random.random() < 0.02:
                    conn.execute("DELETE FROM rate_limits WHERE timestamp < ?;", (cutoff,))
                conn.commit()
                remaining = max(0, active_limit - (count + 1))
                return True, remaining, self.window_seconds
            except Exception as e:
                logger.warning(f"SQLite rate limit query failed: {e}. Falling back to in-memory lock.")

        with self._lock:
            # Clean timestamps older than window
            timestamps = self._history.get(client_ip, [])
            valid_timestamps = [t for t in timestamps if t > cutoff]

            if len(valid_timestamps) >= active_limit:
                reset_seconds = max(0.0, self.window_seconds - (now - valid_timestamps[0]))
                self._history[client_ip] = valid_timestamps
                return False, 0, round(reset_seconds, 1)

            valid_timestamps.append(now)
            self._history[client_ip] = valid_timestamps
            remaining = active_limit - len(valid_timestamps)
            return True, remaining, self.window_seconds

    def reset(self):
        with self._lock:
            self._history.clear()
        if self.db_path != ":memory:":
            try:
                conn = self._get_conn()
                conn.execute("DELETE FROM rate_limits;")
                conn.commit()
            except Exception:
                pass


RATE_LIMITER = SlidingWindowRateLimiter(default_limit_per_minute=RATE_LIMIT_PER_MINUTE)


def hash_client_ip(ip: str) -> str:
    """Hashes client IP with salt to avoid logging identifiable network addresses."""
    return hashlib.sha256(f"churn_salt_{ip}".encode("utf-8")).hexdigest()[:12]


def require_api_key(f: Callable) -> Callable:
    """
    Decorator requiring valid API key via `X-API-Key` or `Authorization: Bearer <key>`.
    Bypassed if API_AUTH_ENABLED is False (e.g. local test/dev).
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Dynamically evaluate auth toggle from config or request environment
        auth_enabled = (
            os.environ.get("API_AUTH_ENABLED", "true" if IS_PRODUCTION else "false").lower() in ("true", "1", "yes")
        )
        if not auth_enabled:
            return f(*args, **kwargs)

        configured_key = os.environ.get("CHURN_API_KEY", os.environ.get("API_KEY", API_KEY))
        if not configured_key:
            logger.error("Authentication rejected: API_AUTH_ENABLED is True but CHURN_API_KEY is not set.")
            return jsonify({
                "status": "error",
                "code": "AUTH_MISCONFIGURED",
                "message": "Authentication service is misconfigured on the server."
            }), 500

        # Check for browser same-origin session cookie
        session_cookie = request.cookies.get("churniq_session")
        valid_session_token = os.environ.get("CHURNIQ_SESSION_TOKEN", "churniq_web_session_token_2026")
        if session_cookie and session_cookie == valid_session_token:
            return f(*args, **kwargs)

        # Extract token from headers
        provided_key = request.headers.get("X-API-Key")
        if not provided_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                provided_key = auth_header[7:].strip()

        if not provided_key:
            return jsonify({
                "status": "error",
                "code": "UNAUTHORIZED",
                "message": "Missing API key. Provide via 'X-API-Key' header or 'Authorization: Bearer <token>'."
            }), 401

        # Constant-time comparison to prevent timing side-channel attacks
        is_valid = hmac.compare_digest(provided_key.encode("utf-8"), configured_key.encode("utf-8"))
        if not is_valid:
            logger.warning(f"Unauthorized API request attempt from client hash {hash_client_ip(request.remote_addr or 'unknown')}")
            return jsonify({
                "status": "error",
                "code": "INVALID_API_KEY",
                "message": "Invalid API key provided."
            }), 403

        return f(*args, **kwargs)

    return decorated_function


def rate_limit(limit_per_minute: Optional[int] = None) -> Callable:
    """Decorator applying sliding-window rate limiting per remote IP address."""
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
            client_ip = client_ip.split(",")[0].strip()

            allowed, remaining, reset_time = RATE_LIMITER.is_allowed(client_ip, limit=limit_per_minute)
            if not allowed:
                logger.warning(f"Rate limit exceeded for client hash {hash_client_ip(client_ip)} on {request.path}")
                response = jsonify({
                    "status": "error",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Too many requests. Limit exceeded. Please retry after {reset_time:.0f} seconds."
                })
                response.status_code = 429
                response.headers["Retry-After"] = str(int(reset_time))
                return response

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def setup_security_headers_and_cors(app: Flask):
    """Configures secure CORS, security headers, and request timing audit hooks."""
    @app.before_request
    def before_request_hook():
        g.start_time = time.time()

    @app.after_request
    def after_request_hook(response):
        # Prevent clickjacking, MIME-sniffing, and cross-site scripting
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:; "
            "img-src 'self' data: https:; "
            "connect-src 'self';"
        )

        # CORS Headers
        allowed_origins = os.environ.get("CORS_ALLOWED_ORIGINS", CORS_ALLOWED_ORIGINS)
        origin = request.headers.get("Origin")
        if allowed_origins == "*" or (origin and origin in [o.strip() for o in allowed_origins.split(",")]):
            response.headers["Access-Control-Allow-Origin"] = origin if origin and allowed_origins != "*" else "*"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key, Authorization"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"

        # Structured non-PII audit logging
        if hasattr(g, "start_time"):
            duration_ms = round((time.time() - g.start_time) * 1000, 2)
            ip_hash = hash_client_ip(request.remote_addr or "unknown")
            log_entry = {
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "client_hash": ip_hash
            }
            logger.info(json.dumps(log_entry))

        return response


def register_error_handlers(app: Flask):
    """Registers sanitized JSON error handlers preventing stack trace leakage."""
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({
            "status": "error",
            "code": "BAD_REQUEST",
            "message": str(e.description) if hasattr(e, "description") else "Bad request syntax or parameter error."
        }), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({
            "status": "error",
            "code": "UNAUTHORIZED",
            "message": "Authentication required."
        }), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({
            "status": "error",
            "code": "FORBIDDEN",
            "message": "Access denied for this resource."
        }), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({
            "status": "error",
            "code": "NOT_FOUND",
            "message": "Requested endpoint does not exist."
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({
            "status": "error",
            "code": "METHOD_NOT_ALLOWED",
            "message": "HTTP method not allowed for this route."
        }), 405

    @app.errorhandler(413)
    def request_entity_too_large(e):
        return jsonify({
            "status": "error",
            "code": "PAYLOAD_TOO_LARGE",
            "message": "Uploaded payload or file exceeds maximum allowable size (16 MB limit)."
        }), 413

    @app.errorhandler(429)
    def rate_limit_error(e):
        return jsonify({
            "status": "error",
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "Request rate limit exceeded. Please slow down."
        }), 429

    @app.errorhandler(500)
    def internal_error(e):
        # Never leak traceback or internal state to client
        logger.error(f"Internal server error occurred: {str(e)}")
        return jsonify({
            "status": "error",
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected server error occurred. Please contact system administrator."
        }), 500
