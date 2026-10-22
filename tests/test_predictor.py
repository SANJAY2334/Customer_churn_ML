"""
test_predictor.py
------------------
Comprehensive unit tests for model loading, inference, threshold application,
feature contributions, scenario simulation, and financial impact estimation.
"""

import pytest
import numpy as np
import pandas as pd
from src.preprocessing import prepare_input_features, FEATURE_ORDER
from src.predictor import (
    load_churn_model,
    predict_customer_churn,
    analyze_feature_contributions,
    generate_business_recommendations,
    calculate_financial_impact,
    simulate_scenario_impact,
)


def test_prediction_output_structure(model, sample_customer_high_risk):
    df_encoded = prepare_input_features(sample_customer_high_risk)
    pred_label, churn_proba, retain_proba, risk_level, risk_color = predict_customer_churn(model, df_encoded)

    assert pred_label in ["Likely to Churn", "Likely to Stay", "Churn (Likely to leave)", "Retain (Likely to stay)"]
    assert 0.0 <= churn_proba <= 1.0
    assert 0.0 <= retain_proba <= 1.0
    assert round(churn_proba + retain_proba, 4) == 1.0
    assert risk_level in ["Low Risk", "Medium Risk", "High Risk"]
    assert risk_color.startswith("#")


def test_relative_risk_classification(model, sample_customer_high_risk, sample_customer_low_risk):
    df_high = prepare_input_features(sample_customer_high_risk)
    _, p_high, _, risk_high, _ = predict_customer_churn(model, df_high)

    df_low = prepare_input_features(sample_customer_low_risk)
    _, p_low, _, risk_low, _ = predict_customer_churn(model, df_low)

    assert p_high > p_low
    assert risk_high in ["Medium Risk", "High Risk"]
    assert risk_low == "Low Risk"


def test_threshold_application(model, sample_customer_high_risk):
    df_encoded = prepare_input_features(sample_customer_high_risk)
    _, churn_proba, _, _, _ = predict_customer_churn(model, df_encoded)

    # Force threshold higher than churn probability -> should predict Retain
    label_high_thresh, _, _, _, _ = predict_customer_churn(model, df_encoded, threshold=churn_proba + 0.05)
    assert "Retain" in label_high_thresh

    # Force threshold lower than churn probability -> should predict Churn
    label_low_thresh, _, _, _, _ = predict_customer_churn(model, df_encoded, threshold=max(0.01, churn_proba - 0.05))
    assert "Churn" in label_low_thresh


def test_missing_or_invalid_artifact_path():
    with pytest.raises(FileNotFoundError):
        load_churn_model("non_existent_model_file.pkl")


def test_feature_size_mismatch_rejection(model):
    df_invalid = pd.DataFrame({"Tenure Months": [12], "Monthly Charges": [50.0]})
    with pytest.raises(ValueError, match="Feature size mismatch"):
        predict_customer_churn(model, df_invalid)


def test_deterministic_repeated_predictions(model, sample_customer_high_risk):
    df_encoded = prepare_input_features(sample_customer_high_risk)
    res1 = predict_customer_churn(model, df_encoded)
    res2 = predict_customer_churn(model, df_encoded)
    assert res1 == res2


def test_analyze_feature_contributions(model, sample_customer_high_risk):
    df_encoded = prepare_input_features(sample_customer_high_risk)
    drivers = analyze_feature_contributions(model, df_encoded, top_n=5)

    assert isinstance(drivers, pd.DataFrame)
    assert len(drivers) <= 5
    assert "Feature" in drivers.columns
    assert "Contribution" in drivers.columns


def test_generate_business_recommendations(sample_customer_high_risk):
    recs = generate_business_recommendations(sample_customer_high_risk, churn_proba=0.75, risk_level="High Risk")
    assert isinstance(recs, list)
    assert len(recs) >= 1
    combined_text = " ".join(recs).lower()
    assert any(term in combined_text for term in ["contract", "discount", "support", "offer", "check"])


def test_calculate_financial_impact_normal(sample_customer_high_risk):
    impact = calculate_financial_impact(sample_customer_high_risk, churn_proba=0.8)
    assert isinstance(impact, dict)
    assert "clv" in impact
    assert "revenue_at_risk" in impact
    assert "recommended_retention_budget" in impact
    assert impact["clv"] > 0
    assert impact["revenue_at_risk"] > 0
    assert impact["recommended_retention_budget"] == round(impact["revenue_at_risk"] * 0.15, 2)


def test_calculate_financial_impact_boundaries():
    # Boundary: Zero charges and zero tenure
    impact_zero = calculate_financial_impact({"tenure": 0, "monthly_charges": 0.0}, churn_proba=0.5)
    assert impact_zero["clv"] == 0.0
    assert impact_zero["revenue_at_risk"] == 0.0
    assert impact_zero["recommended_retention_budget"] == 0.0

    # Boundary: Negative tenure or charges are defensively clamped to 0
    impact_neg = calculate_financial_impact({"tenure": -5, "monthly_charges": -50.0}, churn_proba=-0.2)
    assert impact_neg["clv"] >= 0.0
    assert impact_neg["revenue_at_risk"] >= 0.0

    # Boundary: Churn proba > 1 is bounded
    impact_high_p = calculate_financial_impact({"tenure": 10, "monthly_charges": 100.0}, churn_proba=1.5)
    assert impact_high_p["revenue_at_risk"] <= impact_high_p["clv"]


def test_simulate_scenario_impact(model, sample_customer_high_risk):
    scenario = {"contract": "Two year", "monthly_charges": 80.0}
    sim = simulate_scenario_impact(model, sample_customer_high_risk, scenario)

    assert "baseline" in sim
    assert "simulated" in sim
    assert "impact" in sim
    assert "disclaimer" in sim["impact"]
    assert "revenue_saved_$" in sim["impact"]
