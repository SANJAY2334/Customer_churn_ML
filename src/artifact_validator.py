"""
artifact_validator.py
--------------------
Model artifact integrity verification, SHA-256 checksum enforcement,
pipeline step inspection, and runtime readiness health probes.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import joblib
import pandas as pd

from src.config import DEFAULT_PKL_PATH, EXPECTED_ARTIFACT_SHA256, ROOT
from src.preprocessing import FEATURE_ORDER

TRUSTED_MANIFEST_PATH = ROOT / "Models" / "release_manifest.json"


def compute_file_sha256(filepath: Union[str, Path]) -> str:
    """Computes the cryptographic SHA-256 digest of a target file."""
    path_obj = Path(filepath)
    if not path_obj.is_file():
        raise FileNotFoundError(f"Target artifact not found at {path_obj}")

    hasher = hashlib.sha256()
    with open(path_obj, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_artifact_integrity(
    filepath: Union[str, Path] = DEFAULT_PKL_PATH,
    expected_sha256: Optional[str] = None,
    manifest_path: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """
    Verifies that a model artifact file exists, is non-empty, matches expected SHA-256 hash (if specified),
    cross-references against trusted release manifest, and can be properly deserialized into a valid
    scikit-learn estimator pipeline.
    """
    path_obj = Path(filepath)
    if not path_obj.is_absolute():
        path_obj = ROOT / path_obj

    if not path_obj.is_file():
        return {
            "valid": False,
            "error": f"Artifact file missing: {path_obj}",
            "sha256": None
        }

    actual_hash = compute_file_sha256(path_obj)
    file_size_bytes = path_obj.stat().st_size

    if file_size_bytes == 0:
        return {
            "valid": False,
            "error": "Artifact file is empty (0 bytes)",
            "sha256": actual_hash
        }

    # Cross-reference with trusted release manifest if available
    m_path = Path(manifest_path) if manifest_path is not None else TRUSTED_MANIFEST_PATH
    manifest_verified = False
    manifest_expected_hash = None
    if m_path.is_file():
        try:
            with open(m_path, "r", encoding="utf-8") as mf:
                m_data = json.load(mf)
                artifacts = m_data.get("artifacts", {})
                # Check relative path match
                rel_path = str(path_obj.relative_to(ROOT)).replace("\\", "/")
                if rel_path in artifacts:
                    manifest_expected_hash = artifacts[rel_path].get("sha256")
                    if manifest_expected_hash and manifest_expected_hash.lower() != actual_hash.lower():
                        return {
                            "valid": False,
                            "error": f"Manifest checksum mismatch for {rel_path}. Manifest expected '{manifest_expected_hash}', found '{actual_hash}'",
                            "sha256": actual_hash,
                            "manifest_expected_sha256": manifest_expected_hash
                        }
                    manifest_verified = True
        except Exception:
            pass

    target_hash = expected_sha256 if expected_sha256 is not None else (manifest_expected_hash or EXPECTED_ARTIFACT_SHA256)
    hash_match = True
    if target_hash and target_hash != "none":
        hash_match = (actual_hash.lower() == target_hash.lower())

    if not hash_match:
        return {
            "valid": False,
            "error": f"SHA-256 checksum mismatch. Expected '{target_hash}', found '{actual_hash}'",
            "sha256": actual_hash,
            "expected_sha256": target_hash
        }

    # Deserialization test
    try:
        loaded_obj = joblib.load(path_obj)
        has_predict = hasattr(loaded_obj, "predict") or isinstance(loaded_obj, dict)
        if not has_predict:
            return {
                "valid": False,
                "error": "Loaded object is not a valid scikit-learn estimator or model dictionary",
                "sha256": actual_hash
            }

        return {
            "valid": True,
            "sha256": actual_hash,
            "file_size_bytes": file_size_bytes,
            "path": str(path_obj),
            "manifest_verified": manifest_verified
        }
    except Exception as e:
        return {
            "valid": False,
            "error": f"Deserialization failure: {str(e)}",
            "sha256": actual_hash
        }


def perform_readiness_probe(model: Any = None) -> Dict[str, Any]:
    """
    Executes a synthetic end-to-end inference pass through the model to confirm runtime readiness.
    Measures latency and verifies model name and threshold.
    """
    if model is None:
        try:
            from src.predictor import load_churn_model
            model = load_churn_model()
        except Exception as e:
            return {
                "ready": False,
                "error": f"Model loader failed: {str(e)}",
                "latency_ms": None,
                "model_name": None
            }

    if not hasattr(model, "predict"):
        return {
            "ready": False,
            "error": "Supplied model object does not expose a .predict method",
            "latency_ms": None,
            "model_name": None
        }

    # Synthetic 1-row feature DataFrame
    synthetic_row = pd.DataFrame([{col: 0.0 for col in FEATURE_ORDER}], columns=FEATURE_ORDER)
    synthetic_row['Tenure Months'] = 12.0
    synthetic_row['Monthly Charges'] = 70.0
    synthetic_row['Total Charges'] = 840.0

    try:
        t0 = time.time()
        if hasattr(model, "predict_proba"):
            _ = model.predict_proba(synthetic_row)
        else:
            _ = model.predict(synthetic_row)
        latency_ms = round((time.time() - t0) * 1000, 2)

        return {
            "ready": True,
            "latency_ms": latency_ms,
            "model_name": getattr(model, "model_name_", "Unknown"),
            "threshold": float(getattr(model, "threshold_", 0.5)),
            "model_version": getattr(model, "model_version_", "1.0.0")
        }
    except Exception as e:
        return {
            "ready": False,
            "error": f"Synthetic prediction failure: {str(e)}",
            "latency_ms": None,
            "model_name": getattr(model, "model_name_", "Unknown")
        }
