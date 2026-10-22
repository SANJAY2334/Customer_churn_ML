"""
test_simulator.py
-----------------
Unit tests for the portfolio-level retention campaign simulator,
budget constraint logic, exposure accounting, and boundary conditions.
"""
import pytest
import numpy as np
import pandas as pd

from src.simulator import simulate_retention_campaign


@pytest.fixture
def scored_campaign_cohort():
    return pd.DataFrame({
        "customerID": [f"CUST-{i:03d}" for i in range(1, 11)],
        "Priority_Tier": ["Urgent", "Urgent", "High", "High", "Medium", "Medium", "Low", "Low", "Urgent", "High"],
        "Revenue_At_Risk_$": [1000.0, 800.0, 600.0, 500.0, 400.0, 300.0, 200.0, 100.0, 1200.0, 700.0],
        "Estimated_CLV_$": [2000.0, 1600.0, 1500.0, 1400.0, 1200.0, 1000.0, 800.0, 500.0, 2400.0, 1800.0],
        "Churn_Probability_%": [50.0, 50.0, 40.0, 35.7, 33.3, 30.0, 25.0, 20.0, 50.0, 38.9]
    })


def test_simulate_retention_campaign_normal(scored_campaign_cohort):
    # Target Urgent & High: 6 customers in cohort (1, 2, 3, 4, 9, 10)
    # Total revenue at risk for these 6: 1000 + 800 + 600 + 500 + 1200 + 700 = 4800.0
    # Cost per contact: $50. No budget cap.
    # Total spend: 6 * 50 = $300.
    # Assumed reduction: 25%.
    # Gross saved: 4800 * 0.25 = $1200.
    # Net return: 1200 - 300 = $900.
    # ROI: 1200 / 300 = 4.0x.
    res = simulate_retention_campaign(
        scored_campaign_cohort,
        assumed_reduction_rate=0.25,
        cost_per_intervention=50.0,
        budget_cap=None,
        target_cohort_values=["Urgent", "High"]
    )

    assert res["status"] == "success"
    assert res["eligible_customers"] == 6
    assert res["targeted_customers"] == 6
    assert res["total_campaign_cost_$"] == 300.0
    assert res["baseline_revenue_at_risk_$"] == 4800.0
    assert res["gross_exposure_reduction_$"] == 1200.0
    assert res["net_scenario_return_$"] == 900.0
    assert res["return_on_retention_spend_ratio"] == 4.0
    assert "disclaimer" in res


def test_simulate_budget_exhaustion(scored_campaign_cohort):
    # 6 eligible customers at $50/contact requires $300.
    # If budget cap is $160, only int(160 // 50) = 3 customers can be targeted.
    res = simulate_retention_campaign(
        scored_campaign_cohort,
        assumed_reduction_rate=0.20,
        cost_per_intervention=50.0,
        budget_cap=160.0,
        target_cohort_values=["Urgent", "High"]
    )

    assert res["eligible_customers"] == 6
    assert res["targeted_customers"] == 3
    assert res["total_campaign_cost_$"] == 150.0
    assert res["remaining_budget_$"] == 10.0
    assert res["gross_exposure_reduction_$"] > 0


def test_simulate_zero_budget(scored_campaign_cohort):
    res = simulate_retention_campaign(
        scored_campaign_cohort,
        assumed_reduction_rate=0.20,
        cost_per_intervention=50.0,
        budget_cap=0.0
    )

    assert res["targeted_customers"] == 0
    assert res["total_campaign_cost_$"] == 0.0
    assert res["gross_exposure_reduction_$"] == 0.0
    assert res["net_scenario_return_$"] == 0.0
    assert res["return_on_retention_spend_ratio"] == 0.0


def test_simulate_zero_unit_cost_spend_ratio_not_misrepresented(scored_campaign_cohort):
    res = simulate_retention_campaign(
        scored_campaign_cohort,
        assumed_reduction_rate=0.20,
        cost_per_intervention=0.0,
        budget_cap=None
    )
    assert res["total_campaign_cost_$"] == 0.0
    assert res["gross_exposure_reduction_$"] > 0.0
    # Ratio must not be misrepresented as positive when spend is zero
    assert res["return_on_retention_spend_ratio"] == 0.0


def test_simulate_boundary_and_invalid_rates(scored_campaign_cohort):
    # Reduction rate > 1.0 clamped to 1.0 (100% reduction)
    res_high = simulate_retention_campaign(scored_campaign_cohort, assumed_reduction_rate=1.8)
    assert res_high["parameters"]["assumed_reduction_rate"] == 1.0
    assert res_high["simulated_revenue_at_risk_$"] == 0.0

    # Negative reduction rate clamped to 0.0
    res_neg = simulate_retention_campaign(scored_campaign_cohort, assumed_reduction_rate=-0.5)
    assert res_neg["parameters"]["assumed_reduction_rate"] == 0.0
    assert res_neg["gross_exposure_reduction_$"] == 0.0

    # Negative cost clamped to 0.0
    res_neg_cost = simulate_retention_campaign(scored_campaign_cohort, cost_per_intervention=-25.0)
    assert res_neg_cost["total_campaign_cost_$"] == 0.0


def test_simulate_empty_cohort():
    empty_df = pd.DataFrame()
    res = simulate_retention_campaign(empty_df, assumed_reduction_rate=0.20)
    assert res["status"] == "empty_input"
    assert res["eligible_customers"] == 0
    assert res["targeted_customers"] == 0
    assert res["gross_exposure_reduction_$"] == 0.0


def test_simulate_analytical_disclaimer():
    df_sample = pd.DataFrame({
        "Priority_Tier": ["High"],
        "Revenue_At_Risk_$": [500.0]
    })
    res = simulate_retention_campaign(df_sample)
    assert "hypothetical" in res["disclaimer"].lower() or "randomized" in res["disclaimer"].lower()
