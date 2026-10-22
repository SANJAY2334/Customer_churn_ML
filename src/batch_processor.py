"""
batch_processor.py
------------------
CSV batch prediction, schema validation, row-count preservation,
threshold consistency, and financial aggregate reconciliation.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import numpy as np
import pandas as pd

from src.preprocessing import prepare_input_features, FEATURE_ORDER
from src.predictor import calculate_financial_impact, predict_customer_churn
from src.prioritization import rank_customers
from src.config import get_risk_tier

COLUMN_MAPPING = {
    'tenure': 'tenure', 'Tenure Months': 'tenure', 'Tenure': 'tenure', 'tenure_months': 'tenure',
    'MonthlyCharges': 'monthly_charges', 'Monthly Charges': 'monthly_charges', 'monthly_charges': 'monthly_charges',
    'TotalCharges': 'total_charges', 'Total Charges': 'total_charges', 'total_charges': 'total_charges',
    'gender': 'gender', 'Gender': 'gender',
    'SeniorCitizen': 'senior_citizen', 'Senior Citizen': 'senior_citizen', 'senior_citizen': 'senior_citizen',
    'Partner': 'partner', 'partner': 'partner',
    'Dependents': 'dependents', 'dependents': 'dependents',
    'PhoneService': 'phone_service', 'Phone Service': 'phone_service', 'phone_service': 'phone_service',
    'MultipleLines': 'multiple_lines', 'Multiple Lines': 'multiple_lines', 'multiple_lines': 'multiple_lines',
    'InternetService': 'internet_service', 'Internet Service': 'internet_service', 'internet_service': 'internet_service',
    'OnlineSecurity': 'online_security', 'Online Security': 'online_security', 'online_security': 'online_security',
    'OnlineBackup': 'online_backup', 'Online Backup': 'online_backup', 'online_backup': 'online_backup',
    'DeviceProtection': 'device_protection', 'Device Protection': 'device_protection', 'device_protection': 'device_protection',
    'TechSupport': 'tech_support', 'Tech Support': 'tech_support', 'tech_support': 'tech_support',
    'StreamingTV': 'streaming_tv', 'Streaming TV': 'streaming_tv', 'streaming_tv': 'streaming_tv',
    'StreamingMovies': 'streaming_movies', 'Streaming Movies': 'streaming_movies', 'streaming_movies': 'streaming_movies',
    'Contract': 'contract', 'contract': 'contract',
    'PaperlessBilling': 'paperless_billing', 'Paperless Billing': 'paperless_billing', 'paperless_billing': 'paperless_billing',
    'PaymentMethod': 'payment_method', 'Payment Method': 'payment_method', 'payment_method': 'payment_method'
}


def process_batch_csv(
    df_raw: pd.DataFrame,
    model: Any,
    threshold: Optional[float] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Processes a DataFrame of customer records, encodes features row-by-row,
    applies canonical ML predictions, and reconciles financial risk aggregates.

    Guarantees:
    - Never drops valid customer rows silently.
    - Preserves all original metadata and identifier columns.
    - Uses the configured model threshold consistently.
    - Reconciles aggregate metrics with row-level values.

    Returns:
        tuple: (result_df, summary_dict)
    """
    if df_raw is None or df_raw.empty:
        raise ValueError("Uploaded CSV dataset is empty or contains no records.")

    active_threshold = threshold if threshold is not None else getattr(model, "threshold_", 0.5)

    df_clean = df_raw.copy()
    renamed_cols = {col: COLUMN_MAPPING[col] for col in df_clean.columns if col in COLUMN_MAPPING}
    df_clean.rename(columns=renamed_cols, inplace=True)

    # Fast vectorized path if all 30 model features already exist in input df_raw
    if all(col in df_raw.columns for col in FEATURE_ORDER):
        try:
            X_mat = df_raw[FEATURE_ORDER].astype(float)
            if hasattr(model, "predict_proba"):
                probs = model.predict_proba(X_mat)[:, 1]
            elif hasattr(model, "decision_function"):
                dfs = model.decision_function(X_mat)
                probs = 1.0 / (1.0 + np.exp(-dfs))
            else:
                probs = model.predict(X_mat).astype(float)

            raw_tenure = pd.to_numeric(df_raw['Tenure Months'], errors='coerce').fillna(12.0).clip(lower=0.0)
            raw_monthly = pd.to_numeric(df_raw['Monthly Charges'], errors='coerce').fillna(70.0).clip(lower=0.0)
            expected_months = np.maximum(12.0, 36.0 - np.minimum(raw_tenure, 24.0))

            clvs = (raw_monthly * expected_months).round(2).tolist()
            at_risks = (pd.Series(clvs) * probs).round(2).tolist()
            recommended_budgets = (pd.Series(at_risks) * 0.15).round(2).tolist()
            probabilities = [round(float(p) * 100, 2) for p in probs]
            predictions = ["Churn" if p >= active_threshold else "Retain" for p in probs]
            risk_levels = [get_risk_tier(p)[0] for p in probs]
        except Exception:
            # Fall back to row-by-row if vectorized pipeline encountered unexpected types
            predictions, probabilities, risk_levels, clvs, at_risks, recommended_budgets = [], [], [], [], [], []
    else:
        predictions, probabilities, risk_levels, clvs, at_risks, recommended_budgets = [], [], [], [], [], []

    if not predictions:
        for idx, row in df_clean.iterrows():
            input_dict = row.to_dict()
            try:
                df_encoded = prepare_input_features(input_dict)
                _, churn_proba, _, risk_level, _ = predict_customer_churn(
                    model, df_encoded, threshold=active_threshold
                )
                fin = calculate_financial_impact(input_dict, churn_proba)

                pred_status = "Churn" if churn_proba >= active_threshold else "Retain"
                predictions.append(pred_status)
                probabilities.append(round(churn_proba * 100, 2))
                risk_levels.append(risk_level)
                clvs.append(fin['clv'])
                at_risks.append(fin['revenue_at_risk'])
                recommended_budgets.append(fin['recommended_retention_budget'])
            except Exception as e:
                # Safe row-level fallback without dropping record
                predictions.append("Unknown")
                probabilities.append(0.0)
                risk_levels.append("Error")
                clvs.append(0.0)
                at_risks.append(0.0)
                recommended_budgets.append(0.0)

    result_df = df_raw.copy()
    result_df['Predicted_Status'] = predictions
    result_df['Churn_Probability_%'] = probabilities
    result_df['Risk_Level'] = risk_levels
    result_df['Estimated_CLV_$'] = clvs
    result_df['Revenue_At_Risk_$'] = at_risks
    result_df['Recommended_Budget_$'] = recommended_budgets

    # Attach retention prioritization score, tier, and rank
    result_df = rank_customers(result_df, preserve_order=True)

    total_records = len(result_df)
    valid_records = sum(1 for p in predictions if p != "Unknown")
    high_risk_count = sum(1 for r in risk_levels if r == 'High Risk')
    urgent_count = sum(1 for t in result_df['Priority_Tier'] if t == 'Urgent')
    high_priority_count = sum(1 for t in result_df['Priority_Tier'] if t in ('Urgent', 'High'))
    churn_count = sum(1 for p in predictions if p == 'Churn')
    churn_rate = (churn_count / total_records * 100) if total_records > 0 else 0.0
    total_revenue_at_risk = round(sum(at_risks), 2)
    total_clv = round(sum(clvs), 2)

    summary = {
        'total_records': total_records,
        'valid_records': valid_records,
        'churn_count': churn_count,
        'churn_rate': round(float(churn_rate), 2),
        'high_risk_count': high_risk_count,
        'urgent_priority_count': urgent_count,
        'high_priority_count': high_priority_count,
        'total_clv_$': total_clv,
        'total_revenue_at_risk_$': total_revenue_at_risk,
        'applied_threshold': round(float(active_threshold), 4)
    }

    return result_df, summary
