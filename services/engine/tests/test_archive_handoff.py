"""Check the public app contracts against the training archive's top-level outputs."""
import csv
from datetime import date, timedelta
import hashlib
import io
import json
from zipfile import ZipFile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from services.engine.main import app
from services.engine.upri_data import ROOT

ZIP = ROOT / "production/SurgeWise_80_10_10.zip"
client = TestClient(app)


def table(archive, path):
    with archive.open("SurgeWise_80_10_10/" + path) as stream:
        return list(csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")))


def test_web_forest_matches_both_archived_forecasts_for_every_barangay():
    with ZipFile(ZIP) as archive:
        updates = [{"year": int(r["year"]), "week": int(r["week"]), "city_cases": float(r["city_cases"])}
                   for r in table(archive, "examples/updates_example.csv")]
        for prefix, history in [("2023_w01_06", []), ("2023_w07_12_updated", updates)]:
            expected = table(archive, "outputs/forecasts/" + prefix + "_barangay.csv")
            actual = client.post("/v1/predict", json={"city_updates": history}).json()
            keyed = {(r["year"], r["week"], r["barangay_code"]): r["expected_cases"] for r in actual["barangays"]}
            assert len(keyed) == len(expected) == 852
            for r in expected:
                assert keyed[int(r["year"]), int(r["week"]), r["barangay_code"]] == pytest.approx(float(r["expected_cases"]), abs=1e-10)


def test_historical_reconstruction_each_year_and_cross_year():
    from services.engine.repositories import gp_runs
    with ZipFile(ZIP) as archive:
        raw = archive.read("SurgeWise_80_10_10/data/processed/gp_cases.csv")
        assert hashlib.sha256(raw).hexdigest() == gp_runs.GP_SHA256
    for year in range(2012, 2023):
        start = date(year, 1, 1)
        response = client.post("/v1/qc-simulation", json={"startDate": str(start), "endDate": str(start + timedelta(days=1)), "reconstructHistory": True})
        assert response.status_code == 200, response.text[:400]
        result = response.json()
        evidence = result["forecastEvidence"]
        assert evidence["caseSourceKind"] == "gp_reconstruction" and evidence["issueBlock"] is None
        assert len(result["days"][1]["facilities"]) == 46
        assert len(result["days"][1]["barangays"]) == 142
        assert result["days"][1]["balanceError"] == pytest.approx(0, abs=1e-8)
    for start, end, status in [("2012-12-25", "2013-01-08", 200), ("2022-12-31", "2023-01-01", 200),
                               ("2022-12-31", "2023-01-02", 422)]:
        assert client.post("/v1/qc-simulation", json={"startDate": start, "endDate": end}).status_code == status


def test_linked_forecast_reaches_same_hospitals_with_same_weekly_cases():
    request = {"weeks_ahead": 2, "multiplier": 1.5, "start": 2, "prepare_hospital_simulation": True}
    response = client.post("/v1/predict", json=request)
    assert response.status_code == 200, response.text
    forecast = response.json()
    ident = forecast["hospitalSimulation"]["forecastRunId"]
    response = client.get("/v1/qc-simulation", params={"weeklyForecastId": ident})
    assert response.status_code == 200, response.text[:400]
    movie = response.json()
    assert movie["parameters"]["forecastRunId"] == ident
    assert movie["periodSummary"]["expectedCases"] == pytest.approx(sum(w["scenario_expected_cases"] for w in forecast["city"]))
    for row in forecast["barangays"]:
        d = movie["days"][7 * row["horizon"]]
        b = next(b for b in d["barangays"] if b["barangayId"] == row["barangay_code"])
        assert b["baselineCases"] == pytest.approx(row["expected_cases"] / 7)
        assert b["expectedCases"] == pytest.approx(row["scenario_expected_cases"] / 7)


def test_simulation_results_include_all_forecast_weeks_and_respect_hospital_window(tmp_path, monkeypatch):
    from services.engine.repositories import weekly_handoff
    monkeypatch.setattr(weekly_handoff, "FOLDER", tmp_path)
    forecast = client.post("/v1/predict", json={"weeks_ahead": 6, "multiplier": 2, "start": 2,
                                                "prepare_hospital_simulation": True}).json()
    handoff = forecast["hospitalSimulation"]
    movie = client.post("/v1/qc-simulation", json={"weeklyForecastId": handoff["forecastRunId"],
        "mode": "hypothetical_shock", "startDate": handoff["startDate"], "endDate": handoff["endDate"],
        "hospitalizationRate": .2}).json()
    weeks = movie["forecastEvidence"]["weeklyCases"]
    assert len(weeks) == 6 and movie["durationDays"] == 28
    assert movie["parameters"]["hospitalizationRate"] == .2
    assert "scenarioCityCases" not in weeks[0]
    for week, city in zip(weeks, forecast["city"], strict=True):
        assert (week["year"], week["week"], week["cityCases"]) == (city["year"], city["week"], city["expected_cases"])
        assert week.get("scenarioCityCases", week["cityCases"]) == city["scenario_expected_cases"]
        local = [r for r in forecast["barangays"] if (r["year"], r["week"]) == (week["year"], week["week"])]
        assert week["barangayCases"] == {r["barangay_code"]: r["expected_cases"] for r in local}
        assert week.get("scenarioBarangayCases", week["barangayCases"]) == {
            r["barangay_code"]: r["scenario_expected_cases"] for r in local}
    assert movie["periodSummary"]["expectedCases"] == pytest.approx(sum(w["scenario_expected_cases"] for w in forecast["city"][:4]))


def test_past_only_forest_matches_every_archived_evaluation_target():
    from services.engine.repositories import gp_runs
    with ZipFile(ZIP) as archive:
        rows = table(archive, "outputs/evaluation/weekly_backtest.csv")
        metrics = table(archive, "outputs/evaluation/metrics.csv")
    rows = [r for r in rows if r["method"] == "RF_shallow" and r["protocol"] == "chronological"]
    starts, _ = gp_runs.archive_calendar()
    with np.load(gp_runs.RF_PATH, allow_pickle=False) as artifact:
        assert len(rows) == 104
        for row in rows:
            origin, horizon = int(row["origin"]), int(row["horizon"])
            values = artifact["cases"][origin - 467, horizon - 1]
            assert values.sum() == pytest.approx(float(row["pred_city"]), abs=1e-7)
    summary = json.loads((ROOT / "apps/web/public/data/qc-archive-forecast-validation.json").read_text())
    for protocol in summary["holdouts"]:
        score, = [r for r in metrics if (r["method"], r["protocol"], r["split"]) == ("RF_shallow", protocol["protocol"], "test")]
        assert protocol["cityMae"] == pytest.approx(float(score["city_MAE"]))
        assert protocol["cityWapePercent"] == pytest.approx(float(score["city_WAPE"]))
    # With an intra-week start, the whole simulated window still uses the same prior origin.
    for year in (2021, 2022):
        start = starts[(year - 2012) * 52] + timedelta(days=2)
        r = client.post("/v1/qc-simulation", json={"startDate": str(start), "endDate": str(start + timedelta(days=28)), "reconstructHistory": False})
        assert r.status_code == 200, r.text[:400]
        e = r.json()["forecastEvidence"]
        assert e["trainedThrough"] == 2020 and e["featureHistoryThrough"] == year - 1
        assert e["issueBlock"] == {"YR": year - 1, "WN": 52}
        assert r.json()["parameters"]["forecastRunId"].startswith("qc-holdout-replay-")


def test_archive_calendar_mass_and_unassigned_cases():
    from services.engine.repositories import gp_runs
    from production.surgewise import history
    starts, _ = gp_runs.archive_calendar()
    rows = history.city_history()
    index = next(i for i, r in enumerate(rows) if r["unassigned_expected_cases"] > 0)
    duration = (starts[index + 1] - starts[index]).days
    run = gp_runs.reconstruction_run(starts[index], duration)
    assert run["unassignedWindowCases"] == pytest.approx(rows[index]["unassigned_expected_cases"])
    mapped = sum(d["meanCases"] for d in run["dailyPredictions"])
    assert mapped + run["unassignedWindowCases"] == pytest.approx(rows[index]["observed_city_week_cases"])
    # January 1 through January 4 is the first corrected interval of 2022.
    assert all(d["sourceBlockDays"] == 4 for d in gp_runs.reconstruction_run(date(2022, 1, 1), 4)["dailyPredictions"])


def test_linked_archive_forecast_uses_reviewed_matrix_and_refuses_tampering(tmp_path, monkeypatch):
    from services.engine.repositories import weekly_handoff, first_admission
    monkeypatch.setattr(weekly_handoff, "FOLDER", tmp_path)
    req = {"prepare_hospital_simulation": True, "weeks_ahead": 1}
    forecast = client.post("/v1/predict", json=req).json()
    ident = forecast["hospitalSimulation"]["forecastRunId"]
    details = client.get("/v1/forecast-runs/" + ident)
    assert details.status_code == 200 and details.json()["weeklyPredictions"][0]["meanCases"] == forecast["city"][0]["expected_cases"]
    query = {"weeklyForecastId": ident}
    movie = client.get("/v1/qc-simulation", params=query).json()
    assert movie["forecastEvidence"]["observationSource"].startswith("Training archive")
    assert movie["firstAdmissionMatrixSha256"] == first_admission.MATRICES["markov_preference"][1]
    assert client.get("/v1/outbreak-scenarios/" + movie["scenarioId"]).status_code == 200
    rows = {row["barangay_code"]: row["expected_cases"] for row in forecast["barangays"]}
    matrix = ROOT / "data/processed/qc_first_admission_preference_v1/first_hospital_probabilities.csv"
    with matrix.open() as stream:
        header, *body = csv.reader(stream)
    for j, hospital in enumerate(header[2:], 2):
        expected = sum(float(line[j]) * rows[line[0]] for line in body) * movie["parameters"]["hospitalizationRate"]
        actual = sum(next(f["firstAdmissionsToday"] for f in d["facilities"] if f["facilityId"] == hospital) for d in movie["days"][1:])
        assert actual == pytest.approx(expected)
    patched = {**movie["controlValues"], "extraCasesPerWeek": 700}
    assert client.post("/v1/qc-simulation", json=patched).status_code == 422
    assert client.get("/v1/qc-simulation", params={"weeklyForecastId": "qc-weekly-" + "0"*64}).status_code == 404
    path, = (tmp_path / "scenarios/weekly").glob("*.json")
    path.write_bytes(b"{}")
    assert client.get("/v1/qc-simulation", params=query).status_code == 503


def test_missing_historical_forest_is_a_blocked_state(monkeypatch, tmp_path):
    from services.engine.repositories import gp_runs
    monkeypatch.setattr(gp_runs, "RF_PATH", tmp_path / "absent.npz")
    r = client.post("/v1/qc-simulation", json={"startDate": "2021-06-01", "endDate": "2021-06-02", "reconstructHistory": False})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "ARCHIVE_REPLAY_UNAVAILABLE"
    assert not client.get("/readiness").json()["archiveReplay"]["ready"]


def test_simulation_case_history_is_archive_only_and_reports_weekly_changes():
    historical = client.get("/v1/qc-simulation").json()
    assert historical["controlValues"]["startDate"] == "2012-01-01"
    window, = historical["historicalWindows"]
    assert (window["startDate"], window["endDate"]) == ("2012-01-01", "2023-01-01")
    for year in (2024, 2025):
        assert client.post("/v1/qc-simulation", json={"startDate": f"{year}-01-29", "endDate": f"{year}-02-05"}).status_code == 422
    planned = client.get("/v1/future-simulation").json()
    assert planned["forecastEvidence"]["issueBlock"] == {"YR": 2022, "WN": 52}
    archive = client.post("/v1/predict", json={"weeks_ahead": 4}).json()
    assert [w["cityCases"] for w in planned["forecastEvidence"]["weeklyCases"]] == [w["expected_cases"] for w in archive["city"]]
    days = planned["days"]
    assert days[7]["weeklyCasesChangePct"] is days[7]["bedForecast"]["weeklyDemandChangePct"] is None
    for t in (14, 21, 28):
        current = sum(d["expectedCases"] for d in days[t-6:t+1])
        previous = sum(d["expectedCases"] for d in days[t-13:t-6])
        assert days[t]["weeklyCasesChangePct"] == pytest.approx((current / previous - 1) * 100)
        pairs = [(days[t]["bedForecast"], days[t-7]["bedForecast"])]
        pairs.extend((now["bedForecast"], prev["bedForecast"]) for now, prev in zip(days[t]["facilities"], days[t-7]["facilities"], strict=True))
        for now, prev in pairs:
            assert now["weeklyDemandChangePct"] == pytest.approx((now["expectedBeds"] / prev["expectedBeds"] - 1) * 100)
    from services.engine.domain.bed_forecast import change_percent
    assert change_percent(1, 0) is None and change_percent(0, 0) is None
    assert change_percent(0, 5) == -100

def test_saved_external_observations_stay_out_of_the_archive_workspace(tmp_path, monkeypatch):
    from services.engine.repositories import weekly_handoff
    monkeypatch.setattr(weekly_handoff, "FOLDER", tmp_path)
    updates = [{"year": 2023, "week": 1, "city_cases": 55.0}]
    forecast = client.post("/v1/predict", json={"city_updates": updates, "prepare_hospital_simulation": True}).json()
    assert "unavailableReason" in forecast["hospitalSimulation"]
    old_id = weekly_handoff.save_handoff(forecast, updates, [])["forecastRunId"]
    assert client.get("/v1/forecast-runs/" + old_id).status_code == 200
    replay = client.get("/v1/qc-simulation", params={"weeklyForecastId": old_id})
    assert replay.status_code == 422
    assert replay.json()["detail"]["code"] == "ARCHIVE_CASE_HISTORY_REQUIRED"
