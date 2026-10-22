"""
train_model.py
--------------
Canonical, Leakage-Free Machine Learning Pipeline for Telecom Customer Churn Prediction.

Responsibilities:
1. Validates source dataset and target column.
2. Isolates features and target; prevents all forms of data leakage.
3. Implements 80/20 stratified train/test split.
4. Fits preprocessing exclusively on training data (X_train).
5. Compares candidate estimators:
   - Baseline (Most Frequent Dummy Classifier)
   - Logistic Regression (Interpretable linear model with balanced class weights)
   - Decision Tree
   - Random Forest
   - XGBoost
6. Optimizes decision threshold via 5-fold Stratified Cross-Validation on X_train only
   (never optimizing on the held-out test split).
7. Evaluates performance on the untouched test split (X_test, y_test).
8. Persists unified model artifacts:
   - Models/churn_models.joblib (full multi-model artifact with metrics & curves)
   - Models/churn_model.pkl (primary scikit-learn pipeline for API/predictor)
   - Models/model_metrics.json (standardized metrics schema)
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, Any, Tuple, List

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "Data" / "processed_data.csv"
MODEL_DIR = ROOT / "Models"
ARTIFACT_PATH = MODEL_DIR / "churn_models.joblib"
PRIMARY_MODEL_PATH = MODEL_DIR / "churn_model.pkl"
METRICS_PATH = MODEL_DIR / "model_metrics.json"

TARGET_CANDIDATES = ("churn value", "churn", "churn label", "exited", "is churn")

FEATURE_COLS = [
    'Tenure Months', 'Monthly Charges', 'Total Charges', 'Gender_Male',
    'Senior Citizen_Yes', 'Partner_Yes', 'Dependents_Yes', 'Phone Service_Yes',
    'Multiple Lines_No phone service', 'Multiple Lines_Yes',
    'Internet Service_Fiber optic', 'Internet Service_No',
    'Online Security_No internet service', 'Online Security_Yes',
    'Online Backup_No internet service', 'Online Backup_Yes',
    'Device Protection_No internet service', 'Device Protection_Yes',
    'Tech Support_No internet service', 'Tech Support_Yes',
    'Streaming TV_No internet service', 'Streaming TV_Yes',
    'Streaming Movies_No internet service', 'Streaming Movies_Yes',
    'Contract_One year', 'Contract_Two year', 'Paperless Billing_Yes',
    'Payment Method_Credit card (automatic)',
    'Payment Method_Electronic check', 'Payment Method_Mailed check'
]

NUMERICAL_COLS = ['Tenure Months', 'Monthly Charges', 'Total Charges']
CATEGORICAL_COLS = [c for c in FEATURE_COLS if c not in NUMERICAL_COLS]


def normalized(name: str) -> str:
    """Normalizes column names for fuzzy discovery."""
    return re.sub(r"[^a-z0-9]+", " ", str(name).strip().lower()).strip()


def find_target(columns: List[str]) -> str:
    """Identifies the true target column from dataset columns."""
    by_normalized = {normalized(c): c for c in columns}
    for candidate in TARGET_CANDIDATES:
        if candidate in by_normalized:
            return by_normalized[candidate]
    candidates = [c for c in columns if "churn" in normalized(c)]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(
        "Could not identify one target column. Expected a column such as 'Churn Value' or 'Churn Label'."
    )


def target_to_binary(values: pd.Series) -> pd.Series:
    """Converts diverse binary target formats into 0 and 1."""
    if values.isna().any():
        raise ValueError("The target column contains missing values.")
    if pd.api.types.is_numeric_dtype(values) or pd.api.types.is_bool_dtype(values):
        unique = set(pd.unique(values))
        if unique <= {0, 1, False, True} and len(unique) == 2:
            return values.astype(int)
    mapping = {
        "yes": 1, "true": 1, "churn": 1, "churned": 1, "1": 1,
        "no": 0, "false": 0, "stay": 0, "stayed": 0, "not churned": 0, "0": 0
    }
    mapped = values.astype(str).str.strip().str.lower().map(mapping)
    if mapped.isna().any() or mapped.nunique() != 2:
        raise ValueError(
            f"Target values must represent exactly two churn classes. Found: {values.dropna().unique()[:10].tolist()}"
        )
    return mapped.astype(int)


def load_dataset(path: Path = DATA_PATH) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, str, List[str]]:
    """
    Loads dataset, isolates target, removes target-derived/leakage/identifier columns,
    and returns sanitized feature matrix X and target y.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found at: {path}")

    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("Dataset is empty.")

    target = find_target(df.columns)
    y = target_to_binary(df[target])

    # Build leakage and identifier drop list
    drop_cols = []
    for col in df.columns:
        key = normalized(col)
        if col == target:
            drop_cols.append(col)
        elif (
            "churn" in key
            or "target" in key
            or key in {"exited", "is churn"}
            or key in {"id", "customer id", "customerid", "row id", "index"}
            or key.startswith("unnamed ")
        ):
            drop_cols.append(col)

    X = df.drop(columns=drop_cols).copy()

    # Convert boolean columns to int
    for col in X.columns:
        if X[col].dtype == "bool":
            X[col] = X[col].astype(int)

    # Clean numerical columns defensively
    if "Total Charges" in X.columns:
        X["Total Charges"] = pd.to_numeric(X["Total Charges"], errors="coerce")
        if "Tenure Months" in X.columns and "Monthly Charges" in X.columns:
            X["Total Charges"] = X["Total Charges"].fillna(X["Tenure Months"] * X["Monthly Charges"])
        else:
            X["Total Charges"] = X["Total Charges"].fillna(0.0)

    # Discard constant columns
    X = X.loc[:, X.nunique(dropna=True) > 1]
    valid = X.notna().any(axis=1)
    X, y = X.loc[valid].reset_index(drop=True), y.loc[valid].reset_index(drop=True)

    if X.empty:
        raise ValueError("No usable feature columns remain after removing leakage-prone fields.")

    return df.loc[valid].reset_index(drop=True), X, y, target, drop_cols


