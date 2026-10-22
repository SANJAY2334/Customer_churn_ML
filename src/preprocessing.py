"""
preprocessing.py
----------------
Module to convert raw customer input dictionary into the exact 30 encoded
feature columns expected by the trained Machine Learning models.

Feature Schema (30 columns in strict order):
 1. Tenure Months
 2. Monthly Charges
 3. Total Charges
 4. Gender_Male
 5. Senior Citizen_Yes
 6. Partner_Yes
 7. Dependents_Yes
 8. Phone Service_Yes
 9. Multiple Lines_No phone service
10. Multiple Lines_Yes
11. Internet Service_Fiber optic
12. Internet Service_No
13. Online Security_No internet service
14. Online Security_Yes
15. Online Backup_No internet service
16. Online Backup_Yes
17. Device Protection_No internet service
18. Device Protection_Yes
19. Tech Support_No internet service
20. Tech Support_Yes
21. Streaming TV_No internet service
22. Streaming TV_Yes
23. Streaming Movies_No internet service
24. Streaming Movies_Yes
25. Contract_One year
26. Contract_Two year
27. Paperless Billing_Yes
28. Payment Method_Credit card (automatic)
29. Payment Method_Electronic check
30. Payment Method_Mailed check
"""
from __future__ import annotations

import re
from typing import Any, Dict
import numpy as np
import pandas as pd

FEATURE_ORDER = [
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
CATEGORICAL_COLS = [c for c in FEATURE_ORDER if c not in NUMERICAL_COLS]


def _is_truthy(val: Any) -> bool:
    """Evaluates whether an arbitrary input represents a boolean True."""
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in {"yes", "true", "1", "1.0", "y"}


def prepare_input_features(inputs: Dict[str, Any]) -> pd.DataFrame:
    """
    Transforms a dictionary of raw customer inputs into a single-row DataFrame
    with 30 features ordered exactly as required by the trained model pipeline.

    Defensively validates numerical ranges and categorical dependencies.
    """
    if not isinstance(inputs, dict):
        raise TypeError(f"Expected input payload to be a dictionary, got {type(inputs).__name__}")

    # Extract & validate numerical features
    try:
        raw_tenure = inputs.get('tenure', inputs.get('Tenure Months', 0))
        tenure = max(0.0, float(raw_tenure if raw_tenure is not None else 0))
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid tenure value: {e}")

    try:
        raw_monthly = inputs.get('monthly_charges', inputs.get('Monthly Charges', 0.0))
        monthly_charges = max(0.0, float(raw_monthly if raw_monthly is not None else 0.0))
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid monthly_charges value: {e}")

    raw_total = inputs.get('total_charges', inputs.get('Total Charges', None))
    if raw_total is None or str(raw_total).strip() == "" or str(raw_total).lower() == "none":
        total_charges = tenure * monthly_charges
    else:
        try:
            val = float(raw_total)
            total_charges = max(0.0, val) if val > 0 else (tenure * monthly_charges)
        except (ValueError, TypeError):
            total_charges = tenure * monthly_charges

    # Categorical logic mapping
    gender = str(inputs.get('gender', inputs.get('Gender', 'Female'))).strip()
    senior = inputs.get('senior_citizen', inputs.get('Senior Citizen', 'No'))
    partner = inputs.get('partner', inputs.get('Partner', 'No'))
    dependents = inputs.get('dependents', inputs.get('Dependents', 'No'))
    phone = str(inputs.get('phone_service', inputs.get('Phone Service', 'Yes'))).strip()
    multiple_lines = str(inputs.get('multiple_lines', inputs.get('Multiple Lines', 'No'))).strip()
    internet = str(inputs.get('internet_service', inputs.get('Internet Service', 'DSL'))).strip()
    online_sec = inputs.get('online_security', inputs.get('Online Security', 'No'))
    online_bkp = inputs.get('online_backup', inputs.get('Online Backup', 'No'))
    dev_prot = inputs.get('device_protection', inputs.get('Device Protection', 'No'))
    tech_sup = inputs.get('tech_support', inputs.get('Tech Support', 'No'))
    stream_tv = inputs.get('streaming_tv', inputs.get('Streaming TV', 'No'))
    stream_mov = inputs.get('streaming_movies', inputs.get('Streaming Movies', 'No'))
    contract = str(inputs.get('contract', inputs.get('Contract', 'Month-to-month'))).strip()
    paperless = inputs.get('paperless_billing', inputs.get('Paperless Billing', 'Yes'))
    payment = str(inputs.get('payment_method', inputs.get('Payment Method', 'Electronic check'))).strip()

    is_no_internet = internet.lower() in {'no', 'no internet', 'none'}
    is_no_phone = phone.lower() in {'no', 'false', '0'}

    row_data = {
        'Tenure Months': tenure,
        'Monthly Charges': monthly_charges,
        'Total Charges': total_charges,

        # Demographics
        'Gender_Male': 1 if gender.lower() == 'male' else 0,
        'Senior Citizen_Yes': 1 if _is_truthy(senior) else 0,
        'Partner_Yes': 1 if _is_truthy(partner) else 0,
        'Dependents_Yes': 1 if _is_truthy(dependents) else 0,

        # Phone Services
        'Phone Service_Yes': 1 if not is_no_phone else 0,
        'Multiple Lines_No phone service': 1 if is_no_phone else 0,
        'Multiple Lines_Yes': 1 if (not is_no_phone and _is_truthy(multiple_lines)) else 0,

        # Internet Services
        'Internet Service_Fiber optic': 1 if internet.lower() == 'fiber optic' else 0,
        'Internet Service_No': 1 if is_no_internet else 0,

        # Internet Add-on Services
        'Online Security_No internet service': 1 if is_no_internet else 0,
        'Online Security_Yes': 1 if (not is_no_internet and _is_truthy(online_sec)) else 0,

        'Online Backup_No internet service': 1 if is_no_internet else 0,
        'Online Backup_Yes': 1 if (not is_no_internet and _is_truthy(online_bkp)) else 0,

        'Device Protection_No internet service': 1 if is_no_internet else 0,
        'Device Protection_Yes': 1 if (not is_no_internet and _is_truthy(dev_prot)) else 0,

        'Tech Support_No internet service': 1 if is_no_internet else 0,
        'Tech Support_Yes': 1 if (not is_no_internet and _is_truthy(tech_sup)) else 0,

        'Streaming TV_No internet service': 1 if is_no_internet else 0,
        'Streaming TV_Yes': 1 if (not is_no_internet and _is_truthy(stream_tv)) else 0,

        'Streaming Movies_No internet service': 1 if is_no_internet else 0,
        'Streaming Movies_Yes': 1 if (not is_no_internet and _is_truthy(stream_mov)) else 0,

        # Contract & Billing
        'Contract_One year': 1 if contract.lower() == 'one year' else 0,
        'Contract_Two year': 1 if contract.lower() == 'two year' else 0,
        'Paperless Billing_Yes': 1 if _is_truthy(paperless) else 0,

        # Payment Methods
        'Payment Method_Credit card (automatic)': 1 if 'credit card' in payment.lower() else 0,
        'Payment Method_Electronic check': 1 if 'electronic check' in payment.lower() else 0,
        'Payment Method_Mailed check': 1 if 'mailed check' in payment.lower() else 0
    }

    df_encoded = pd.DataFrame([row_data])[FEATURE_ORDER]
    return df_encoded
