"""Contract checks against the supplied RandomForest prediction CSV."""
from fastapi.testclient import TestClient
import pytest

from services.engine.main import app

client = TestClient(app)
URL = "/v1/synthetic-barangay-simulation"


def test_default_model_matches_saved_predictions_and_hospital_inputs():
    response = client.get(URL)
    assert response.status_code == 200, response.text
    data = response.json()
    evidence = data["syntheticForecast"]
    assert evidence["model"] == "RandomForest" and evidence["coverage"] == 142
    assert evidence["missingBarangays"] == []
    alicia = evidence["weeklyByBarangay"]["PH1307404001"]
    assert alicia == pytest.approx([1.0950387554185061, .8098656949826636, 1.1457872373576001, .905859601130265])
    for day in data["days"][1:]:
        row = next(b for b in day["barangays"] if b["barangayId"] == "PH1307404001")
        assert row["expectedCases"] == pytest.approx(alicia[(day["dayIndex"]-1)//7] / 7)
        assert sum(b["expectedCases"] for b in day["barangays"]) == pytest.approx(day["expectedCases"])
        assert abs(day["balanceError"]) < 1e-7
        assert day["bedForecast"]["lowerBeds"] is None and "caseRange" not in day
    assert data["periodSummary"]["caseRange"] is None
    assert data["days"][-1]["hotspotIds"] == [b["barangayId"] for b in data["periodSummary"]["barangays"][:10]]


def test_partial_window_counts_only_covered_barangays():
    response = client.post(URL, json={"startDate":"2024-01-31","endDate":"2024-02-08","allocationPolicy":"nearest","compareAllocation":True})
    assert response.status_code == 200, response.text
    data = response.json()
    f = data["syntheticForecast"]
    assert f["coverage"] == 141 and len(f["missingBarangays"]) == 1
    assert set(f["weeklyByBarangay"]).isdisjoint(b["id"] for b in f["missingBarangays"])
    assert len(data["context"]["hospitals"]) == 46
    assert set(data["allocationComparison"]) >= {"nearest", "optimized"}
    assert data["periodSummary"]["expectedCases"] == pytest.approx(sum(v[0]*5/7 + v[1]*3/7 for v in f["weeklyByBarangay"].values()))
    assert client.post(URL, json={"startDate":"2026-01-01","endDate":"2026-01-08"}).status_code == 422


def test_synthetic_identity_and_readiness_do_not_require_annual_model(monkeypatch):
    from services.engine.repositories import barangay_runs, synthetic_barangay
    def no_model(*_):
        raise barangay_runs.BarangayRankingUnavailable("Annual model absent in this test")
    monkeypatch.setattr(barangay_runs, "approved_ranking", no_model)
    assert client.get("/readiness").json()["syntheticBarangayForecast"]["ready"] is True
    data = client.get(URL).json()
    assert data["parameters"]["scenarioKind"] == "synthetic_replay"
    for day in data["days"][1:]:
        assert day["hotspotIds"] == data["days"][-1]["hotspotIds"]
    monkeypatch.setattr(synthetic_barangay, "DIGEST", "invalid-for-test")
    synthetic_barangay._decode.cache_clear()
    unavailable = client.get(URL)
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "SYNTHETIC_FORECAST_UNAVAILABLE"
    assert client.get("/readiness").json()["syntheticBarangayForecast"]["ready"] is False


def test_import_rejects_corrupt_keys_and_preserves_zero():
    from scripts.import_synthetic_barangay import collect
    base = {"model":"RandomForest", "barangay_code":"A", "origin_block":"105144", "prediction":"0"}
    rows = [dict(base, horizon=str(h), target_block=str(105144+h)) for h in range(1, 5)]
    assert collect(rows, {"A","B"}) == {105144:{"A":[0.0]*4}}
    for invalid in [rows + rows[:1], rows[:3]] + [
        [dict(rows[0], **change), *rows[1:]] for change in [
            {"barangay_code":"unknown"}, {"prediction":"nan"}, {"prediction":"-1"}, {"target_block":"105144"}]]:
        with pytest.raises(ValueError):
            collect(invalid, {"A","B"})


def test_year_end_uses_actual_block_length_and_unsupported_origin_is_rejected():
    # Final source block covers eight days in 2025. Use the whole block.
    result = client.post(URL, json={"startDate":"2025-12-24","endDate":"2026-01-01"})
    assert result.status_code == 200
    data = result.json()
    values = data["syntheticForecast"]["weeklyByBarangay"]["PH1307404001"]
    local = next(b for b in data["periodSummary"]["barangays"] if b["barangayId"]=="PH1307404001")
    assert local["cumulativeCases"] == pytest.approx(values[3])
    assert client.post(URL, json={"startDate":"2022-01-01","endDate":"2022-01-08"}).status_code == 422


def test_preference_matrix_applies_to_only_the_available_rf_demand():
    response = client.post(URL, json={"startDate": "2024-01-31", "endDate": "2024-02-02",
                                      "compareAllocation": True, "baselineOccupancy": 1, "surgeCapacity": 0})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["controlValues"]["arrivalSplitPolicy"] == "markov_preference"
    assert data["controlValues"]["allocationPolicy"] == "first_hospital"
    assert data["syntheticForecast"]["coverage"] == 141
    assert len(data["syntheticForecast"]["missingBarangays"]) == 1
    assert len(data["firstAdmissionComparison"]) == 2
    frame = data["days"][1]
    assert frame["arrivals"] == pytest.approx(sum(v[0] / 7 for v in data["syntheticForecast"]["weeklyByBarangay"].values()) * .15)
    assert sum(f["firstAdmissionsToday"] for f in frame["facilities"]) == pytest.approx(frame["arrivals"])
    assert sum(b["expectedBedsShort"] for b in frame["barangays"]) == pytest.approx(frame["bedForecast"]["expectedBeds"])
    assert frame["bedForecast"]["hospitalBedsShort"] == sum(f["bedForecast"]["additionalStaffedBedsNeeded"] for f in frame["facilities"])
    assert frame["bedForecast"]["lowerBeds"] is None


def test_first_admission_and_shortfall_follow_changing_local_week_and_stay():
    import csv
    from services.engine.upri_data import ROOT
    data = client.post(URL, json={"startDate": "2025-01-29", "endDate": "2025-02-12",
        "admissionDelayDays": 2, "lengthOfStayDays": 3, "baselineOccupancy": 1, "surgeCapacity": 0}).json()
    weekly = data["syntheticForecast"]["weeklyByBarangay"]
    site = "HOSP-614"
    with (ROOT / "data/processed/qc_first_admission_preference_v1/first_hospital_probabilities.csv").open() as stream:
        choices = {row["barangayId"]: float(row[site]) for row in csv.DictReader(stream)}
    for day in data["days"][3:]:
        i = day["dayIndex"]
        h = (i - 3) // 7
        demand = {code: weeks[h] / 7 * .15 for code, weeks in weekly.items()}
        hospital = next(f for f in day["facilities"] if f["facilityId"] == site)
        arrivals = sum(demand[b] * choices[b] for b in demand)
        assert hospital["firstAdmissionsToday"] == pytest.approx(arrivals)
        assert day["arrivalForecastHorizon"] == h + 1
        mix = data["context"]["firstAdmissionOriginSharesByHorizon"][str(h + 1)][site]
        b = "PH1307404001"
        assert mix[b] == pytest.approx(demand[b] * choices[b] / arrivals)
        expected_beds = sum(weekly[b][(j-3)//7] / 7 * .15 for j in range(max(3, i-2), i+1))
        place = next(row for row in day["barangays"] if row["barangayId"] == b)
        assert place["expectedBedsShort"] == pytest.approx(expected_beds)


def test_default_readiness_requires_approved_hospital_choice(monkeypatch):
    from services.engine.repositories import first_admission
    folder, _ = first_admission.MATRICES["markov_preference"]
    monkeypatch.setitem(first_admission.MATRICES, "markov_preference", (folder, "invalid-for-test"))
    status = client.get("/readiness").json()
    assert status["syntheticBarangayForecast"]["ready"]
    assert not status["defaultWorkspaceReady"]
    assert status["firstAdmissionPreference"]["code"] == "FIRST_ADMISSION_MATRIX_UNAVAILABLE"
