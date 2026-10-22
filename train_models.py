"""
train_models.py
---------------
Backward-compatible wrapper for the canonical training pipeline.
Delegates model training, cross-validation threshold tuning, and artifact generation
to `train_model.py`.
"""

import sys
from pathlib import Path
from train_model import train_model, FEATURE_COLS, NUMERICAL_COLS, CATEGORICAL_COLS

def train_and_evaluate():
    """Wrapper function preserving legacy entry-point signature."""
    print("[*] Invoking canonical training pipeline via train_model.py ...")
    artifact = train_model()
    return artifact.get("metrics", {})

if __name__ == "__main__":
    train_and_evaluate()