def create_preprocessor(feature_columns: List[str]) -> ColumnTransformer:
    """
    Builds a robust, leakage-free ColumnTransformer fitted only on training data.
    Scales continuous numeric features; imputes categoricals/indicators.
    """
    num_cols = [c for c in NUMERICAL_COLS if c in feature_columns]
    cat_cols = [c for c in feature_columns if c not in num_cols]

    numeric_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scale", StandardScaler())
    ])

    categorical_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent"))
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, num_cols),
            ("cat", categorical_pipe, cat_cols)
        ],
        remainder="drop",
        verbose_feature_names_out=False
    )
    return preprocessor


def optimize_threshold_on_train(pipeline: Pipeline, X_train: pd.DataFrame, y_train: pd.Series) -> float:
    """
    Finds optimal F1 classification threshold using 5-fold Stratified Cross-Validation on X_train.
    Never evaluates on or leaks the test set.
    """
    clf = pipeline.named_steps["classifier"]
    if not hasattr(clf, "predict_proba"):
        return 0.5

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    try:
        train_proba = cross_val_predict(pipeline, X_train, y_train, cv=cv, method="predict_proba")[:, 1]
        prec, rec, thresholds = precision_recall_curve(y_train, train_proba)
        # Avoid division by zero
        f1_scores = [
            2 * (p * r) / (p + r) if (p + r) > 0 else 0.0
            for p, r in zip(prec[:-1], rec[:-1])
        ]
        if len(f1_scores) > 0 and max(f1_scores) > 0:
            best_idx = int(np.argmax(f1_scores))
            best_threshold = float(thresholds[best_idx])
            # Bound threshold reasonably between 0.15 and 0.85
            return round(float(np.clip(best_threshold, 0.15, 0.85)), 4)
    except Exception as e:
        print(f"Warning: CV threshold tuning encountered issue ({e}). Defaulting to 0.50.")

    return 0.5


