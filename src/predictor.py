"""
predictor.py
------------
Inference engine, model loading, threshold-aware prediction, risk categorization,
interpretable feature attribution, financial estimation, and retention recommendations.
"""
from __future__ import annotations

import json
import os
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import joblib
import numpy as np
import pandas as pd

from src.config import RISK_CONFIG, get_risk_tier
from src.preprocessing import FEATURE_ORDER, prepare_input_features

ROOT = Path(__file__).resolve().parent.parent

try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False


def resolve_model_path(model_path: Union[str, Path] = "Models/churn_model.pkl") -> Path:
    """Resolves model path predictably against project root or current working directory without silent fallbacks."""
    path_obj = Path(model_path)
    if path_obj.is_absolute():
        if path_obj.is_file():
            return path_obj
        raise FileNotFoundError(f"Model artifact not found at absolute path: '{path_obj}'")

    # Check relative to project root
    root_resolved = ROOT / path_obj
    if root_resolved.is_file():
        return root_resolved

    # Check relative to current working directory
    cwd_resolved = Path.cwd() / path_obj
    if cwd_resolved.is_file():
        return cwd_resolved

    raise FileNotFoundError(
        f"Model artifact not found at '{model_path}'. Please run 'python train_model.py' to generate artifacts."
    )


def load_churn_model(
    model_path: Union[str, Path] = "Models/churn_model.pkl",
    model_name: Optional[str] = None
) -> Any:
    """
    Loads trained machine learning pipeline from disk.
    Supports both standalone Pipeline artifacts (.pkl) and full multi-model dictionary artifacts (.joblib).
    Respects explicit model selection configuration (CHURN_ACTIVE_MODEL).
    Attaches threshold, model version, and metadata attributes to the returned pipeline.
    """
    from src.config import ACTIVE_MODEL_NAME

    target_model_name = model_name if model_name is not None else ACTIVE_MODEL_NAME
    resolved_path = resolve_model_path(model_path)
    artifact = joblib.load(resolved_path)

    # If artifact is a dictionary (canonical churn_models.joblib format)
    if isinstance(artifact, dict):
        available_models = artifact.get("models", {})
        best_name = artifact.get("best_model", "XGBoost")

        if target_model_name and target_model_name != "auto" and target_model_name in available_models:
            chosen_name = target_model_name
            pipeline = available_models[chosen_name]
        elif best_name in available_models:
            chosen_name = best_name
            pipeline = available_models[chosen_name]
        elif "pipeline" in artifact:
            pipeline = artifact["pipeline"]
            chosen_name = getattr(pipeline, "model_name_", best_name)
        elif available_models:
            chosen_name = next(iter(available_models.keys()))
            pipeline = available_models[chosen_name]
        else:
            raise ValueError(f"No valid models found in model artifact dictionary at {resolved_path}")

        # Attach metadata to pipeline instance
        thresholds_dict = artifact.get("thresholds", {})
        pipeline.threshold_ = thresholds_dict.get(chosen_name, artifact.get("threshold", 0.5))
        pipeline.model_version_ = artifact.get("model_version", "1.0.0")
        pipeline.model_name_ = chosen_name
        pipeline.best_model_name_ = best_name
        pipeline.metrics_ = artifact.get("metrics", {}).get(chosen_name, {})
        return pipeline

    # If artifact is already a scikit-learn Pipeline
    if not hasattr(artifact, "predict"):
        raise TypeError(f"Loaded object from {resolved_path} is not a valid scikit-learn estimator/pipeline.")

    # Check if threshold is already attached, otherwise load from model_metrics.json if present
    if not hasattr(artifact, "threshold_"):
        metrics_file = resolved_path.parent / "model_metrics.json"
        threshold = 0.5
        model_name_found = getattr(artifact, "model_name_", "Unknown")
        if metrics_file.is_file():
            try:
                with open(metrics_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    best_m = data.get("best_model")
                    for k in [model_name_found, best_m, "XGBoost", "Logistic Regression"]:
                        if k and k in data.get("metrics", {}):
                            threshold = data["metrics"][k].get("Optimal Threshold", threshold)
                            model_name_found = k
                            break
            except Exception:
                threshold = 0.5
        artifact.threshold_ = float(threshold)
        if not hasattr(artifact, "model_name_"):
            artifact.model_name_ = model_name_found

    return artifact


def predict_customer_churn(
    model: Any,
    df_encoded: pd.DataFrame,
    threshold: Optional[float] = None
) -> Tuple[str, float, float, str, str]:
    """
    Predicts churn class and probability scores for a given customer feature DataFrame.
    Applies the model's configured classification threshold or an optional override.

    Returns:
        tuple: (prediction_label, churn_probability, retain_probability, risk_level, risk_color)
    """
    expected_num_features = 30
    if hasattr(model, "feature_names_in_"):
        expected_num_features = len(model.feature_names_in_)
    elif hasattr(model, "named_steps") and hasattr(model.named_steps.get('classifier'), "feature_names_in_"):
        expected_num_features = len(model.named_steps['classifier'].feature_names_in_)

    if df_encoded.shape[1] != expected_num_features:
        raise ValueError(
            f"Feature size mismatch! Model expects {expected_num_features} features, "
            f"but got {df_encoded.shape[1]}."
        )

    # Obtain class probabilities
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(df_encoded)[0]
        churn_proba = float(probabilities[1])
        retain_proba = float(probabilities[0])
    elif hasattr(model, "decision_function"):
        df_score = float(model.decision_function(df_encoded)[0])
        # Logistic sigmoid approximation
        churn_proba = float(1.0 / (1.0 + np.exp(-df_score)))
        retain_proba = 1.0 - churn_proba
    else:
        pred_raw = int(model.predict(df_encoded)[0])
        churn_proba = 1.0 if pred_raw == 1 else 0.0
        retain_proba = 1.0 - churn_proba

    # Apply configured classification threshold
    active_threshold = threshold if threshold is not None else getattr(model, "threshold_", 0.5)
    prediction = 1 if churn_proba >= active_threshold else 0

    # Standardized risk tier from centralized configuration
    risk_level, risk_color = get_risk_tier(churn_proba)

    pred_label = "Churn (Likely to leave)" if prediction == 1 else "Retain (Likely to stay)"
    return pred_label, churn_proba, retain_proba, risk_level, risk_color


def calculate_financial_impact(inputs: Dict[str, Any], churn_proba: float) -> Dict[str, Any]:
    """
    Calculates Customer Lifetime Value (CLV), Revenue at Risk, and Recommended Retention Budget.

    Formulas & Documented Business Assumptions:
    - Horizon: Customer lifespan horizon modeled as 36 months baseline minus accrued tenure
      (capped at 24 months tenure deduction, with a 12-month minimum retention floor).
      `expected_months = max(12.0, 36.0 - min(tenure, 24.0))`
    - CLV = Monthly Charges * Expected Horizon Months
    - Revenue at Risk = CLV * Churn Probability (Estimated exposure, not guaranteed future loss)
    - Recommended Budget = Revenue at Risk * 15% (Heuristic policy cap for retention offers)
    """
    raw_tenure = inputs.get('tenure', inputs.get('Tenure Months', 12))
    raw_monthly = inputs.get('monthly_charges', inputs.get('Monthly Charges', 70.0))

    try:
        tenure = max(0.0, float(raw_tenure if raw_tenure is not None else 12))
    except (ValueError, TypeError):
        tenure = 12.0

    try:
        monthly = max(0.0, float(raw_monthly if raw_monthly is not None else 70.0))
    except (ValueError, TypeError):
        monthly = 70.0

    bounded_proba = max(0.0, min(1.0, float(churn_proba)))

    expected_months = max(12.0, 36.0 - min(tenure, 24.0))
    clv = round(monthly * expected_months, 2)
    revenue_at_risk = round(clv * bounded_proba, 2)
    recommended_budget = round(revenue_at_risk * 0.15, 2)

    return {
        "clv": clv,
        "monthly_charges": monthly,
        "revenue_at_risk": revenue_at_risk,
        "recommended_retention_budget": recommended_budget,
        "horizon_months": int(expected_months),
        "disclaimer": "Revenue at risk is a statistical estimate based on churn probability, not realized loss."
    }


def analyze_feature_contributions(model: Any, df_encoded: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """
    Calculates feature contribution toward churn probability.
    Supports linear models (via scaled log-odds coefficients) and ensemble/tree models (via feature importances).
    Reuses immutable preprocessor metadata and uses vectorized top-N selection for fast inference.
    """
    classifier = model.named_steps.get('classifier', model) if hasattr(model, "named_steps") else model
    preprocessor = model.named_steps.get('preprocessor') if hasattr(model, "named_steps") else None

    # Cached immutable feature names and model weights on model instance
    if not hasattr(model, "_cached_feature_names"):
        if preprocessor is not None and hasattr(preprocessor, "get_feature_names_out"):
            model._cached_feature_names = np.array(preprocessor.get_feature_names_out())
        elif hasattr(model, "feature_names_in_"):
            model._cached_feature_names = np.array(model.feature_names_in_)
        else:
            model._cached_feature_names = np.array(FEATURE_ORDER)

    feature_names = getattr(model, "_cached_feature_names", np.array(FEATURE_ORDER))

    if not hasattr(model, "_cached_coefs"):
        if hasattr(classifier, "coef_"):
            model._cached_coefs = classifier.coef_[0]
            model._is_linear = True
        elif hasattr(classifier, "feature_importances_"):
            model._cached_coefs = classifier.feature_importances_
            model._is_linear = False
        else:
            model._cached_coefs = np.zeros(len(feature_names))
            model._is_linear = False

    coefs = model._cached_coefs
    is_linear = getattr(model, "_is_linear", False)

    if preprocessor is not None:
        transformed_val = preprocessor.transform(df_encoded)
        if hasattr(transformed_val, "toarray"):
            transformed_val = transformed_val.toarray()
        values = transformed_val[0]
    else:
        values = df_encoded.iloc[0].values

    if is_linear:
        contributions = coefs * values
    else:
        contributions = coefs * (values - np.mean(values))

    raw_values = df_encoded.iloc[0].values
    top_indices = np.argsort(-contributions)[:top_n]

    records = [
        {
            'Feature': feature_names[i],
            'Coefficient': round(float(coefs[i]), 4),
            'Value': round(float(raw_values[i]), 2),
            'Contribution': round(float(contributions[i]), 4)
        }
        for i in top_indices
    ]
    return pd.DataFrame(records)


def compute_shap_contributions(model: Any, df_encoded: pd.DataFrame, top_n: int = 8) -> pd.DataFrame:
    """
    Computes SHAP attribution values if SHAP is available, falling back gracefully
    to log-odds / importance attribution if unavailable.
    """
    if not HAS_SHAP:
        return analyze_feature_contributions(model, df_encoded, top_n=top_n)

    try:
        classifier = model.named_steps.get('classifier', model) if hasattr(model, "named_steps") else model
        preprocessor = model.named_steps.get('preprocessor') if hasattr(model, "named_steps") else None

        if preprocessor is not None:
            transformed_val = preprocessor.transform(df_encoded)
            if hasattr(transformed_val, "toarray"):
                transformed_val = transformed_val.toarray()
            explainer = shap.LinearExplainer(classifier, transformed_val)
            shap_values = explainer.shap_values(transformed_val)
            shap_arr = shap_values[1][0] if isinstance(shap_values, list) and len(shap_values) > 1 else shap_values[0]
            feature_names = (
                preprocessor.get_feature_names_out()
                if hasattr(preprocessor, "get_feature_names_out")
                else FEATURE_ORDER
            )
        else:
            explainer = shap.Explainer(model, df_encoded)
            shap_res = explainer(df_encoded)
            shap_arr = shap_res.values[0]
            feature_names = df_encoded.columns.tolist()

        df_shap = pd.DataFrame({
            'Feature': feature_names,
            'SHAP_Value': shap_arr,
            'Absolute_Impact': np.abs(shap_arr)
        }).sort_values(by='Absolute_Impact', ascending=False).head(top_n)
        return df_shap
    except Exception as e:
        warnings.warn(f"SHAP computation warning: {e}. Falling back to log-odds driver analysis.")
        return analyze_feature_contributions(model, df_encoded, top_n=top_n)


def simulate_scenario_impact(model: Any, baseline_inputs: Dict[str, Any], scenario_overrides: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simulates a what-if counterfactual scenario (e.g. extending contract, offering bill discount).
    Estimates potential reduction in churn exposure.
    """
    modified_inputs = baseline_inputs.copy()
    modified_inputs.update(scenario_overrides)

    df_base = prepare_input_features(baseline_inputs)
    df_mod = prepare_input_features(modified_inputs)

    _, base_proba, _, base_risk, base_color = predict_customer_churn(model, df_base)
    _, mod_proba, _, mod_risk, mod_color = predict_customer_churn(model, df_mod)

    base_fin = calculate_financial_impact(baseline_inputs, base_proba)
    mod_fin = calculate_financial_impact(modified_inputs, mod_proba)

    prob_delta = round((mod_proba - base_proba) * 100, 1)
    revenue_delta = round(base_fin['revenue_at_risk'] - mod_fin['revenue_at_risk'], 2)

    return {
        "baseline": {
            "churn_probability": round(base_proba * 100, 1),
            "risk_level": base_risk,
            "risk_color": base_color,
            "financial": base_fin
        },
        "simulated": {
            "churn_probability": round(mod_proba * 100, 1),
            "risk_level": mod_risk,
            "risk_color": mod_color,
            "financial": mod_fin
        },
        "impact": {
            "probability_change_%": prob_delta,
            "revenue_saved_$": max(0.0, revenue_delta),
            "estimated_exposure_reduction_$": max(0.0, revenue_delta),
            "risk_reduced": base_proba > mod_proba,
            "disclaimer": "Simulated impact reflects model sensitivity and does not guarantee retention outcomes without intervention trial data."
        }
    }


def generate_business_recommendations(inputs: Dict[str, Any], churn_proba: float, risk_level: str) -> List[str]:
    """
    Generates actionable, rule-based business recommendations based on observed customer
    profile attributes and estimated churn risk tier.
    """
    recs = []

    contract = str(inputs.get('contract', inputs.get('Contract', 'Month-to-month'))).strip()
    payment = str(inputs.get('payment_method', inputs.get('Payment Method', ''))).strip()
    internet = str(inputs.get('internet_service', inputs.get('Internet Service', ''))).strip()
    tech_sup = str(inputs.get('tech_support', inputs.get('Tech Support', 'No'))).strip()
    online_sec = str(inputs.get('online_security', inputs.get('Online Security', 'No'))).strip()

    try:
        tenure = float(inputs.get('tenure', inputs.get('Tenure Months', 0)))
    except (ValueError, TypeError):
        tenure = 0.0

    try:
        monthly = float(inputs.get('monthly_charges', inputs.get('Monthly Charges', 0.0)))
    except (ValueError, TypeError):
        monthly = 0.0

    if risk_level == "High Risk":
        recs.append("🚨 **Immediate Retention Trigger**: Assign a dedicated Customer Success agent to contact this customer within 24 hours with a personalized retention offer.")
    elif risk_level == "Medium Risk":
        recs.append("⚠️ **Proactive Engagement**: Target this customer with promotional retention campaigns and plan optimization before contract renewal.")
    else:
        recs.append("✅ **Loyalty Program Candidate**: Customer is stable. Consider upselling premium services or introducing loyalty rewards.")

    if contract.lower() == 'month-to-month':
        recs.append("📜 **Contract Upgrade Offer**: Month-to-month contracts have 4x higher churn risk. Offer a **15% annual discount** for switching to a 1-year or 2-year contract.")

    if 'electronic check' in payment.lower():
        recs.append("💳 **Automated Payment Incentive**: Electronic check users have high churn correlation. Offer a **$10 one-time bill credit** to enroll in Auto-Pay via Credit Card or Bank Transfer.")

    if 'fiber optic' in internet.lower() and tech_sup.lower() in {'no', 'false', '0'}:
        recs.append("🛠️ **Bundled Tech Support**: Fiber optic customers without Tech Support experience higher service friction. Offer **3 months of complimentary Tech Support**.")

    if internet.lower() not in {'no', 'none'} and online_sec.lower() in {'no', 'false', '0'}:
        recs.append("🔒 **Security Bundle Promotion**: Add Online Security package at a discounted rate to increase service stickiness.")

    if tenure < 12:
        recs.append("🎁 **New Customer Onboarding**: Customer is in the critical first year. Send targeted onboarding guides and usage satisfaction surveys.")

    if monthly > 80.0:
        recs.append(f"💰 **Bill Optimization Review**: High monthly bill (${monthly:.2f}) detected. Conduct a plan review to optimize features and offer tailored discounts.")

    return recs
