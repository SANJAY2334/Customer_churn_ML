"""
test_prioritization.py
----------------------
Unit and integration tests for customer retention prioritization,
composite multi-criteria scoring, tier assignment, and cohort filtering.
"""
import pytest
import numpy as np
import pandas as pd

from src.prioritization import (
    calculate_priority_score,
    assign_priority_tier,
    rank_customers,
    filter_customer_cohort
)


def test_priority_score_normal_values():
    # P(Churn)=0.80, CLV=$1500, max_clv=$3000
    # Expected: 100 * (0.60 * 0.80 + 0.40 * 0.50) = 100 * (0.48 + 0.20) = 68.0
    score = calculate_priority_score(churn_proba=0.80, clv=1500.0, max_clv=3000.0, weight_churn=0.60, weight_clv=0.40)
    assert score == 68.0


def test_priority_score_custom_weights():
    # 80% weight on churn risk, 20% on CLV
    # 100 * (0.80 * 0.50 + 0.20 * 1.0) = 100 * (0.40 + 0.20) = 60.0
    score = calculate_priority_score(churn_proba=0.50, clv=3000.0, max_clv=3000.0, weight_churn=0.80, weight_clv=0.20)
    assert score == 60.0


def test_priority_score_boundaries_and_extremes():
    # Probability clamped to [0, 1]
    assert calculate_priority_score(churn_proba=1.5, clv=1000.0) == calculate_priority_score(churn_proba=1.0, clv=1000.0)
    assert calculate_priority_score(churn_proba=-0.5, clv=1000.0) == calculate_priority_score(churn_proba=0.0, clv=1000.0)

    # Negative and NaN CLV safely clamped
    assert calculate_priority_score(churn_proba=0.5, clv=-500.0) == calculate_priority_score(churn_proba=0.5, clv=0.0)
    assert calculate_priority_score(churn_proba=0.5, clv=np.nan) == calculate_priority_score(churn_proba=0.5, clv=0.0)

    # Infinite CLV does not crash and gets bounded
    score_inf = calculate_priority_score(churn_proba=0.5, clv=np.inf)
    assert 0.0 <= score_inf <= 100.0

    # Weights summing to zero fallback to defaults
    score_zero_w = calculate_priority_score(churn_proba=0.5, clv=1500.0, weight_churn=0.0, weight_clv=0.0)
    assert 0.0 <= score_zero_w <= 100.0


def test_priority_tier_assignment():
    # High risk (P >= 0.60) AND High Value => Urgent
    assert assign_priority_tier(priority_score=65.0, churn_proba=0.75, is_high_value=True) == "Urgent"

    # Score >= 75 => Urgent
    assert assign_priority_tier(priority_score=78.0, churn_proba=0.55, is_high_value=False) == "Urgent"

    # Score 50 to 74 => High
    assert assign_priority_tier(priority_score=55.0, churn_proba=0.45, is_high_value=False) == "High"

    # Score 30 to 49 => Medium
    assert assign_priority_tier(priority_score=35.0, churn_proba=0.25, is_high_value=False) == "Medium"

    # Score < 30 => Low
    assert assign_priority_tier(priority_score=20.0, churn_proba=0.10, is_high_value=False) == "Low"


@pytest.fixture
def sample_cohort():
    return pd.DataFrame({
        "customerID": ["CUST-A", "CUST-B", "CUST-C", "CUST-D"],
        "Contract": ["Month-to-month", "One year", "Two year", "Month-to-month"],
        "tenure": [2, 24, 48, 6],
        "monthly_charges": [90.0, 60.0, 40.0, 100.0],
        "Estimated_CLV_$": [2880.0, 1440.0, 960.0, 3000.0],
        "Churn_Probability_%": [85.0, 45.0, 10.0, 90.0],
        "Risk_Level": ["High Risk", "Medium Risk", "Low Risk", "High Risk"],
        "Revenue_At_Risk_$": [2448.0, 648.0, 96.0, 2700.0]
    })


def test_rank_customers_sorting_and_tiers(sample_cohort):
    ranked = rank_customers(sample_cohort, sort_by="Priority_Score", ascending=False, preserve_order=False)

    assert len(ranked) == 4
    assert "Priority_Score" in ranked.columns
    assert "Priority_Tier" in ranked.columns
    assert "Priority_Rank" in ranked.columns

    # Highest priority customer must be rank 1
    assert ranked.iloc[0]["Priority_Rank"] == 1
    # Scores must be sorted non-increasingly
    assert ranked["Priority_Score"].is_monotonic_decreasing

    # Identifiers must be preserved
    assert set(ranked["customerID"]) == {"CUST-A", "CUST-B", "CUST-C", "CUST-D"}


def test_rank_customers_preserve_order(sample_cohort):
    ranked = rank_customers(sample_cohort, preserve_order=True)

    # Row order must match original sample_cohort
    assert list(ranked["customerID"]) == ["CUST-A", "CUST-B", "CUST-C", "CUST-D"]
    assert "Priority_Rank" in ranked.columns
    assert "Priority_Score" in ranked.columns


def test_filter_customer_cohort(sample_cohort):
    # Filter by Risk Level
    high_risk_only = filter_customer_cohort(sample_cohort, risk_levels=["High Risk"])
    assert len(high_risk_only) == 2
    assert set(high_risk_only["customerID"]) == {"CUST-A", "CUST-D"}

    # Filter by Contract Type
    month_to_month = filter_customer_cohort(sample_cohort, contract_types=["Month-to-month"])
    assert len(month_to_month) == 2

    # Filter by Tenure bounds (e.g. 5 to 30 months)
    tenure_filtered = filter_customer_cohort(sample_cohort, min_tenure=5, max_tenure=30)
    assert len(tenure_filtered) == 2
    assert set(tenure_filtered["customerID"]) == {"CUST-B", "CUST-D"}

    # Filter by Monthly Charges bounds
    charges_filtered = filter_customer_cohort(sample_cohort, min_monthly_charges=80.0)
    assert len(charges_filtered) == 2
    assert set(charges_filtered["customerID"]) == {"CUST-A", "CUST-D"}


def test_empty_dataframe_prioritization():
    empty_df = pd.DataFrame()
    ranked = rank_customers(empty_df)
    assert ranked.empty

    filtered = filter_customer_cohort(empty_df)
    assert filtered.empty


def test_rank_customers_deterministic_tie_breaking():
    # Two customers with identical probability and CLV (tied priority score)
    # but different revenue at risk
    df_tied = pd.DataFrame({
        "customerID": ["TIED-LOW-REV", "TIED-HIGH-REV"],
        "Churn_Probability_%": [50.0, 50.0],
        "Estimated_CLV_$": [1000.0, 1000.0],
        "Revenue_At_Risk_$": [500.0, 800.0]
    })
    ranked = rank_customers(df_tied, preserve_order=False)
    # Higher revenue at risk must break tie and rank first
    assert ranked.iloc[0]["customerID"] == "TIED-HIGH-REV"
    assert ranked.iloc[0]["Priority_Rank"] == 1
    assert ranked.iloc[1]["customerID"] == "TIED-LOW-REV"
    assert ranked.iloc[1]["Priority_Rank"] == 2
