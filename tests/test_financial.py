"""
test_financial.py
-----------------
Dedicated unit tests for financial calculations:
Customer Lifetime Value (CLV), Revenue at Risk, Recommended Retention Budget,
and What-If Scenario Simulations.
"""

import pytest
from src.predictor import calculate_financial_impact, simulate_scenario_impact
from src.config import FINANCIAL_CONFIG


def test_financial_formula_reconciliation():
    """Confirms CLV, revenue at risk, and budget strictly follow documented formulas."""
    tenure = 12.0
    monthly = 70.0
    churn_p = 0.50

    # Horizon: max(12.0, 36.0 - min(12.0, 24.0)) = max(12.0, 24.0) = 24.0 months
    expected_horizon = 24
    expected_clv = 70.0 * 24.0  # 1680.0
    expected_at_risk = 1680.0 * 0.50  # 840.0
    expected_budget = round(840.0 * 0.15, 2)  # 126.0

    impact = calculate_financial_impact({"tenure": tenure, "monthly_charges": monthly}, churn_proba=churn_p)

    assert impact["horizon_months"] == expected_horizon
    assert impact["clv"] == expected_clv
    assert impact["revenue_at_risk"] == expected_at_risk
    assert impact["recommended_retention_budget"] == expected_budget
    assert "disclaimer" in impact


def test_financial_tenure_horizon_boundaries():
    """Verifies horizon calculation across the full tenure spectrum."""
    # Tenure 0 months -> Max horizon 36 months
    imp_0 = calculate_financial_impact({"tenure": 0, "monthly_charges": 50.0}, churn_proba=0.5)
    assert imp_0["horizon_months"] == 36
    assert imp_0["clv"] == 1800.0

    # Tenure 24 months -> Floor horizon 12 months
    imp_24 = calculate_financial_impact({"tenure": 24, "monthly_charges": 50.0}, churn_proba=0.5)
    assert imp_24["horizon_months"] == 12
    assert imp_24["clv"] == 600.0

    # Tenure 72 months -> Floor horizon 12 months
    imp_72 = calculate_financial_impact({"tenure": 72, "monthly_charges": 50.0}, churn_proba=0.5)
    assert imp_72["horizon_months"] == 12
    assert imp_72["clv"] == 600.0

    # Negative tenure clamped to 0 -> 36 months
    imp_neg = calculate_financial_impact({"tenure": -10, "monthly_charges": 50.0}, churn_proba=0.5)
    assert imp_neg["horizon_months"] == 36


def test_financial_monthly_charges_boundaries():
    """Verifies zero, extreme, and negative monthly charges."""
    # Zero monthly charges
    imp_zero = calculate_financial_impact({"tenure": 10, "monthly_charges": 0.0}, churn_proba=0.8)
    assert imp_zero["clv"] == 0.0
    assert imp_zero["revenue_at_risk"] == 0.0
    assert imp_zero["recommended_retention_budget"] == 0.0

    # Negative monthly charges clamped to 0
    imp_neg = calculate_financial_impact({"tenure": 10, "monthly_charges": -95.0}, churn_proba=0.8)
    assert imp_neg["clv"] == 0.0
    assert imp_neg["revenue_at_risk"] == 0.0

    # Large enterprise charges
    imp_large = calculate_financial_impact({"tenure": 12, "monthly_charges": 5000.0}, churn_proba=0.25)
    assert imp_large["clv"] == 5000.0 * 24.0  # 120,000.0
    assert imp_large["revenue_at_risk"] == 30000.0
    assert imp_large["recommended_retention_budget"] == 4500.0


def test_financial_churn_probability_boundaries():
    """Verifies probability bounds [0.0, 1.0]."""
    # 0% churn probability -> zero revenue at risk
    imp_p0 = calculate_financial_impact({"tenure": 12, "monthly_charges": 100.0}, churn_proba=0.0)
    assert imp_p0["revenue_at_risk"] == 0.0
    assert imp_p0["recommended_retention_budget"] == 0.0

    # 100% churn probability -> revenue at risk equals CLV
    imp_p1 = calculate_financial_impact({"tenure": 12, "monthly_charges": 100.0}, churn_proba=1.0)
    assert imp_p1["revenue_at_risk"] == imp_p1["clv"]
    assert imp_p1["recommended_retention_budget"] == round(imp_p1["clv"] * 0.15, 2)

    # Negative probability clamped to 0
    imp_neg_p = calculate_financial_impact({"tenure": 12, "monthly_charges": 100.0}, churn_proba=-0.5)
    assert imp_neg_p["revenue_at_risk"] == 0.0

    # Probability > 1 clamped to 1
    imp_high_p = calculate_financial_impact({"tenure": 12, "monthly_charges": 100.0}, churn_proba=2.5)
    assert imp_high_p["revenue_at_risk"] == imp_high_p["clv"]


def test_scenario_impact_exposure_labeling(model, sample_customer_high_risk):
    """Verifies that scenario simulation does not claim guaranteed retention savings."""
    sim = simulate_scenario_impact(model, sample_customer_high_risk, {"contract": "Two year"})
    impact = sim["impact"]

    assert "estimated_exposure_reduction_$" in impact
    assert "disclaimer" in impact
    assert "guarantee" in impact["disclaimer"].lower() or "intervention" in impact["disclaimer"].lower()
