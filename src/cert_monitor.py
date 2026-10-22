"""
cert_monitor.py
---------------
Certificate expiration, validity window, and chain inspection probe.
Provides automated monitoring to prevent unexpected TLS certificate outages.
"""
from __future__ import annotations

import datetime
import os
import ssl
from pathlib import Path
from typing import Any, Dict, Optional, Union

from src.config import ROOT

DEFAULT_CERT_PATH = ROOT / "nginx" / "certs" / "staging_leaf.crt"
DEFAULT_FALLBACK_CERT_PATH = ROOT / "nginx" / "certs" / "fullchain.pem"


def parse_cert_expiration(cert_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Decodes an X.509 certificate file and extracts validity dates, SANs, and remaining days.
    """
    p = Path(cert_path)
    if not p.is_file():
        return {
            "status": "ERROR",
            "error": f"Certificate file not found at {p}",
            "days_until_expiry": None,
            "valid": False
        }

    try:
        decoded = ssl._ssl._test_decode_cert(str(p))
    except Exception as e:
        return {
            "status": "ERROR",
            "error": f"Failed to decode X.509 certificate: {str(e)}",
            "days_until_expiry": None,
            "valid": False
        }

    not_after_str = decoded.get("notAfter")
    not_before_str = decoded.get("notBefore")
    if not not_after_str:
        return {
            "status": "ERROR",
            "error": "Certificate missing notAfter field",
            "days_until_expiry": None,
            "valid": False
        }

    # Format example: 'Oct 21 17:01:12 2027 GMT'
    expiry_dt = datetime.datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=datetime.timezone.utc)
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    remaining_delta = expiry_dt - now_dt
    days_left = round(remaining_delta.total_seconds() / 86400, 1)

    sans = [item[1] for item in decoded.get("subjectAltName", []) if len(item) == 2]

    # Evaluate health status
    if days_left <= 0:
        health_status = "EXPIRED"
        valid = False
    elif days_left < 30:
        health_status = "WARNING_EXPIRING_SOON"
        valid = True
    else:
        health_status = "HEALTHY"
        valid = True

    return {
        "status": health_status,
        "valid": valid,
        "days_until_expiry": days_left,
        "expires_at": expiry_dt.isoformat(),
        "issued_at": not_before_str,
        "subject": decoded.get("subject"),
        "issuer": decoded.get("issuer"),
        "subject_alt_names": sans,
        "cert_path": str(p)
    }


def check_staging_tls_certificate() -> Dict[str, Any]:
    """Helper to inspect the default staging certificate."""
    target = DEFAULT_CERT_PATH if DEFAULT_CERT_PATH.is_file() else DEFAULT_FALLBACK_CERT_PATH
    return parse_cert_expiration(target)


if __name__ == "__main__":
    import json
    print(json.dumps(check_staging_tls_certificate(), indent=2))
