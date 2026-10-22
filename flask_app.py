"""
flask_app.py
------------
Flask REST API and Web Application Server for Customer Churn Prediction and Risk Analysis.
Includes full OpenAPI / Swagger documentation and healthcheck endpoints.
"""

import os
import json
import time
from pathlib import Path
import pandas as pd
from flask import Flask, render_template, request, jsonify, make_response, Response
from flasgger import Swagger, swag_from

from src.preprocessing import prepare_input_features
from src.predictor import (
    load_churn_model,
    predict_customer_churn,
    analyze_feature_contributions,
    generate_business_recommendations,
    calculate_financial_impact
)
from src.batch_processor import process_batch_csv
from src.prioritization import rank_customers, filter_customer_cohort
from src.simulator import simulate_retention_campaign
from src.security import (
    require_api_key,
    rate_limit,
    setup_security_headers_and_cors,
    register_error_handlers
)
from src.artifact_validator import perform_readiness_probe, verify_artifact_integrity
from src.monitoring import detect_dataset_drift
from src.customer_explorer import (
    get_overview_metrics,
    get_paginated_customers,
    generate_sample_csv,
    get_system_telemetry
)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload limit
setup_security_headers_and_cors(app)
register_error_handlers(app)

# Configure Flasgger / OpenAPI Specification
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec_1",
            "route": "/apispec_1.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/"
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Telecom Customer Churn Prediction & Risk Analysis API",
        "description": "Production REST API for evaluating telecom customer churn risk, feature attribution drivers, retention recommendations, and batch CSV scoring.",
        "version": "1.0.0",
        "contact": {
            "name": "Telecom ML Team",
            "url": "https://github.com/SANJAY2334/Customer_churn_ML"
        }
    },
    "tags": [
        {"name": "Prediction", "description": "Single customer prediction and risk scoring"},
        {"name": "Batch Processing", "description": "Batch CSV file scoring and revenue-at-risk analysis"},
        {"name": "Prioritization", "description": "Customer ranking, multi-criteria prioritization, and cohort filtering"},
        {"name": "Decision Support", "description": "Hypothetical retention campaign simulation and scenario modeling"},
        {"name": "Model Intelligence", "description": "Model metrics, comparison curves, and evaluation stats"},
        {"name": "System", "description": "Application health and status"}
    ]
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

APP_START_TIME = time.time()
MODEL_PATH = "Models/churn_model.pkl"
_CACHED_MODEL = None


def get_model():
    """Thread-safe singleton model loader caching the fitted pipeline in memory."""
    global _CACHED_MODEL
    if _CACHED_MODEL is None:
        try:
            integrity = verify_artifact_integrity(MODEL_PATH)
            if not integrity.get("valid"):
                logger.error(f"Integrity check failed for {MODEL_PATH}: {integrity.get('error')}")
                return None
            _CACHED_MODEL = load_churn_model(MODEL_PATH)
        except Exception as e:
            _CACHED_MODEL = None
            logger.warning(f"Warning: Model could not be loaded ({e}). Run train_model.py first.")
    return _CACHED_MODEL


# Warm up model at startup
model = get_model()

@app.route("/")
def home():
    """
    Web Dashboard UI
    ---
    tags:
      - System
    summary: Renders the web application dashboard interface.
    responses:
      200:
        description: HTML web page rendered successfully.
    """
    resp = make_response(render_template("index.html"))
    token = os.environ.get("CHURNIQ_SESSION_TOKEN", "churniq_web_session_token_2026")
    resp.set_cookie("churniq_session", token, httponly=True, samesite="Lax")
    return resp

@app.route("/api/live", methods=["GET"])
def liveness_check():
    """
    Kubernetes / Container Liveness Probe
    ---
    tags:
      - System
    summary: Confirms the HTTP server process is running and accepting connections.
    responses:
      200:
        description: Process is alive and healthy.
    """
    return jsonify({
        "status": "alive",
        "uptime_seconds": round(time.time() - APP_START_TIME, 2),
        "timestamp": time.time()
    }), 200

