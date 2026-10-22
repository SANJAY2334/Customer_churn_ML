"""
test_preprocessing.py
---------------------
Unit tests for customer feature preprocessing, defensive validation,
categorical encoding, and edge-case handling.
"""

import pytest
import pandas as pd
import numpy as np
from src.preprocessing import prepare_input_features, FEATURE_ORDER


def test_feature_count_and_order(sample_customer_high_risk):
    df_encoded = prepare_input_features(sample_customer_high_risk)
    assert isinstance(df_encoded, pd.DataFrame)
    assert df_encoded.shape == (1, 30)
    assert list(df_encoded.columns) == FEATURE_ORDER


def test_total_charges_imputation(sample_customer_high_risk):
    payload = sample_customer_high_risk.copy()
    payload["total_charges"] = None
    payload["tenure"] = 10
    payload["monthly_charges"] = 50.0

    df_encoded = prepare_input_features(payload)
    # Total charges should be tenure * monthly_charges = 500.0
    assert df_encoded["Total Charges"].iloc[0] == 500.0


def test_contract_encoding(sample_customer_low_risk):
    df_encoded = prepare_input_features(sample_customer_low_risk)
    assert df_encoded["Contract_Two year"].iloc[0] == 1
    assert df_encoded["Contract_One year"].iloc[0] == 0


def test_internet_service_fiber_optic(sample_customer_high_risk):
    df_encoded = prepare_input_features(sample_customer_high_risk)
    assert df_encoded["Internet Service_Fiber optic"].iloc[0] == 1
    assert df_encoded["Internet Service_No"].iloc[0] == 0


def test_no_internet_service_cascading(sample_customer_low_risk):
    df_encoded = prepare_input_features(sample_customer_low_risk)
    assert df_encoded["Internet Service_No"].iloc[0] == 1
    assert df_encoded["Online Security_No internet service"].iloc[0] == 1
    assert df_encoded["Tech Support_No internet service"].iloc[0] == 1


def test_extra_columns_ignored_safely(sample_customer_high_risk):
    payload = sample_customer_high_risk.copy()
    payload["customerID"] = "7590-VHVEG"
    payload["Churn"] = "Yes"
    payload["unrelated_meta"] = "test"

    df_encoded = prepare_input_features(payload)
    assert df_encoded.shape == (1, 30)
    assert "customerID" not in df_encoded.columns
    assert "Churn" not in df_encoded.columns


def test_invalid_payload_type():
    with pytest.raises(TypeError, match="Expected input payload to be a dictionary"):
        prepare_input_features(["not", "a", "dict"])


def test_invalid_numerical_values():
    with pytest.raises(ValueError, match="Invalid tenure value"):
        prepare_input_features({"tenure": "invalid_string"})

    with pytest.raises(ValueError, match="Invalid monthly_charges value"):
        prepare_input_features({"tenure": 10, "monthly_charges": "bad_charge"})


def test_missing_optional_fields_fallback_safely():
    minimal_payload = {"tenure": 5, "monthly_charges": 30.0}
    df_encoded = prepare_input_features(minimal_payload)
    assert df_encoded.shape == (1, 30)
    assert df_encoded["Tenure Months"].iloc[0] == 5.0
    assert df_encoded["Monthly Charges"].iloc[0] == 30.0
    assert df_encoded["Total Charges"].iloc[0] == 150.0


def test_negative_numeric_inputs_clamped():
    payload = {"tenure": -5, "monthly_charges": -20.0}
    df_encoded = prepare_input_features(payload)
    assert df_encoded["Tenure Months"].iloc[0] == 0.0
    assert df_encoded["Monthly Charges"].iloc[0] == 0.0
