"""
simulator.py
------------
Hypothetical retention campaign simulator, cost-benefit scenario modeler,
and portfolio-level sensitivity analysis with non-causal analytical disclaimers.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


def simulate_retention_campaign(
    df_scored: pd.DataFrame,
    assumed_reduction_rate: float = 0.20,
    cost_per_intervention: float = 25.0,
    budget_cap: Optional[float] = None,
    target_cohort_column: Optional[str] = "Priority_Tier",
    target_cohort_values: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Simulates portfolio-level retention scenarios under user-defined budget and effectiveness parameters.

    Important Analytical Disclaimer:
    This simulator models hypothetical scenarios based on user-supplied assumptions.
    Observed model predictions describe statistical correlation, not proven causal outcomes.
    Intervention effectiveness (reduction rate) must be empirically verified via randomized controlled trials (A/B testing).

    Parameters:
        df_scored: DataFrame containing scored customers (with CLV, Probability, Revenue at Risk, Priority Tier).
        assumed_reduction_rate: Hypothetical relative reduction in churn probability (0.0 to 1.0).
        cost_per_intervention: Non-negative cost in currency ($) per customer targeted.
        budget_cap: Optional maximum budget allocation limit.
        target_cohort_column: Column name to segment the target population.
        target_cohort_values: List of cohort values to include (defaults to ['Urgent', 'High'] if available).

    Returns:
        dict: Summary of scenario inputs, operational metrics, financial exposure, net return, and analytical disclaimers.
    """
    # Defensive input validations
    try:
        eff_rate = max(0.0, min(1.0, float(assumed_reduction_rate)))
    except (ValueError, TypeError):
        eff_rate = 0.20

    try:
        unit_cost = max(0.0, float(cost_per_intervention))
    except (ValueError, TypeError):
        unit_cost = 25.0

    cap = None
    if budget_cap is not None:
        try:
            cap = max(0.0, float(budget_cap))
        except (ValueError, TypeError):
            cap = None

    if df_scored is None or df_scored.empty:
        return {
            "status": "empty_input",
            "eligible_customers": 0,
            "targeted_customers": 0,
            "total_campaign_cost_$": 0.0,
            "remaining_budget_$": cap if cap is not None else 0.0,
            "baseline_revenue_at_risk_$": 0.0,
            "simulated_revenue_at_risk_$": 0.0,
            "gross_exposure_reduction_$": 0.0,
            "net_scenario_return_$": 0.0,
            "return_on_retention_spend_ratio": 0.0,
            "parameters": {
                "assumed_reduction_rate": eff_rate,
                "cost_per_intervention": unit_cost,
                "budget_cap": cap
            },
            "disclaimer": "No customer records provided for simulation."
        }

    cohort_df = df_scored.copy()

    # Apply cohort filtering if specified
    if target_cohort_column and target_cohort_column in cohort_df.columns:
        if target_cohort_values:
            allowed = {str(v).lower().strip() for v in target_cohort_values}
            cohort_df = cohort_df[cohort_df[target_cohort_column].astype(str).str.lower().str.strip().isin(allowed)]
        else:
            # Default sensible cohort: Urgent and High priority, or High Risk
            default_allowed = {"urgent", "high", "high risk"}
            cohort_df = cohort_df[cohort_df[target_cohort_column].astype(str).str.lower().str.strip().isin(default_allowed)]

    eligible_count = len(cohort_df)

    # Determine how many customers can be targeted within budget cap
    if cap is not None:
        if unit_cost > 0:
            max_affordable = int(cap // unit_cost)
            targeted_count = min(eligible_count, max_affordable)
        else:
            targeted_count = eligible_count
    else:
        targeted_count = eligible_count

    targeted_df = cohort_df.head(targeted_count).copy() if targeted_count > 0 else pd.DataFrame()

    total_cost = round(targeted_count * unit_cost, 2)
    remaining_budget = round(cap - total_cost, 2) if cap is not None else None

    # Calculate financial exposures
    if not targeted_df.empty:
        # Resolve revenue at risk column
        at_risk_col = next((c for c in ['Revenue_At_Risk_$', 'revenue_at_risk', 'Revenue at Risk'] if c in targeted_df.columns), None)
        clv_col = next((c for c in ['Estimated_CLV_$', 'clv', 'CLV', 'Customer_Lifetime_Value'] if c in targeted_df.columns), None)
        prob_col = next((c for c in ['Churn_Probability_%', 'churn_probability', 'Estimated churn probability', 'churn_proba'] if c in targeted_df.columns), None)

        if at_risk_col:
            baseline_risks = pd.to_numeric(targeted_df[at_risk_col], errors='coerce').fillna(0.0).clip(lower=0.0)
        elif clv_col and prob_col:
            clvs = pd.to_numeric(targeted_df[clv_col], errors='coerce').fillna(0.0).clip(lower=0.0)
            raw_p = pd.to_numeric(targeted_df[prob_col], errors='coerce').fillna(0.0)
            p = raw_p / 100.0 if raw_p.max() > 1.0 else raw_p
            baseline_risks = clvs * p.clip(0.0, 1.0)
        else:
            baseline_risks = pd.Series(0.0, index=targeted_df.index)

        baseline_exposure = round(float(baseline_risks.sum()), 2)
        # Exposure reduction under assumed effectiveness rate:
        # New Risk = Baseline Risk * (1 - eff_rate) => Saved = Baseline Risk * eff_rate
        gross_reduction = round(float((baseline_risks * eff_rate).sum()), 2)
        simulated_exposure = round(max(0.0, baseline_exposure - gross_reduction), 2)
    else:
        baseline_exposure = 0.0
        gross_reduction = 0.0
        simulated_exposure = 0.0

    net_return = round(gross_reduction - total_cost, 2)
    roi_ratio = round(gross_reduction / total_cost, 2) if total_cost > 0.0 else 0.0

    return {
        "status": "success",
        "eligible_customers": eligible_count,
        "targeted_customers": targeted_count,
        "total_campaign_cost_$": total_cost,
        "remaining_budget_$": remaining_budget,
        "baseline_revenue_at_risk_$": baseline_exposure,
        "simulated_revenue_at_risk_$": simulated_exposure,
        "gross_exposure_reduction_$": gross_reduction,
        "net_scenario_return_$": net_return,
        "return_on_retention_spend_ratio": roi_ratio,
        "parameters": {
            "assumed_reduction_rate": eff_rate,
            "cost_per_intervention": unit_cost,
            "budget_cap": cap,
            "target_cohort": target_cohort_values or ["Urgent", "High"]
        },
        "disclaimer": (
            "Hypothetical simulation based on user-defined assumptions. "
            "Model predictions describe statistical correlations and do not guarantee causal retention outcomes. "
            "Retention campaigns should be validated through randomized controlled A/B experiments."
        )
    }
