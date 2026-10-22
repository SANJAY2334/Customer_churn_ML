"""
load_test.py
------------
Bounded staging performance and latency benchmark.
Measures throughput, latency percentiles (p50, p90, p95, p99), error rates,
and server behavior under concurrent traffic.
"""
from __future__ import annotations

import concurrent.futures
import json
import ssl
import sys
import time
import urllib.request
import urllib.error
import numpy as np

BASE_URL = "https://127.0.0.1"
API_KEY = "test_production_api_key_4a9b8c7d6e5f"

PREDICT_PAYLOAD = json.dumps({
    "tenure": 12,
    "monthly_charges": 75.0,
    "total_charges": 900.0,
    "contract": "Month-to-month",
    "internet_service": "Fiber optic"
}).encode("utf-8")


def make_ssl_context(cafile: str = "nginx/certs/staging_ca.crt"):
    if cafile and Path(cafile).exists():
        return ssl.create_default_context(cafile=cafile)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


from pathlib import Path


def send_request(ctx, base_url: str, endpoint: str = "/predict", client_ip: str | None = None):
    is_https = base_url.startswith("https")
    headers = {
        "Host": "staging.telecom-churn.internal"
    }
    if client_ip:
        headers["X-Forwarded-For"] = client_ip

    if endpoint == "/api/live":
        req = urllib.request.Request(
            f"{base_url}/api/live",
            headers=headers,
            method="GET"
        )
    else:
        headers["Content-Type"] = "application/json"
        headers["X-API-Key"] = API_KEY
        req = urllib.request.Request(
            f"{base_url}{endpoint}",
            data=PREDICT_PAYLOAD,
            headers=headers,
            method="POST"
        )
    t0 = time.perf_counter()
    try:
        ssl_ctx = ctx if is_https else None
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15.0) as resp:
            status = resp.status
            body = resp.read()
            lat_ms = (time.perf_counter() - t0) * 1000
            return True, status, lat_ms
    except urllib.error.HTTPError as e:
        lat_ms = (time.perf_counter() - t0) * 1000
        return False, e.code, lat_ms
    except Exception as e:
        lat_ms = (time.perf_counter() - t0) * 1000
        return False, str(e), lat_ms


def run_benchmark(
    base_url: str = BASE_URL,
    endpoint: str = "/predict",
    total_requests: int = 25,
    max_workers: int = 4,
    warmup_requests: int = 10,
    cafile: str = "nginx/certs/staging_ca.crt",
    simulate_multi_client: bool = True
):
    ctx = make_ssl_context(cafile)

    if warmup_requests > 0:
        print(f"Executing {warmup_requests} warm-up requests against {base_url}{endpoint}...")
        for i in range(warmup_requests):
            ip = f"10.0.{i // 50}.{i % 50 + 1}" if simulate_multi_client else None
            send_request(ctx, base_url, endpoint, client_ip=ip)

    print(f"Starting benchmark on {base_url}{endpoint}: {total_requests} requests across {max_workers} worker threads (multi_client={simulate_multi_client})...")
    latencies = []
    successes = 0
    errors = 0
    status_codes = {}

    t_start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for i in range(total_requests):
            ip = f"10.0.{i // 50}.{i % 50 + 1}" if simulate_multi_client else None
            futures.append(executor.submit(send_request, ctx, base_url, endpoint, ip))

        for fut in concurrent.futures.as_completed(futures):
            ok, status, lat_ms = fut.result()
            latencies.append(lat_ms)
            status_codes[str(status)] = status_codes.get(str(status), 0) + 1
            if ok:
                successes += 1
            else:
                errors += 1

    total_duration = time.perf_counter() - t_start
    throughput = round(total_requests / total_duration, 2)

    lat_arr = np.array(latencies)
    results = {
        "base_url": base_url,
        "endpoint": endpoint,
        "total_requests": total_requests,
        "warmup_requests": warmup_requests,
        "concurrency_workers": max_workers,
        "successful_requests": successes,
        "failed_requests": errors,
        "status_distribution": status_codes,
        "total_duration_seconds": round(total_duration, 2),
        "throughput_req_per_sec": throughput,
        "latency_percentiles_ms": {
            "min": round(float(np.min(lat_arr)), 2),
            "p50_median": round(float(np.percentile(lat_arr, 50)), 2),
            "p90": round(float(np.percentile(lat_arr, 90)), 2),
            "p95": round(float(np.percentile(lat_arr, 95)), 2),
            "p99": round(float(np.percentile(lat_arr, 99)), 2),
            "max": round(float(np.max(lat_arr)), 2),
            "mean": round(float(np.mean(lat_arr)), 2)
        }
    }
    return results


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    ep = sys.argv[3] if len(sys.argv) > 3 else "/predict"
    b_url = sys.argv[4] if len(sys.argv) > 4 else BASE_URL
    warm = int(sys.argv[5]) if len(sys.argv) > 5 else 10
    ca = sys.argv[6] if len(sys.argv) > 6 else "nginx/certs/staging_ca.crt"
    multi = sys.argv[7].lower() in ("true", "1") if len(sys.argv) > 7 else True
    benchmark_results = run_benchmark(
        base_url=b_url,
        endpoint=ep,
        total_requests=count,
        max_workers=workers,
        warmup_requests=warm,
        cafile=ca,
        simulate_multi_client=multi
    )
    print("\nBENCHMARK_RESULTS_START")
    print(json.dumps(benchmark_results, indent=2))
    print("BENCHMARK_RESULTS_END")
