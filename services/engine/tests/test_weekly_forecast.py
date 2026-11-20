import pytest
from fastapi.testclient import TestClient

from services.engine.main import app

client = TestClient(app)


def test_bundled_release_forecasts_six_weeks_from_last_observation():
    response = client.post("/v1/predict", json={})
    assert response.status_code == 200
    result = response.json()
    assert result["model"] == "RF_shallow"
    assert result["as_of"] == {"year": 2022, "week": 52}
    assert result["city"][0]["expected_cases"] == pytest.approx(63.79985, abs=1e-5)
    assert len(result["city"]) == 6
    assert len(result["barangays"]) == 852
    for h, city in enumerate(result["city"], 1):
        assert (city["year"], city["week"], city["horizon"]) == (2023, h, h)
        rows = [row for row in result["barangays"] if row["horizon"] == h]
        assert len({row["barangay_code"] for row in rows}) == 142
        assert sum(row["expected_cases"] for row in rows) == pytest.approx(city["expected_cases"])


def test_updated_origin_and_scenario_use_production_contract():
    updates = [dict(year=2024, week=week, city_cases=55) for week in range(1, 53)]
    updates.insert(0, dict(year=2023, week=52, city_cases=55))
    result = client.post("/v1/predict", json=dict(
        weeks_ahead=2, city_updates=updates, multiplier=2, duration=2, ramp=True,
        local_updates=[dict(year=2024, week=52, barangay_code="PH1307404001", cases=2)],
    )).json()
    assert result["as_of"] == {"year": 2024, "week": 52}
    assert result["feature_history_through"] == result["trained_through"] == 2022
    assert len(result["barangays"]) == 284
    for week, row in enumerate(result["city"], 1):
        assert (row["year"], row["week"]) == (2025, week)
        assert row["scenario_expected_cases"] == pytest.approx(row["expected_cases"] * (1 + week / 2))


def test_forecast_rejects_missing_weeks_and_out_of_range_horizon():
    response = client.post("/v1/predict", json={"city_updates": [dict(year=2025, week=52, city_cases=100)]})
    assert response.status_code == 400
    assert "53 consecutive" in response.json()["detail"]["message"]
    assert client.post("/v1/predict", json={"weeks_ahead": 7}).status_code == 422


def test_observation_upload_limit_is_scoped_to_prediction():
    body = b" " * 33000 + b'{"weeks_ahead": 1}'
    for path, status in [("/v1/predict", 200), ("/v1/qc-simulation", 413)]:
        assert client.post(path, content=body, headers={"content-type": "application/json"}).status_code == status
    assert client.post("/v1/predict", content=b" " * (2 * 1024**2 + 1)).status_code == 413


def test_missing_release_files_report_unavailability(monkeypatch, tmp_path):
    from production.surgewise import predictor

    monkeypatch.setattr(predictor, "PACKAGE", tmp_path)
    predictor.assets.cache_clear()
    response = client.post("/v1/predict", json={})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "FORECAST_MODEL_UNAVAILABLE"


def test_simulators_fail_closed_if_production_forecaster_is_unavailable(monkeypatch):
    from production.surgewise import predictor

    def unavailable(**kwargs):
        raise FileNotFoundError("missing release file")

    monkeypatch.setattr(predictor, "predict", unavailable)
    assert client.get("/v1/qc-simulation").status_code == 200  # Imputed historical inputs are independent.
    response = client.get("/v1/future-simulation")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PRODUCTION_FORECAST_UNAVAILABLE"
