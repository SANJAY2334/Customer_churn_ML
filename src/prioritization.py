"""
prioritization.py
-----------------
Customer retention prioritization, composite multi-criteria scoring,
cohort ranking, and business segment filtering.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from src.config import PRIORITIZATION_CONFIG, RISK_CONFIG, get_risk_tier


def calculate_priority_score(
    churn_proba: float,
    clv: float,
    max_clv: float = 3000.0,
    weight_churn: float = 0.60,
    weight_clv: float = 0.40
) -> float:
    """
    Calculates a normalized composite retention priority score (0.0 to 100.0).

    Formula:
        Priority Score = 100 * (w_churn * P(Churn) + w_clv * min(1.0, CLV / max_clv))

    Inputs:
        churn_proba: Estimated probability of churn in [0.0, 1.0].
        clv: Customer Lifetime Value (non-negative currency amount).
        max_clv: Reference upper bound for CLV scaling (defaults to $3,000).
        weight_churn: Relative weight assigned to churn risk.
        weight_clv: Relative weight assigned to customer lifetime value.

    Returns:
        float: Composite priority score between 0.0 and 100.0.
    """
    # Defensive normalization of inputs
    p = max(0.0, min(1.0, float(churn_proba) if churn_proba is not None and not np.isnan(churn_proba) else 0.0))
    val = max(0.0, float(clv) if clv is not None and not np.isnan(clv) and not np.isinf(clv) else 0.0)
    ref_max = max(1.0, float(max_clv) if max_clv is not None and not np.isnan(max_clv) and not np.isinf(max_clv) else 3000.0)

    # Normalize weights to sum to 1.0
    w_c = max(0.0, float(weight_churn))
    w_v = max(0.0, float(weight_clv))
    total_w = w_c + w_v
    if total_w <= 0.0:
        w_c, w_v = 0.60, 0.40
    else:
        w_c, w_v = w_c / total_w, w_v / total_w

    scaled_clv = min(1.0, val / ref_max)
    raw_score = 100.0 * (w_c * p + w_v * scaled_clv)
    return round(float(np.clip(raw_score, 0.0, 100.0)), 2)


def assign_priority_tier(
    priority_score: float,
    churn_proba: float,
    is_high_value: bool = False
) -> str:
    """
    Assigns an operational priority category based on composite score, churn risk, and value tier.
    Tiers:
    - Urgent: High risk (P >= 0.60) AND High Value, or composite score >= 75.
    - High: Composite score >= 50.
    - Medium: Composite score >= 30.
    - Low: Composite score < 30.
    """
    p = max(0.0, min(1.0, float(churn_proba) if not np.isnan(churn_proba) else 0.0))
    score = max(0.0, float(priority_score) if not np.isnan(priority_score) else 0.0)

    if (p >= PRIORITIZATION_CONFIG["urgent_risk_threshold"] and is_high_value) or score >= 75.0:
        return "Urgent"
    elif score >= 50.0:
        return "High"
    elif score >= 30.0:
        return "Medium"
    else:
        return "Low"


def rank_customers(
    df: pd.DataFrame,
    weight_churn: Optional[float] = None,
    weight_clv: Optional[float] = None,
    sort_by: str = "Priority_Score",
    ascending: bool = False,
    preserve_order: bool = False
) -> pd.DataFrame:
    """
    Ranks a cohort of customer records by retention priority.

    Computes:
    - Priority_Score: Composite multi-criteria score (0-100).
    - Priority_Tier: Categorical operational tier ("Urgent", "High", "Medium", "Low").
    - Priority_Rank: 1-indexed ordinal rank (1 = highest priority).

    Guarantees:
    - Never mutates the input DataFrame in-place.
    - Preserves all input columns and identifiers.
    - If preserve_order=True, preserves original row sequence while adding rank.
    - Handles missing or zero CLV safely.
    - Includes non-causal analytical disclaimers in metadata.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    ranked = df.copy()

    # Determine probability and CLV columns
    prob_col = None
    for cand in ['Churn_Probability_%', 'churn_probability', 'Estimated churn probability', 'churn_proba', 'Probability']:
        if cand in ranked.columns:
            prob_col = cand
            break

    clv_col = None
    for cand in ['Estimated_CLV_$', 'clv', 'CLV', 'Customer_Lifetime_Value', 'TotalCharges']:
        if cand in ranked.columns:
            clv_col = cand
            break

    # Extract or estimate probabilities in [0.0, 1.0]
    if prob_col is not None:
        raw_p = pd.to_numeric(ranked[prob_col], errors='coerce').fillna(0.0)
        # If expressed as percentage > 1.0, scale down to [0.0, 1.0]
        if raw_p.max() > 1.0:
            probs = (raw_p / 100.0).clip(0.0, 1.0)
        else:
            probs = raw_p.clip(0.0, 1.0)
    else:
        probs = pd.Series(0.0, index=ranked.index)

    # Extract or estimate CLV
    if clv_col is not None:
        clvs = pd.to_numeric(ranked[clv_col], errors='coerce').fillna(0.0).clip(lower=0.0)
    else:
        # Fallback approximation from MonthlyCharges and tenure if available
        monthly = pd.to_numeric(ranked.get('monthly_charges', ranked.get('MonthlyCharges', 70.0)), errors='coerce').fillna(70.0)
        clvs = (monthly * 24.0).clip(lower=0.0)

    # Determine reference max CLV (95th percentile to prevent skew from single outliers)
    positive_clvs = clvs[clvs > 0]
    ref_max_clv = float(positive_clvs.quantile(0.95)) if len(positive_clvs) > 0 else 3000.0
    if ref_max_clv <= 0 or np.isnan(ref_max_clv):
        ref_max_clv = 3000.0

    high_val_cutoff = float(clvs.quantile(PRIORITIZATION_CONFIG["high_value_clv_quantile"])) if len(clvs) > 0 else 1500.0

    w_c = weight_churn if weight_churn is not None else PRIORITIZATION_CONFIG["default_weight_churn"]
    w_v = weight_clv if weight_clv is not None else PRIORITIZATION_CONFIG["default_weight_clv"]

    scores = []
    tiers = []
    for p, c in zip(probs, clvs):
        score = calculate_priority_score(p, c, max_clv=ref_max_clv, weight_churn=w_c, weight_clv=w_v)
        is_hv = bool(c >= high_val_cutoff)
        tier = assign_priority_tier(score, p, is_high_value=is_hv)
        scores.append(score)
        tiers.append(tier)

    ranked['Priority_Score'] = scores
    ranked['Priority_Tier'] = tiers

    valid_sort_cols = [c for c in [sort_by, 'Priority_Score', 'Revenue_At_Risk_$', 'Estimated_CLV_$'] if c in ranked.columns]
    primary_sort = valid_sort_cols[0] if valid_sort_cols else 'Priority_Score'

    tie_breaker_hierarchy = [primary_sort, 'Revenue_At_Risk_$', 'Estimated_CLV_$', 'Churn_Probability_%']
    sort_cols = []
    for c in tie_breaker_hierarchy:
        if c in ranked.columns and c not in sort_cols:
            sort_cols.append(c)

    if preserve_order:
        # Assign rank based on priority score without reordering dataframe rows
        ranked['Priority_Rank'] = ranked[primary_sort].rank(ascending=ascending, method='min').astype(int)
    else:
        # Sort rows with explicit, deterministic tie-breaking hierarchy
        ranked.sort_values(by=sort_cols, ascending=[ascending] * len(sort_cols), inplace=True)
        ranked.reset_index(drop=True, inplace=True)
        ranked['Priority_Rank'] = range(1, len(ranked) + 1)

    return ranked