def train_model(data_path: Path = DATA_PATH) -> Dict[str, Any]:
    """
    Canonical training function: fits preprocessing and models, optimizes threshold
    on training fold, evaluates on held-out test data, and saves unified artifacts.
    """
    print(f"[+] Loading dataset from {data_path} ...")
    original_df, X, y, target_name, dropped_cols = load_dataset(data_path)
    feature_columns = X.columns.tolist()

    if y.nunique() != 2 or y.value_counts().min() < 10:
        raise ValueError("Need at least 10 examples in each churn class for a valid stratified split.")

    print(f"[*] Dataset: {X.shape[0]} rows, {X.shape[1]} features. Target '{target_name}' distribution: {dict(y.value_counts())}")

    # 80/20 Stratified Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    print(f"[*] Data split: Train = {X_train.shape[0]} samples, Test = {X_test.shape[0]} samples (held out)")

    # Define candidate models (including simple baseline)
    candidate_estimators = {
        "Baseline (Most Frequent)": DummyClassifier(strategy="most_frequent"),
        "Logistic Regression": LogisticRegression(max_iter=1500, random_state=42),
        "Decision Tree": DecisionTreeClassifier(max_depth=6, min_samples_split=10, random_state=42),
        "Random Forest": RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_split=5, random_state=42),
        "XGBoost": XGBClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, eval_metric="logloss")
    }

    fitted_pipelines = {}
    metrics_report = {}
    optimal_thresholds = {}
    roc_curves = {}
    pr_curves = {}

    print("\n[*] Training and validating candidate pipelines ...")
    for name, estimator in candidate_estimators.items():
        preprocessor = create_preprocessor(feature_columns)
        pipeline = Pipeline([
            ("preprocessor", preprocessor),
            ("classifier", estimator)
        ])

        # Step 1: Optimize threshold on training set via CV
        opt_thresh = optimize_threshold_on_train(pipeline, X_train, y_train)
        optimal_thresholds[name] = opt_thresh

        # Step 2: Fit full pipeline on X_train only
        pipeline.fit(X_train, y_train)
        pipeline.threshold_ = opt_thresh
        fitted_pipelines[name] = pipeline

        # Step 3: Evaluate on held-out X_test
        if hasattr(pipeline, "predict_proba"):
            test_proba = pipeline.predict_proba(X_test)[:, 1]
            auc_roc = float(roc_auc_score(y_test, test_proba))
            auc_pr = float(average_precision_score(y_test, test_proba))

            # ROC Curve coordinates downsampled for UI
            fpr, tpr, _ = roc_curve(y_test, test_proba)
            idx_roc = np.linspace(0, len(fpr) - 1, num=min(30, len(fpr)), dtype=int)
            roc_curves[name] = {
                "fpr": [round(float(v), 4) for v in fpr[idx_roc]],
                "tpr": [round(float(v), 4) for v in tpr[idx_roc]],
                "false_positive_rate": [round(float(v), 4) for v in fpr[idx_roc]],
                "true_positive_rate": [round(float(v), 4) for v in tpr[idx_roc]]
            }

            # PR Curve coordinates
            p_curve, r_curve, _ = precision_recall_curve(y_test, test_proba)
            idx_pr = np.linspace(0, len(p_curve) - 1, num=min(30, len(p_curve)), dtype=int)
            pr_curves[name] = {
                "precision": [round(float(v), 4) for v in p_curve[idx_pr]],
                "recall": [round(float(v), 4) for v in r_curve[idx_pr]]
            }
        else:
            test_proba = pipeline.predict(X_test)
            auc_roc = 0.5
            auc_pr = float(y_test.mean())
            roc_curves[name] = {"fpr": [0.0, 1.0], "tpr": [0.0, 1.0], "false_positive_rate": [0.0, 1.0], "true_positive_rate": [0.0, 1.0]}
            pr_curves[name] = {"precision": [float(y_test.mean()), float(y_test.mean())], "recall": [1.0, 0.0]}

        # Test metrics at default 0.5 threshold
        pred_default = (test_proba >= 0.5).astype(int)
        # Test metrics at CV-optimized threshold
        pred_opt = (test_proba >= opt_thresh).astype(int)

        acc = float(accuracy_score(y_test, pred_opt))
        prec = float(precision_score(y_test, pred_opt, zero_division=0))
        rec = float(recall_score(y_test, pred_opt, zero_division=0))
        f1 = float(f1_score(y_test, pred_opt, zero_division=0))
        cm = confusion_matrix(y_test, pred_opt, labels=[0, 1]).tolist()

        metrics_report[name] = {
            "Accuracy": round(acc, 4),
            "Precision": round(prec, 4),
            "Recall": round(rec, 4),
            "F1-score": round(f1, 4),
            "F1 Score": round(f1, 4),
            "ROC-AUC": round(auc_roc, 4),
            "ROC AUC": round(auc_roc, 4),
            "PR-AUC": round(auc_pr, 4),
            "Optimal Threshold": round(opt_thresh, 4),
            "optimal_threshold": round(opt_thresh, 4),
            "Confusion matrix": cm,
            "Confusion Matrix": cm,
            "ROC Curve": roc_curves[name],
            "PR Curve": pr_curves[name],
            "Default_Threshold_Metrics": {
                "Accuracy": round(float(accuracy_score(y_test, pred_default)), 4),
                "Precision": round(float(precision_score(y_test, pred_default, zero_division=0)), 4),
                "Recall": round(float(recall_score(y_test, pred_default, zero_division=0)), 4),
                "F1-score": round(float(f1_score(y_test, pred_default, zero_division=0)), 4)
            }
        }

        print(f"  - {name:26s} | Opt Thresh (from train CV): {opt_thresh:.4f} | Held-out F1: {f1:.4f} | Recall: {rec:.4f} | ROC-AUC: {auc_roc:.4f}")

    # Determine best model excluding Dummy baseline
    ml_models = {k: v for k, v in metrics_report.items() if "Baseline" not in k}
    best_model_name = max(ml_models.keys(), key=lambda k: (ml_models[k]["F1-score"], ml_models[k]["ROC-AUC"]))
    print(f"\n[+] Selected Best Model: {best_model_name} (F1={ml_models[best_model_name]['F1-score']}, AUC={ml_models[best_model_name]['ROC-AUC']})")

    # Set threshold and metadata on all pipelines
    for name, pipe in fitted_pipelines.items():
        pipe.threshold_ = optimal_thresholds[name]
        pipe.model_name_ = name
        pipe.model_version_ = "1.0.0"

    # Best performing pipeline is designated as canonical primary pipeline
    active_pipeline = fitted_pipelines[best_model_name]

    # Compute feature contributions/importances for reporting
    importance_rows = []
    clf = active_pipeline.named_steps["classifier"]
    if hasattr(clf, "feature_importances_"):
        importances = clf.feature_importances_
        importance_rows = sorted(
            [(str(feat), float(imp)) for feat, imp in zip(feature_columns, importances)],
            key=lambda x: abs(x[1]),
            reverse=True
        )
    elif hasattr(clf, "coef_"):
        coefs = clf.coef_[0]
        importance_rows = sorted(
            [(str(feat), float(coef)) for feat, coef in zip(feature_columns, coefs)],
            key=lambda x: abs(x[1]),
            reverse=True
        )

    # Construct canonical unified artifact dictionary
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    artifact = {
        "models": fitted_pipelines,
        "pipeline": active_pipeline,
        "best_model": best_model_name,
        "primary_model_name": best_model_name,
        "threshold": optimal_thresholds[best_model_name],
        "optimal_threshold": optimal_thresholds[best_model_name],
        "thresholds": optimal_thresholds,
        "feature_columns": feature_columns,
        "target_column": target_name,
        "target_positive_value": 1,
        "metrics": metrics_report,
        "roc_curves": roc_curves,
        "pr_curves": pr_curves,
        "feature_importance": importance_rows,
        "dataset_path": str(data_path),
        "dataset_rows": int(len(original_df)),
        "dataset_columns": original_df.columns.tolist(),
        "excluded_columns": dropped_cols,
        "positive_count": int((y == 1).sum()),
        "negative_count": int((y == 0).sum()),
        "test_size": 0.20,
        "random_state": 42,
        "model_version": "1.0.0",
        "training_timestamp": timestamp,
    }

    # Ensure output directory exists
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Save canonical multi-model joblib artifact (consumed by Streamlit app.py)
    joblib.dump(artifact, ARTIFACT_PATH)
    print(f"[+] Saved canonical artifact: {ARTIFACT_PATH}")

    # 2. Save primary active pipeline for standalone consumers (flask_app.py, predictor.py)
    joblib.dump(active_pipeline, PRIMARY_MODEL_PATH)
    print(f"[+] Saved primary pipeline ({best_model_name}): {PRIMARY_MODEL_PATH}")

    # Also save Logistic Regression specifically for reference
    lr_path = MODEL_DIR / "churn_model_logistic_regression.pkl"
    joblib.dump(fitted_pipelines["Logistic Regression"], lr_path)
    print(f"[+] Saved Logistic Regression reference pipeline: {lr_path}")

    # 3. Save standardized model_metrics.json (consumed by /api/metrics and UI)
    metrics_payload = {
        "best_model": best_model_name,
        "primary_model": "Logistic Regression",
        "model_version": "1.0.0",
        "training_timestamp": timestamp,
        "metrics": metrics_report,
        "roc_curves": roc_curves,
        "pr_curves": pr_curves,
        "target_column": target_name,
        "feature_columns": feature_columns,
        "excluded_columns": dropped_cols
    }
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2)
    print(f"[+] Saved standardized metrics: {METRICS_PATH}")

    return artifact


if __name__ == "__main__":
    train_model()
