"""
test_api.py
-----------
Integration tests for Flask REST API endpoints, Swagger specifications,
request validation, file uploads, and error handling.
"""

import io
import json
import pytest


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Customer Churn" in response.data


def test_swagger_ui_and_spec(client):
    ui_resp = client.get("/apidocs/")
    assert ui_resp.status_code == 200

    spec_resp = client.get("/apispec_1.json")
    assert spec_resp.status_code == 200
    spec_data = json.loads(spec_resp.data)
    assert "swagger" in spec_data or "openapi" in spec_data
    assert "/predict" in spec_data["paths"]
    assert "/api/health" in spec_data["paths"]


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "healthy"
    assert data["model_loaded"] is True
    assert "uptime_seconds" in data
    assert "active_threshold" in data


def test_metrics_endpoint(client):
    response = client.get("/api/metrics")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "best_model" in data
    assert "metrics" in data


def test_predict_success(client, sample_customer_high_risk):
    response = client.post(
        "/predict",
        data=json.dumps(sample_customer_high_risk),
        content_type="application/json"
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert "prediction" in data
    assert "churn_probability" in data
    assert "risk_level" in data
    assert "risk_action" in data
    assert "recommendations" in data
    assert "top_drivers" in data
    assert "threshold_applied" in data
    assert "model_version" in data


def test_predict_invalid_payload(client):
    response = client.post(
        "/predict",
        data=json.dumps({"tenure": "not_a_number", "monthly_charges": "abc"}),
        content_type="application/json"
    )
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data["status"] == "error"


def test_predict_empty_payload(client):
    response = client.post(
        "/predict",
        data="",
        content_type="application/json"
    )
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data["status"] == "error"


def test_batch_predict_success(client):
    csv_content = (
        "Tenure Months,Monthly Charges,Total Charges,Gender,Senior Citizen,Partner,Dependents,"
        "Phone Service,Multiple Lines,Internet Service,Online Security,Online Backup,Device Protection,"
        "Tech Support,Streaming TV,Streaming Movies,Contract,Paperless Billing,Payment Method\n"
        "1,70.5,70.5,Female,No,No,No,Yes,No,Fiber optic,No,No,No,No,No,No,Month-to-month,Yes,Electronic check\n"
        "48,20.0,960.0,Male,No,Yes,Yes,Yes,No,No,No internet service,No internet service,No internet service,No internet service,No internet service,No internet service,Two year,No,Mailed check\n"
    )
    data = {
        'file': (io.BytesIO(csv_content.encode('utf-8')), 'test_customers.csv')
    }
    response = client.post(
        "/api/batch_predict",
        data=data,
        content_type='multipart/form-data'
    )
    assert response.status_code == 200
    res_data = json.loads(response.data)
    assert res_data["status"] == "success"
    assert res_data["summary"]["total_records"] == 2
    assert len(res_data["preview"]) == 2


def test_batch_predict_missing_file(client):
    response = client.post("/api/batch_predict", data={})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data["status"] == "error"


def test_batch_predict_non_csv_file(client):
    data = {
        'file': (io.BytesIO(b"some binary data"), 'image.png')
    }
    response = client.post(
        "/api/batch_predict",
        data=data,
        content_type='multipart/form-data'
    )
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data["status"] == "error"
    assert "Only CSV" in data["message"]


def test_batch_predict_empty_csv(client):
    data = {
        'file': (io.BytesIO(b""), 'empty.csv')
    }
    response = client.post(
        "/api/batch_predict",
        data=data,
        content_type='multipart/form-data'
    )
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data["status"] == "error"


def test_prioritize_api_success(client):
    payload = {
        "customers": [
            {
                "customerID": "CUST-1",
                "tenure": 2,
                "monthly_charges": 95.0,
                "contract": "Month-to-month",
                "internet_service": "Fiber optic"
            },
            {
                "customerID": "CUST-2",
                "tenure": 48,
                "monthly_charges": 25.0,
                "contract": "Two year",
                "internet_service": "No"
            }
        ],
        "weight_churn": 0.70,
        "weight_clv": 0.30
    }
    response = client.post("/api/prioritize", json=payload)
    assert response.status_code == 200
    res_data = json.loads(response.data)
    assert res_data["status"] == "success"
    assert res_data["total_customers"] == 2
    assert len(res_data["prioritized_customers"]) == 2
    # Verify priority fields attached
    first = res_data["prioritized_customers"][0]
    assert "Priority_Score" in first
    assert "Priority_Tier" in first
    assert "Priority_Rank" in first
    assert "disclaimer" in res_data


def test_prioritize_api_empty_customers(client):
    response = client.post("/api/prioritize", json={"customers": []})
    assert response.status_code == 400
    res_data = json.loads(response.data)
    assert res_data["status"] == "error"


def test_simulate_retention_api(client):
    payload = {
        "assumed_reduction_rate": 0.20,
        "cost_per_intervention": 25.0,
        "budget_cap": 2000.0,
        "target_cohort": ["Urgent", "High"]
    }
    response = client.post("/api/simulate_retention", json=payload)
    assert response.status_code == 200
    res_data = json.loads(response.data)
    assert res_data["status"] == "success"
    assert res_data["targeted_customers"] > 0
    assert res_data["total_campaign_cost_$"] <= 2000.0
    assert "gross_exposure_reduction_$" in res_data
    assert "net_scenario_return_$" in res_data
    assert "disclaimer" in res_data


def test_overview_endpoint(client):
    response = client.get("/api/overview")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert data["kpis"]["total_customers"] == 7043
    assert data["kpis"]["at_risk_count"] == 1869
    assert len(data["churn_risk_trends"]["months"]) == 12
    assert len(data["top_risk_factors"]) == 5


def test_customers_endpoint(client):
    response = client.get("/api/customers?page=1&page_size=5")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert data["total"] == 7043
    assert len(data["items"]) == 5
    assert data["items"][0]["customer_id"] == "7590-VHVEG"

    # Filter by risk level
    response_high = client.get("/api/customers?risk_level=High&page=1&page_size=5")
    assert response_high.status_code == 200
    data_high = json.loads(response_high.data)
    assert len(data_high["items"]) > 0
    assert all(item["risk_level"] == "High" for item in data_high["items"])


def test_sample_csv_endpoint(client):
    response = client.get("/api/sample_csv")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/csv")
    content = response.data.decode("utf-8")
    lines = content.strip().splitlines()
    assert len(lines) >= 10
    assert "customerID" in lines[0]


def test_system_telemetry_endpoint(client):
    response = client.get("/api/system_telemetry")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert "model_performance" in data
    assert "service_health" in data
    assert "feature_drift" in data
    assert "system_information" in data
