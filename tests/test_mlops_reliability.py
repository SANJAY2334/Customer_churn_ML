"""
test_mlops_reliability.py
-------------------------
Unit tests for model artifact verification, cryptographic integrity,
Population Stability Index (PSI) drift monitoring, and performance degradation tracking.
"""
import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from src.artifact_validator import verify_artifact_integrity, perform_readiness_probe, compute_file_sha256
from src.monitoring import calculate_psi, detect_dataset_drift, evaluate_production_performance


def test_artifact_integrity_verification():
    # Verify default active artifact
    res = verify_artifact_integrity("Models/churn_model.pkl")
    assert res["valid"] is True
    assert len(res["sha256"]) == 64
    assert res["file_size_bytes"] > 0


def test_artifact_integrity_missing_file():
    res = verify_artifact_integrity("Models/non_existent_artifact_xyz.pkl")
    assert res["valid"] is False
    assert "missing" in res["error"].lower()


def test_artifact_integrity_checksum_mismatch():
    res = verify_artifact_integrity("Models/churn_model.pkl", expected_sha256="wrong_hash_12345")
    assert res["valid"] is False
    assert "mismatch" in res["error"].lower()


def test_readiness_probe_active_model():
    probe = perform_readiness_probe()
    assert probe["ready"] is True
    assert probe["model_name"] == "XGBoost"
    assert probe["threshold"] == 0.3236
    assert probe["latency_ms"] >= 0.0


def test_psi_identical_distribution():
    # Identical distributions should yield PSI ~ 0.0
    data = pd.Series(np.random.normal(50, 10, 1000))
    psi = calculate_psi(data, data)
    assert psi == 0.0 or psi < 0.02


def test_psi_shifted_distribution():
    # Shifted distributions should yield significant PSI
    baseline = pd.Series(np.random.normal(50, 10, 1000))
    shifted = pd.Series(np.random.normal(85, 10, 1000))
    psi = calculate_psi(baseline, shifted)
    assert psi >= 0.25  # High drift


def test_detect_dataset_drift_alert_level():
    # Baseline sample
    df_base = pd.DataFrame({
        "Tenure Months": np.random.uniform(1, 72, 500),
        "Monthly Charges": np.random.uniform(20, 120, 500)
    })
    # Same distribution
    res_stable = detect_dataset_drift(df_base, baseline_df=df_base)
    assert res_stable["status"] == "success"
    assert res_stable["overall_alert"] == "GREEN"

    # Shifted distribution
    df_drifted = pd.DataFrame({
        "Tenure Months": np.random.uniform(60, 72, 500),  # Heavy skew to high tenure
        "Monthly Charges": np.random.uniform(110, 120, 500)
    })
    res_drift = detect_dataset_drift(df_drifted, baseline_df=df_base)
    assert res_drift["status"] == "success"
    assert res_drift["overall_alert"] in ("YELLOW", "RED")
    assert res_drift["max_psi"] > 0.10


def test_evaluate_production_performance_stable_and_degraded():
    # Synthetic ground truth and predictions matching baseline
    y_true = [1, 0, 1, 0, 1, 0, 1, 0, 0, 0] * 50
    y_pred = [1, 0, 1, 0, 1, 0, 0, 0, 0, 0] * 50  # High concordance
    y_prob = [0.8, 0.1, 0.9, 0.2, 0.7, 0.1, 0.4, 0.1, 0.2, 0.1] * 50

    eval_res = evaluate_production_performance(y_true, y_pred, y_prob)
    assert "current_metrics" in eval_res
    assert eval_res["current_metrics"]["F1-score"] > 0.70

    # Degraded predictions
    y_bad = [0] * len(y_true)  # Model misses all churners
    eval_bad = evaluate_production_performance(y_true, y_bad, y_prob)
    assert eval_bad["status"] == "DEGRADED"
    assert eval_bad["degradation_alert"] is True


def test_performance_monitoring_delayed_or_unavailable_labels():
    # When ground-truth labels are delayed or not yet observed
    eval_pending = evaluate_production_performance(y_true=None)
    assert eval_pending["status"] == "PENDING_LABELS"
    assert eval_pending["degradation_alert"] is False
    assert eval_pending["current_metrics"] is None

    eval_empty = evaluate_production_performance(y_true=[])
    assert eval_empty["status"] == "PENDING_LABELS"


def test_manifest_verification_and_tamper_detection(tmp_path):
    # Valid check against real manifest
    res = verify_artifact_integrity("Models/churn_model.pkl")
    assert res["valid"] is True
    assert res["manifest_verified"] is True

    # Tampered manifest with forged expected hash
    fake_manifest = tmp_path / "forged_manifest.json"
    fake_manifest.write_text(
        '{"artifacts": {"Models/churn_model.pkl": {"sha256": "forged_malicious_hash_67890"}}}',
        encoding="utf-8"
    )
    tamper_check = verify_artifact_integrity("Models/churn_model.pkl", manifest_path=fake_manifest)
    assert tamper_check["valid"] is False
    assert "Manifest checksum mismatch" in tamper_check["error"]


def test_readiness_probe_on_corrupted_model():
    class BrokenModel:
        def predict(self, X):
            raise RuntimeError("Corrupted weights matrix: internal arithmetic fault")

    probe = perform_readiness_probe(BrokenModel())
    assert probe["ready"] is False
    assert "Synthetic prediction failure" in probe["error"]