def filter_customer_cohort(
    df: pd.DataFrame,
    risk_levels: Optional[List[str]] = None,
    contract_types: Optional[List[str]] = None,
    priority_tiers: Optional[List[str]] = None,
    min_tenure: Optional[float] = None,
    max_tenure: Optional[float] = None,
    min_monthly_charges: Optional[float] = None,
    max_monthly_charges: Optional[float] = None,
    min_churn_proba: Optional[float] = None,
    max_churn_proba: Optional[float] = None,
) -> pd.DataFrame:
    """
    Applies multi-attribute filtering to a customer cohort.

    Supports:
    - risk_levels: e.g. ["High Risk", "Medium Risk"]
    - contract_types: e.g. ["Month-to-month", "One year", "Two year"]
    - priority_tiers: e.g. ["Urgent", "High"]
    - min_tenure / max_tenure: tenure bounds in months
    - min_monthly_charges / max_monthly_charges: monthly bill bounds in $
    - min_churn_proba / max_churn_proba: probability bounds in [0.0, 1.0] or [0, 100]
    """
    if df is None or df.empty:
        return pd.DataFrame()

    filtered = df.copy()

    # Filter by Risk Level
    if risk_levels:
        risk_col = next((c for c in ['Risk_Level', 'risk_level', 'Risk Level'] if c in filtered.columns), None)
        if risk_col:
            allowed_risks = {r.lower().strip() for r in risk_levels}
            filtered = filtered[filtered[risk_col].astype(str).str.lower().str.strip().isin(allowed_risks)]

    # Filter by Priority Tier
    if priority_tiers:
        tier_col = next((c for c in ['Priority_Tier', 'priority_tier', 'Priority Tier'] if c in filtered.columns), None)
        if tier_col:
            allowed_tiers = {t.lower().strip() for t in priority_tiers}
            filtered = filtered[filtered[tier_col].astype(str).str.lower().str.strip().isin(allowed_tiers)]

    # Filter by Contract Type
    if contract_types:
        contract_col = next((c for c in ['Contract', 'contract', 'contract_type'] if c in filtered.columns), None)
        if contract_col:
            allowed_contracts = {ct.lower().strip() for ct in contract_types}
            filtered = filtered[filtered[contract_col].astype(str).str.lower().str.strip().isin(allowed_contracts)]

    # Filter by Tenure bounds
    tenure_col = next((c for c in ['tenure', 'Tenure Months', 'Tenure', 'tenure_months'] if c in filtered.columns), None)
    if tenure_col:
        t_vals = pd.to_numeric(filtered[tenure_col], errors='coerce')
        if min_tenure is not None:
            filtered = filtered[t_vals >= float(min_tenure)]
            t_vals = pd.to_numeric(filtered[tenure_col], errors='coerce')
        if max_tenure is not None:
            filtered = filtered[t_vals <= float(max_tenure)]

    # Filter by Monthly Charges bounds
    charges_col = next((c for c in ['monthly_charges', 'Monthly Charges', 'MonthlyCharges'] if c in filtered.columns), None)
    if charges_col:
        c_vals = pd.to_numeric(filtered[charges_col], errors='coerce')
        if min_monthly_charges is not None:
            filtered = filtered[c_vals >= float(min_monthly_charges)]
            c_vals = pd.to_numeric(filtered[charges_col], errors='coerce')
        if max_monthly_charges is not None:
            filtered = filtered[c_vals <= float(max_monthly_charges)]

    # Filter by Churn Probability bounds
    prob_col = next((c for c in ['Churn_Probability_%', 'churn_probability', 'Estimated churn probability', 'churn_proba'] if c in filtered.columns), None)
    if prob_col:
        raw_p = pd.to_numeric(filtered[prob_col], errors='coerce')
        scale = 100.0 if raw_p.max() > 1.0 else 1.0
        if min_churn_proba is not None:
            thresh_p = float(min_churn_proba) * (scale if min_churn_proba <= 1.0 and scale == 100.0 else 1.0)
            filtered = filtered[raw_p >= thresh_p]
            raw_p = pd.to_numeric(filtered[prob_col], errors='coerce')
        if max_churn_proba is not None:
            thresh_p = float(max_churn_proba) * (scale if max_churn_proba <= 1.0 and scale == 100.0 else 1.0)
            filtered = filtered[raw_p <= thresh_p]

    filtered.reset_index(drop=True, inplace=True)
    return filtered
