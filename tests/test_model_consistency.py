"""
test_model_consistency.py
-------------------------
Integration tests verifying model selection consistency, threshold alignment,
and identical prediction semantics across all interfaces (Flask API, Predictor, Batch Processor, Streamlit).
"""

import json
import pytest
import numpy as np
import pandas as pd
from src.preprocessing import prepare_input_features
from src.predictor import load_churn_model, predict_customer_churn
from src.batch_processor import process_batch_csv
from src.config import ACTIVE_MODEL_NAME, DEFAULT_ARTIFACT_PATH, DEFAULT_PKL_PATH


@pytest.fixture
def test_customers():
    return [
        {
            "tenure": 1, "monthly_charges": 85.0, "total_charges": 85.0,
            "gender": "Female", "senior_citizen": "No", "partner": "No", "dependents": "No",
            "phone_service": "Yes", "multiple_lines": "No", "internet_service": "Fiber optic",
            "online_security": "No", "online_backup": "No", "device_protection": "No",
            "tech_support": "No", "streaming_tv": "Yes", "streaming_movies": "Yes",
            "contract": "Month-to-month", "paperless_billing": "Yes", "payment_method": "Electronic check"
        },
        {
            "tenure": 48, "monthly_charges": 20.0, "total_charges": 960.0,
            "gender": "Male", "senior_citizen": "No", "partner": "Yes", "dependents": "Yes",
            "phone_service": "Yes", "multiple_lines": "No", "internet_service": "No",
            "online_security": "No internet service", "online_backup": "No internet service",
            "device_protection": "No internet service", "tech_support": "No internet service",
            "streaming_tv": "No internet service", "streaming_movies": "No internet service",
            "contract": "Two year", "paperless_billing": "No", "payment_method": "Credit card (automatic)"
        },
        {
            "tenure": 12, "monthly_charges": 55.0, "total_charges": 660.0,
            "gender": "Female", "senior_citizen": "Yes", "partner": "No", "dependents": "No",
            "phone_service": "Yes", "multiple_lines": "No", "internet_service": "DSL",
            "online_security": "Yes", "online_backup": "Yes", "device_protection": "No",
            "tech_support": "No", "streaming_tv": "No", "streaming_movies": "No",
            "contract": "One year", "paperless_billing": "Yes", "payment_method": "Mailed check"
        }
    ]


def test_model_artifact_parity():
    """Confirms churn_model.pkl and churn_models.joblib resolve to consistent active model and threshold."""
    model_pkl = load_churn_model("Models/churn_model.pkl")
    model_joblib = load_churn_model("Models/churn_models.joblib")

    # Verify both pipelines use the same classifier type
    clf_pkl = model_pkl.named_steps["classifier"]
    clf_joblib = model_joblib.named_steps["classifier"]
    assert type(clf_pkl) is type(clf_joblib)

    # Verify thresholds match
    assert hasattr(model_pkl, "threshold_")
    assert hasattr(model_joblib, "threshold_")
    assert round(float(model_pkl.threshold_), 4) == round(float(model_joblib.threshold_), 4)


def test_identical_predictions_across_interfaces(client, test_customers):
    """Verifies that Flask API, direct Predictor, and Batch Processor produce identical outputs."""
    model = load_churn_model()
    threshold = getattr(model, "threshold_", 0.5)

    for customer in test_customers:
        # 1. Direct Predictor
        df_encoded = prepare_input_features(customer)
        direct_label, direct_churn_p, direct_retain_p, direct_risk, _ = predict_customer_churn(model, df_encoded)

        # 2. Flask REST API
        resp = client.post("/predict", json=customer)
        assert resp.status_code == 200
        api_data = resp.get_json()

        # Probabilities match (allowing float rounding to 1 decimal for API percent)
        assert round(direct_churn_p * 100, 1) == round(api_data["churn_probability"], 1)
        assert direct_label == api_data["prediction"]
        assert direct_risk == api_data["risk_level"]
        assert round(float(api_data["threshold_applied"]), 4) == round(float(threshold), 4)

    # 3. Batch Processor parity
    batch_df = pd.DataFrame(test_customers)
    scored_df, summary = process_batch_csv(batch_df, model)

    for idx, customer in enumerate(test_customers):
        df_encoded = prepare_input_features(customer)
        _, direct_churn_p, _, direct_risk, _ = predict_customer_churn(model, df_encoded)

        assert scored_df.iloc[idx]["Churn_Probability_%"] == round(direct_churn_p * 100, 2)
        assert scored_df.iloc[idx]["Risk_Level"] == direct_risk


def test_model_metrics_json_consistency():
    """Verifies that model_metrics.json aligns with active model and artifact configuration."""
    with open("Models/model_metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)

    assert "best_model" in metrics
    best_model_name = metrics["best_model"]
    assert best_model_name in metrics["metrics"]

    model_stats = metrics["metrics"][best_model_name]
    assert "Optimal Threshold" in model_stats
    assert 0.15 <= model_stats["Optimal Threshold"] <= 0.85
    assert model_stats["Accuracy"] > 0.70
    assert model_stats["ROC-AUC"] > 0.80


def test_explicit_model_selection_override():
    """Verifies that explicit model selection (e.g. Logistic Regression) loads cleanly."""
    model_lr = load_churn_model("Models/churn_models.joblib", model_name="Logistic Regression")
    assert "LogisticRegression" in type(model_lr.named_steps["classifier"]).__name__
    assert hasattr(model_lr, "threshold_")
    assert model_lr.threshold_ == 0.3081

    model_xgb = load_churn_model("Models/churn_models.joblib", model_name="XGBoost")
    assert "XGBClassifier" in type(model_xgb.named_steps["classifier"]).__name__
    assert model_xgb.threshold_ == 0.3236
