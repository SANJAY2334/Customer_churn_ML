# ==============================================================================
# TELECOM CUSTOMER CHURN SYSTEM - PRODUCTION DOCKERFILE
# ==============================================================================
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system utilities and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python production dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache -r requirements.txt gunicorn==23.0.0

# Copy application source code and models
COPY src/ /app/src/
COPY Data/ /app/Data/
COPY Models/ /app/Models/
COPY templates/ /app/templates/
COPY static/ /app/static/
COPY flask_app.py /app/
COPY app.py /app/

# Security hardening: Create unprivileged system user and drop root privileges
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /sbin/nologin appuser \
    && chown -R appuser:appgroup /app

USER appuser

EXPOSE 5000 8501

# Healthcheck probe using production liveness endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/api/live || exit 1

# Default execution starts Gunicorn WSGI server
CMD ["gunicorn", "--workers=4", "--bind=0.0.0.0:5000", "--access-logfile=-", "--error-logfile=-", "flask_app:app"]