@app.route("/api/ready", methods=["GET"])
@require_api_key
def readiness_check():
    """
    Kubernetes / Container Readiness Probe
    ---
    tags:
      - System
    summary: Confirms that the model pipeline is loaded, valid, SHA-256 verified against release manifest, and responsive to inference requests.
    responses:
      200:
        description: Service is ready for production traffic.
      503:
        description: Model not loaded, checksum mismatched, or failed synthetic inference probe.
    """
    integrity = verify_artifact_integrity(MODEL_PATH)
    if not integrity.get("valid"):
        # Sanitize internal filesystem paths from error diagnostics
        raw_err = str(integrity.get("error", "Integrity check failed"))
        sanitized_err = raw_err.replace(str(ROOT), "").replace("/app/", "").replace("\\", "/").lstrip("/")
        return jsonify({
            "ready": False,
            "error": "Model artifact verification failed.",
            "diagnostic_code": "ARTIFACT_INTEGRITY_FAILURE",
            "detail": sanitized_err,
            "latency_ms": None,
            "model_name": None
        }), 503

    active_model = get_model()
    probe_result = perform_readiness_probe(active_model)
    if not probe_result.get("ready"):
        raw_err = str(probe_result.get("error", "Synthetic inference probe failed"))
        return jsonify({
            "ready": False,
            "error": "Synthetic inference probe failed.",
            "diagnostic_code": "INFERENCE_PROBE_FAILURE",
            "latency_ms": None,
            "model_name": None
        }), 503

    probe_result["artifact_integrity"] = {
        "valid": True,
        "manifest_verified": integrity.get("manifest_verified", False)
    }
    return jsonify(probe_result), 200

@app.route("/api/health", methods=["GET"])
def health_check():
    """
    Service Health Check
    ---
    tags:
      - System
    summary: Returns system health, model availability, and runtime statistics.
    responses:
      200:
        description: System is healthy and operational.
        schema:
          type: object
          properties:
            status:
              type: string
              example: healthy
            uptime_seconds:
              type: number
              example: 45.2
            model_loaded:
              type: boolean
              example: true
            model_path:
              type: string
              example: Models/churn_model.pkl
            active_model:
              type: string
              example: XGBoost
            active_threshold:
              type: number
              example: 0.3236
      503:
        description: Model artifact is missing or not loaded.
    """
    active_model = get_model()
    is_model_ready = active_model is not None
    status_code = 200 if is_model_ready else 503

    return jsonify({
        "status": "healthy" if is_model_ready else "degraded",
        "uptime_seconds": round(time.time() - APP_START_TIME, 2),
        "model_loaded": is_model_ready,
        "model_path": MODEL_PATH,
        "active_model": getattr(active_model, "model_name_", "Unknown") if is_model_ready else None,
        "active_threshold": round(float(getattr(active_model, "threshold_", 0.5)), 4) if is_model_ready else None
    }), status_code

