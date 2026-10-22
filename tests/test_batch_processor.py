"""
test_batch_processor.py
-----------------------
Unit tests for batch CSV processing, row-count preservation,
aggregate reconciliation, and error resilience.
"""

import pytest
import pandas as pd
from src.batch_processor import process_batch_csv
from src.preprocessing import prepare_input_features
from src.predictor import predict_customer_churn


@pytest.fixture
def sample_batch_df():
    data = {
        "customerID": ["CUST-001", "CUST-002", "CUST-003"],
        "Tenure Months": [1, 48, 12],
        "Monthly Charges": [95.0, 20.0, 65.0],
        "Total Charges": [95.0, 960.0, 780.0],
        "Gender": ["Female", "Male", "Female"],
        "Senior Citizen": ["Yes", "No", "No"],
        "Partner": ["No", "Yes", "No"],
        "Dependents": ["No", "Yes", "No"],
        "Phone Service": ["Yes", "Yes", "Yes"],
        "Multiple Lines": ["Yes", "No", "No"],
        "Internet Service": ["Fiber optic", "No", "DSL"],
        "Online Security": ["No", "No internet service", "Yes"],
        "Online Backup": ["No", "No internet service", "No"],
        "Device Protection": ["No", "No internet service", "No"],
        "Tech Support": ["No", "No internet service", "No"],
        "Streaming TV": ["Yes", "No internet service", "No"],
        "Streaming Movies": ["Yes", "No internet service", "No"],
        "Contract": ["Month-to-month", "Two year", "One year"],
        "Paperless Billing": ["Yes", "No", "Yes"],
        "Payment Method": ["Electronic check", "Credit card (automatic)", "Mailed check"],
        "metadata_region": ["North", "South", "East"]
    }
    return pd.DataFrame(data)


def test_batch_processing_row_preservation(model, sample_batch_df):
    result_df, summary = process_batch_csv(sample_batch_df, model)

    # All rows must be preserved exactly
    assert len(result_df) == len(sample_batch_df)
    # Extra columns must be preserved in output
    assert "customerID" in result_df.columns
    assert "metadata_region" in result_df.columns
    # Output columns added
    assert "Predicted_Status" in result_df.columns
    assert "Churn_Probability_%" in result_df.columns
    assert "Risk_Level" in result_df.columns
    assert "Estimated_CLV_$" in result_df.columns
    assert "Revenue_At_Risk_$" in result_df.columns


def test_batch_aggregate_reconciliation(model, sample_batch_df):
    result_df, summary = process_batch_csv(sample_batch_df, model)

    assert summary["total_records"] == 3
    assert summary["valid_records"] == 3
    # Check that sum of row values matches summary aggregate
    assert round(result_df["Revenue_At_Risk_$"].sum(), 2) == summary["total_revenue_at_risk_$"]
    assert round(result_df["Estimated_CLV_$"].sum(), 2) == summary["total_clv_$"]
    assert summary["applied_threshold"] > 0


def test_batch_individual_consistency(model, sample_batch_df):
    result_df, summary = process_batch_csv(sample_batch_df, model)

    # Compare row 0 against direct individual prediction
    row_0 = sample_batch_df.iloc[0].to_dict()
    df_encoded = prepare_input_features(row_0)
    pred_label, churn_proba, _, risk_level, _ = predict_customer_churn(
        model, df_encoded, threshold=summary["applied_threshold"]
    )

    expected_status = "Churn" if churn_proba >= summary["applied_threshold"] else "Retain"
    assert result_df.iloc[0]["Predicted_Status"] == expected_status
    assert result_df.iloc[0]["Risk_Level"] == risk_level
    assert result_df.iloc[0]["Churn_Probability_%"] == round(churn_proba * 100, 2)


def test_empty_batch_raises_error(model):
    empty_df = pd.DataFrame()
    with pytest.raises(ValueError, match="empty or contains no records"):
        process_batch_csv(empty_df, model)
