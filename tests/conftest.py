"""
conftest.py
-----------
Pytest fixtures for unit and integration testing of the Telecom Churn Prediction API.
"""

import os
import pytest
import pandas as pd
from flask_app import app as flask_app_instance
from src.predictor import load_churn_model

@pytest.fixture(scope="session")
def model():
    """Provides the trained model instance, training if necessary."""
    model_path = os.path.join("Models", "churn_model.pkl")
    if not os.path.exists(model_path):
        import subprocess
        import sys
        subprocess.run([sys.executable, "train_model.py"], check=True)
    return load_churn_model(model_path)

@pytest.fixture
def client():
    """Provides a Flask test client with test configuration."""
    flask_app_instance.config["TESTING"] = True
    with flask_app_instance.test_client() as client:
        yield client

@pytest.fixture
def sample_customer_high_risk():
    """Provides customer attributes typically correlating with high churn risk."""
    return {
        "tenure": 2,
        "monthly_charges": 95.5,
        "total_charges": 191.0,
        "gender": "Female",
        "senior_citizen": "Yes",
        "partner": "No",
        "dependents": "No",
        "phone_service": "Yes",
        "multiple_lines": "Yes",
        "internet_service": "Fiber optic",
        "online_security": "No",
        "online_backup": "No",
        "device_protection": "No",
        "tech_support": "No",
        "streaming_tv": "Yes",
        "streaming_movies": "Yes",
        "contract": "Month-to-month",
        "paperless_billing": "Yes",
        "payment_method": "Electronic check"
    }

@pytest.fixture
def sample_customer_low_risk():
    """Provides customer attributes typically correlating with low churn risk."""
    return {
        "tenure": 60,
        "monthly_charges": 24.5,
        "total_charges": 1470.0,
        "gender": "Male",
        "senior_citizen": "No",
        "partner": "Yes",
        "dependents": "Yes",
        "phone_service": "Yes",
        "multiple_lines": "No",
        "internet_service": "No",
        "online_security": "No internet service",
        "online_backup": "No internet service",
        "device_protection": "No internet service",
        "tech_support": "No internet service",
        "streaming_tv": "No internet service",
        "streaming_movies": "No internet service",
        "contract": "Two year",
        "paperless_billing": "No",
        "payment_method": "Credit card (automatic)"
    }