@app.route("/predict", methods=["POST"])
@require_api_key
@rate_limit()
def predict():
    """
    Single Customer Churn Prediction & Risk Analysis
    ---
    tags:
      - Prediction
    summary: Evaluates customer attributes and predicts churn probability, risk level, action, and drivers.
    consumes:
      - application/json
      - application/x-www-form-urlencoded
    parameters:
      - in: body
        name: body
        required: true
        description: Customer demographic, service, and billing profile.
        schema:
          type: object
          required:
            - tenure
            - monthly_charges
          properties:
            tenure:
              type: number
              example: 12
              description: Total account tenure in months
            monthly_charges:
              type: number
              example: 79.85
              description: Customer monthly recurring charges in USD
            total_charges:
              type: number
              example: 958.20
              description: Total charges billed to date (optional, imputed if omitted)
            gender:
              type: string
              enum: [Male, Female]
              example: Female
            senior_citizen:
              type: string
              enum: [Yes, No]
              example: No
            partner:
              type: string
              enum: [Yes, No]
              example: No
            dependents:
              type: string
              enum: [Yes, No]
              example: No
            phone_service:
              type: string
              enum: [Yes, No]
              example: Yes
            multiple_lines:
              type: string
              enum: [Yes, No, No phone service]
              example: No
            internet_service:
              type: string
              enum: [DSL, Fiber optic, No]
              example: Fiber optic
            online_security:
              type: string
              enum: [Yes, No, No internet service]
              example: No
            online_backup:
              type: string
              enum: [Yes, No, No internet service]
              example: No
            device_protection:
              type: string
              enum: [Yes, No, No internet service]
              example: No
            tech_support:
              type: string
              enum: [Yes, No, No internet service]
              example: No
            streaming_tv:
              type: string
              enum: [Yes, No, No internet service]
              example: No
            streaming_movies:
              type: string
              enum: [Yes, No, No internet service]
              example: No
            contract:
              type: string
              enum: [Month-to-month, One year, Two year]
              example: Month-to-month
            paperless_billing:
              type: string
              enum: [Yes, No]
              example: Yes
            payment_method:
              type: string
              enum: [Electronic check, Mailed check, Bank transfer (automatic), Credit card (automatic)]
              example: Electronic check
    responses:
      200:
        description: Successful churn prediction and risk assessment.
        schema:
          type: object
          properties:
            status:
              type: string
              example: success
            prediction:
              type: string
              example: Likely to Churn
            churn_probability:
              type: number
              example: 74.5
            retain_probability:
              type: number
              example: 25.5
            risk_level:
              type: string
              example: High Risk
            risk_color:
              type: string
              example: "#ef4444"
            risk_action:
              type: string
              example: "🔴 Retention offer - Immediate Customer Success contact within 24 hours"
            recommendations:
              type: array
              items:
                type: string
            top_drivers:
              type: array
              items:
                type: object
                properties:
                  feature:
                    type: string
                    example: Contract_Month-to-month
                  impact:
                    type: number
                    example: 0.82
                  direction:
                    type: string
                    example: Increases Churn
      400:
        description: Invalid request payload or missing features.
      500:
        description: Model not initialized.
    """
    active_model = get_model()
    if active_model is None:
        return jsonify({"status": "error", "message": "Model file not found. Please train model first."}), 500

    try:
        data = request.get_json(force=True, silent=True) if request.is_json else request.form.to_dict()
        if not data:
            return jsonify({"status": "error", "message": "No input payload provided."}), 400

        # Validate numeric inputs
        try:
            tenure_val = float(data.get('tenure', 0))
            monthly_charges_val = float(data.get('monthly_charges', 0.0))
        except (ValueError, TypeError) as e:
            return jsonify({"status": "error", "message": f"Invalid numerical value: {str(e)}"}), 400

        # Prepare input dict
        inputs = {
            'tenure': tenure_val,
            'monthly_charges': monthly_charges_val,
            'total_charges': data.get('total_charges', None),
            'gender': data.get('gender', 'Female'),
            'senior_citizen': data.get('senior_citizen', 'No'),
            'partner': data.get('partner', 'No'),
            'dependents': data.get('dependents', 'No'),
            'phone_service': data.get('phone_service', 'Yes'),
            'multiple_lines': data.get('multiple_lines', 'No'),
            'internet_service': data.get('internet_service', 'Fiber optic'),
            'online_security': data.get('online_security', 'No'),
            'online_backup': data.get('online_backup', 'No'),
            'device_protection': data.get('device_protection', 'No'),
            'tech_support': data.get('tech_support', 'No'),
            'streaming_tv': data.get('streaming_tv', 'No'),
            'streaming_movies': data.get('streaming_movies', 'No'),
            'contract': data.get('contract', 'Month-to-month'),
            'paperless_billing': data.get('paperless_billing', 'Yes'),
            'payment_method': data.get('payment_method', 'Electronic check')
        }

        # Encode input features
        df_encoded = prepare_input_features(inputs)

        # Predict churn using active threshold
        pred_label, churn_proba, retain_proba, risk_level, risk_color = predict_customer_churn(
            active_model, df_encoded
        )

        # Blueprint risk action mapping
        if risk_level == "Low Risk":
            risk_action = "🟢 Normal service - Maintain current relationship & explore loyalty program"
        elif risk_level == "Medium Risk":
            risk_action = "🟡 Monitor customer - Send proactive engagement & renewal discount"
        else:
            risk_action = "🔴 Retention offer - Immediate Customer Success contact within 24 hours"

        # Generate business recommendations
        recs = generate_business_recommendations(inputs, churn_proba, risk_level)

        # Driver analysis
        top_drivers_df = analyze_feature_contributions(active_model, df_encoded, top_n=5)
        drivers_list = top_drivers_df.to_dict(orient="records")

        # Calculate financial impact estimates
        financial_est = calculate_financial_impact(inputs, churn_proba)

        response = {
            "status": "success",
            "prediction": pred_label,
            "churn_probability": round(churn_proba * 100, 1),
            "retain_probability": round(retain_proba * 100, 1),
            "risk_level": risk_level,
            "risk_color": risk_color,
            "risk_action": risk_action,
            "active_model": getattr(active_model, "model_name_", "XGBoost"),
            "threshold_applied": round(float(getattr(active_model, "threshold_", 0.5)), 4),
            "model_version": getattr(active_model, "model_version_", "1.0.0"),
            "financial_impact": financial_est,
            "recommendations": recs,
            "top_drivers": drivers_list,
            "disclaimer": "Statistical risk prediction. Model explanations show statistical correlation and do not imply causal mechanisms."
        }

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/api/batch_predict", methods=["POST"])
@require_api_key
@rate_limit(limit_per_minute=30)
def batch_predict():
    """
    Batch Customer Scoring from CSV
    ---
    tags:
      - Batch Processing
    summary: Uploads a CSV file of customer records and scores churn probability, risk level, CLV, and revenue at risk.
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: file
        type: file
        required: true
        description: CSV file containing customer records matching IBM Telco features.
    responses:
      200:
        description: Batch scoring completed successfully.
        schema:
          type: object
          properties:
            status:
              type: string
              example: success
            summary:
              type: object
              properties:
                total_records:
                  type: integer
                  example: 500
                churn_rate:
                  type: number
                  example: 26.8
                high_risk_count:
                  type: integer
                  example: 134
                total_revenue_at_risk_$:
                  type: number
                  example: 48920.50
            preview:
              type: array
              items:
                type: object
      400:
        description: Missing file or invalid CSV contents.
      500:
        description: Model not loaded.
    """
    active_model = get_model()
    if active_model is None:
        return jsonify({"status": "error", "message": "Model file not found. Please train model first."}), 500

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded in form field 'file'"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No file selected."}), 400

    if not file.filename.lower().endswith('.csv'):
        return jsonify({"status": "error", "message": "Unsupported file format. Only CSV files are supported."}), 400

    try:
        df_input = pd.read_csv(file)
        if df_input.empty:
            return jsonify({"status": "error", "message": "Uploaded CSV file is empty."}), 400

        df_scored, summary = process_batch_csv(df_input, active_model)
        
        # Convert first 20 records for preview
        records = df_scored.head(20).to_dict(orient="records")

        return jsonify({
            "status": "success",
            "summary": summary,
            "preview": records
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/api/prioritize", methods=["POST"])
@require_api_key
@rate_limit(limit_per_minute=30)
def prioritize_customers():
    """
    Retention Prioritization & Multi-Criteria Ranking
    ---
    tags:
      - Prioritization
    summary: Scores and ranks a cohort of customers using a composite index of churn risk and CLV.
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            customers:
              type: array
              items:
                type: object
              description: Array of customer records (raw or scored).
            weight_churn:
              type: number
              example: 0.60
            weight_clv:
              type: number
              example: 0.40
            sort_by:
              type: string
              example: Priority_Score
            ascending:
              type: boolean
              example: false
            filters:
              type: object
              properties:
                risk_levels:
                  type: array
                  items:
                    type: string
                priority_tiers:
                  type: array
                  items:
                    type: string
                contract_types:
                  type: array
                  items:
                    type: string
    responses:
      200:
        description: Customer cohort successfully prioritized and ranked.
      400:
        description: Invalid request payload.
      500:
        description: Model not loaded or scoring error.
    """
    active_model = get_model()
    if active_model is None:
        return jsonify({"status": "error", "message": "Model not loaded."}), 500

    data = request.get_json(force=True, silent=True) if request.is_json else {}
    if not data:
        return jsonify({"status": "error", "message": "No JSON payload provided."}), 400

    raw_customers = data.get("customers", [])
    if not raw_customers:
        # Load sample or fail gracefully
        return jsonify({"status": "error", "message": "The 'customers' list is required and cannot be empty."}), 400

    try:
        df_in = pd.DataFrame(raw_customers)
        # Check if already scored or needs batch scoring
        if 'Churn_Probability_%' not in df_in.columns and 'churn_probability' not in df_in.columns:
            df_scored, _ = process_batch_csv(df_in, active_model)
        else:
            df_scored = df_in.copy()

        weight_c = float(data.get("weight_churn", 0.60))
        weight_v = float(data.get("weight_clv", 0.40))
        sort_col = str(data.get("sort_by", "Priority_Score"))
        ascending = bool(data.get("ascending", False))

        ranked_df = rank_customers(
            df_scored,
            weight_churn=weight_c,
            weight_clv=weight_v,
            sort_by=sort_col,
            ascending=ascending,
            preserve_order=False
        )

        # Apply optional filters
        filters = data.get("filters", {})
        if filters and isinstance(filters, dict):
            ranked_df = filter_customer_cohort(
                ranked_df,
                risk_levels=filters.get("risk_levels"),
                contract_types=filters.get("contract_types"),
                priority_tiers=filters.get("priority_tiers"),
                min_tenure=filters.get("min_tenure"),
                max_tenure=filters.get("max_tenure"),
                min_monthly_charges=filters.get("min_monthly_charges"),
                max_monthly_charges=filters.get("max_monthly_charges")
            )

        tier_counts = ranked_df['Priority_Tier'].value_counts().to_dict() if 'Priority_Tier' in ranked_df.columns else {}
        total_rev_at_risk = round(float(ranked_df['Revenue_At_Risk_$'].sum()), 2) if 'Revenue_At_Risk_$' in ranked_df.columns else 0.0

        return jsonify({
            "status": "success",
            "total_customers": len(ranked_df),
            "tier_counts": tier_counts,
            "total_revenue_at_risk_$": total_rev_at_risk,
            "prioritized_customers": ranked_df.head(100).to_dict(orient="records"),
            "applied_weights": {"churn": weight_c, "clv": weight_v},
            "disclaimer": "Prioritization combines statistical churn risk and expected customer value. It does not guarantee intervention success."
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/api/simulate_retention", methods=["POST"])
@require_api_key
@rate_limit(limit_per_minute=30)
def simulate_retention():
    """
    Retention Campaign Scenario Simulator
    ---
    tags:
      - Decision Support
    summary: Simulates hypothetical portfolio retention scenarios under user-defined budget and effectiveness parameters.
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            customers:
              type: array
              items:
                type: object
              description: Optional array of customer records. If omitted, uses default processed dataset.
            assumed_reduction_rate:
              type: number
              example: 0.20
            cost_per_intervention:
              type: number
              example: 25.0
            budget_cap:
              type: number
              example: 5000.0
            target_cohort:
              type: array
              items:
                type: string
              example: ["Urgent", "High"]
    responses:
      200:
        description: Scenario simulation results.
      400:
        description: Invalid request parameters.
    """
    active_model = get_model()
    if active_model is None:
        return jsonify({"status": "error", "message": "Model not loaded."}), 500

    data = request.get_json(force=True, silent=True) if request.is_json else {}

    try:
        raw_customers = data.get("customers")
        if raw_customers:
            df_in = pd.DataFrame(raw_customers)
            if 'Churn_Probability_%' not in df_in.columns and 'churn_probability' not in df_in.columns:
                df_scored, _ = process_batch_csv(df_in, active_model)
            else:
                df_scored = df_in.copy()
                if 'Priority_Tier' not in df_scored.columns:
                    df_scored = rank_customers(df_scored, preserve_order=True)
        else:
            # Load default processed dataset
            data_path = Path(__file__).resolve().parent / "Data" / "processed_data.csv"
            if not data_path.is_file():
                return jsonify({"status": "error", "message": "Default dataset not found and no customers provided."}), 400
            df_raw = pd.read_csv(data_path).head(500)  # Use representative sample of 500 for swift response
            df_scored, _ = process_batch_csv(df_raw, active_model)

        eff_rate = float(data.get("assumed_reduction_rate", 0.20))
        cost = float(data.get("cost_per_intervention", 25.0))
        budget = float(data.get("budget_cap")) if data.get("budget_cap") is not None else None
        target_cohort = data.get("target_cohort", ["Urgent", "High"])

        res = simulate_retention_campaign(
            df_scored,
            assumed_reduction_rate=eff_rate,
            cost_per_intervention=cost,
            budget_cap=budget,
            target_cohort_column="Priority_Tier" if "Priority_Tier" in df_scored.columns else "Risk_Level",
            target_cohort_values=target_cohort
        )

        return jsonify(res), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/api/monitoring/drift", methods=["POST"])
@require_api_key
@rate_limit(limit_per_minute=20)
def check_drift():
    """
    Data & Feature Drift Monitoring Probe
    ---
    tags:
      - Model Intelligence
    summary: Evaluates Population Stability Index (PSI) drift across incoming customer data against baseline training distributions.
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            customers:
              type: array
              items:
                type: object
    responses:
      200:
        description: Feature drift assessment and alert level (GREEN, YELLOW, RED).
      400:
        description: Invalid or empty payload.
    """
    data = request.get_json(force=True, silent=True) if request.is_json else {}
    customers = data.get("customers", [])
    if not customers:
        return jsonify({"status": "error", "message": "No customer records provided for drift evaluation."}), 400

    try:
        df_curr = pd.DataFrame(customers)
        drift_report = detect_dataset_drift(df_curr)
        return jsonify(drift_report), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/api/metrics", methods=["GET"])
def get_metrics():
    """
    Model Comparison Metrics & ROC/PR Curves
    ---
    tags:
      - Model Intelligence
    summary: Returns evaluation metrics, confusion matrices, and ROC/PR curve points for all trained classifiers.
    responses:
      200:
        description: Model evaluation metrics JSON.
      404:
        description: Metrics file not found.
    """
    metrics_path = Path(__file__).resolve().parent / "Models" / "model_metrics.json"
    if metrics_path.is_file():
        with open(metrics_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data), 200
    else:
        return jsonify({"status": "error", "message": "Metrics file not found. Run train_model.py first."}), 404


@app.route("/api/overview", methods=["GET"])
def get_overview():
    """
    ChurnIQ Executive Overview Analytics
    ---
    tags:
      - Model Intelligence
    summary: Returns high-level executive KPIs, customer risk distribution, 12-month churn risk trends, and top risk factors.
    responses:
      200:
        description: Executive intelligence overview data.
    """
    return jsonify(get_overview_metrics()), 200


@app.route("/api/customers", methods=["GET"])
def get_customers():
    """
    Customer Explorer Directory
    ---
    tags:
      - Prediction
    summary: Returns searchable, filterable, paginated customer cohort records with predicted churn risk.
    parameters:
      - in: query
        name: search
        type: string
        description: Search query matching customer ID, contract, gender, etc.
      - in: query
        name: risk_level
        type: string
        enum: [All, High, Medium, Low]
        description: Filter by risk level
      - in: query
        name: contract
        type: string
        enum: [All, Month-to-month, One year, Two year]
        description: Filter by contract type
      - in: query
        name: payment_method
        type: string
        description: Filter by payment method
      - in: query
        name: page
        type: integer
        default: 1
      - in: query
        name: page_size
        type: integer
        default: 10
    responses:
      200:
        description: Paginated customer cohort records.
    """
    search = request.args.get("search", "")
    risk_level = request.args.get("risk_level", "All")
    contract = request.args.get("contract", "All")
    payment_method = request.args.get("payment_method", "All")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 10))

    result = get_paginated_customers(
        search=search,
        risk_level=risk_level,
        contract=contract,
        payment_method=payment_method,
        page=page,
        page_size=page_size
    )
    return jsonify(result), 200


@app.route("/api/sample_csv", methods=["GET"])
def download_sample_csv():
    """
    Download Sample Batch CSV
    ---
    tags:
      - Batch Processing
    summary: Generates and streams a downloadable sample CSV formatted with valid telecom customer feature records.
    responses:
      200:
        description: CSV file download.
    """
    csv_data = generate_sample_csv()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=telecom_customers_sample.csv"}
    )


@app.route("/api/system_telemetry", methods=["GET"])
def get_system_telemetry_route():
    """
    Model & System Telemetry
    ---
    tags:
      - System
    summary: Returns production model health benchmarks, feature drift PSI scores, and system resource telemetry.
    responses:
      200:
        description: System telemetry and drift stats.
    """
    return jsonify(get_system_telemetry()), 200

if __name__ == "__main__":
    print("Starting Flask Server for Customer Churn Prediction on http://127.0.0.1:5000")
    print("Interactive Swagger API Documentation available at http://127.0.0.1:5000/apidocs/")
    app.run(host="127.0.0.1", port=5000, debug=False)
