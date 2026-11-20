from datetime import date, timedelta
import csv
import json

from fastapi.testclient import TestClient
import pytest

from services.engine.api.qc_simulation import QCInput, workspace
from services.engine.domain.outbreak import build_movie
from services.engine.main import app
from services.engine.repositories import first_admission
from services.engine.upri_data import ROOT, sha256


def test_local_shortage_survives_spare_beds_elsewhere():
    # Two synthetic origins have the same choices. Of eleven arrivals, ten
    # choose A. A can support six, even though B has nineteen spare slots.
    config = {"startDate": date(2027, 1, 1), "endDate": date(2027, 1, 5),
              "autoHotspots": True, "seedBarangayId": "X", "growthDays": 1, "shockProfile": "step",
              "extraCasesPerWeek": 0, "hospitalizationRate": 1, "lengthOfStayDays": 1, "baselineOccupancy": 0,
              "admissionDelayDays": 1, "surgeActivationDay": 4, "allocationPolicy": "first_hospital",
              "arrivalSplitPolicy": "markov_proximity", "facilities": [
                  {"facilityId": "A", "normalCapacity": 6, "surgeCapacity": 4, "holdingCapacity": 0},
                  {"facilityId": "B", "normalCapacity": 20, "surgeCapacity": 0, "holdingCapacity": 0}]}
    context = {"barangays": [{"id": "X", "weight": .75, "coordinates": [121, 14]},
                             {"id": "Y", "weight": .25, "coordinates": [121.01, 14]}],
               "hospitals": [{"id": h, "coordinates": [121, 14]} for h in ("A", "B")]}
    run = {"weeklyPredictions": [{"meanCases": 77} for _ in range(4)],
           "dailyPredictions": [{"meanCases": 11, "lowerCases": 8, "upperCases": 14} for _ in range(28)]}
    matrix = {b: [("A", 10/11), ("B", 1/11)] for b in ("X", "Y")}
    movie = build_movie(run, context, config, matrix)
    assert [d["bedForecast"]["hospitalBedsShort"] for d in movie["days"]] == [0, 0, 4, 4, 0]
    frame = movie["days"][2]
    a, b = frame["facilities"]
    assert a["firstAdmissionsToday"] == 10 and a["supportedCensus"] == 6
    assert a["unplacedToday"] == 4 and a["bedForecast"]["additionalStaffedBedsNeeded"] == 4
    assert b["supportedCensus"] == 1 and b["remainingSupportedCapacity"] == 19
    assert frame["bedForecast"]["additionalStaffedBedsNeeded"] == 4
    assert frame["bedForecast"]["pooledAdditionalStaffedBedsNeeded"] == 0
    assert [r["expectedBedsShort"] for r in frame["barangays"]] == [3, 1]
    assert all(abs(d["balanceError"]) < 1e-8 for d in movie["days"])
    # Holding uses space at the same facility and never covers a staffed-bed shortage.
    config["facilities"][0]["holdingCapacity"] = 2
    held = build_movie(run, context, config, matrix)["days"][2]
    assert held["holdingCensus"] == 2 and held["unresolvedToday"] == 2
    assert held["bedForecast"]["hospitalBedsShort"] == 4


@pytest.fixture(scope="module")
def matching_reference_exports(tmp_path_factory):
    """Compare identical forecast artifacts, including after a local annual model rebuild."""
    from scripts import build_first_admission_matrix as proximity
    from scripts import build_first_admission_preference as preference

    published = ROOT / "data/processed"
    baseline_name, _ = first_admission.MATRICES["markov_proximity"]
    favorite_name, _ = first_admission.MATRICES["markov_preference"]
    manifest = json.loads((published / baseline_name / "manifest.json").read_text())
    annual = "data/processed/upri_noah/qc-barangay-xgboost.json"
    if manifest["inputHashes"][annual] == sha256(ROOT / annual):
        return published

    # The published worked example records the annual forecast hash used to build it.
    # Regenerate its offline reference for this machine's validated local model.
    root = tmp_path_factory.mktemp("historical_reference")
    baseline, favorites = root / baseline_name, root / favorite_name
    baseline.mkdir()
    favorites.mkdir()
    current = proximity.build(baseline, manifest["runId"], 3, .15, 4)
    (baseline / "manifest.json").write_text(json.dumps(current))
    preference.build(favorites, baseline, preference.PREFERENCES, 1.5)
    return root


@pytest.mark.parametrize("policy,folder", [(k, v[0]) for k, v in first_admission.MATRICES.items()])
def test_live_historical_run_matches_every_exported_hospital_day(policy, folder, matching_reference_exports):
    movie = workspace(QCInput(arrivalSplitPolicy=policy))
    assert movie["parameters"]["allocationPolicy"] == "first_hospital"
    assert movie["firstAdmissionMatrixSha256"] == first_admission.MATRICES[policy][1]
    assert len([b for b in movie["context"]["barangays"] if b["mappedFavoriteHospitalId"]]) == 14
    with (matching_reference_exports / folder / "daily_hospital_beds.csv").open() as stream:
        reference = list(csv.DictReader(stream))
    assert len(reference) == 28 * 46
    # The export labels interval starts. The movie labels the end snapshot.
    observations = {(d["intervalStart"][:10], f["facilityId"]): f for d in movie["days"][1:] for f in d["facilities"]}
    for row in reference:
        f = observations[(row["scenarioDate"], row["hospitalId"])]
        assert f["firstAdmissionsToday"] == pytest.approx(float(row["expectedFirstAdmissions"]), abs=1e-12)
        assert f["bedForecast"]["expectedBeds"] == pytest.approx(float(row["expectedOccupiedDengueBedsIfAdmitted"]), abs=1e-12)
    assert all(len(b["hospitals"]) == 46 for b in movie["bedProjection"]["placePeaks"])


def test_future_first_hospital_stress_and_paired_comparison():
    client = TestClient(app)
    from services.engine.api.future_simulation import today_qc
    start = today_qc() + timedelta(days=1)
    resp = client.post("/v1/future-simulation", json={"startDate": start.isoformat(), "horizonDays": 3,
        "compareAllocation": True, "baselineOccupancy": 1, "surgeCapacity": 0, "holdingCapacity": 0})
    assert resp.status_code == 200
    result = resp.json()
    comparisons = {r["arrivalSplitPolicy"]: r for r in result["firstAdmissionComparison"]}
    assert set(comparisons) == {"markov_proximity", "markov_preference"}
    assert comparisons["markov_proximity"]["peakExpectedBeds"] == pytest.approx(comparisons["markov_preference"]["peakExpectedBeds"])
    assert result["controlValues"]["arrivalSplitPolicy"] == "markov_preference"
    for d in result["days"][1:]:
        assert d["bedForecast"]["hospitalBedsShort"] == sum(f["bedForecast"]["additionalStaffedBedsNeeded"] for f in d["facilities"]) > 0
        assert sum(b["expectedBedsShort"] for b in d["barangays"]) == pytest.approx(d["bedForecast"]["expectedBeds"])
        assert d["supportedCensus"] == d["holdingCensus"] == 0
        assert d["arrivals"] == pytest.approx(d["unresolvedToday"])


def test_corrupt_matrix_blocks_new_and_saved_results(monkeypatch):
    client = TestClient(app)
    movie = workspace(QCInput(endDate=date(2025, 2, 1)))
    monkeypatch.setitem(first_admission.MATRICES, "markov_preference", ("qc_first_admission_preference_v1", "0"*64))
    for url in ("/v1/qc-simulation", "/v1/outbreak-scenarios/" + movie["scenarioId"]):
        response = client.get(url)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "FIRST_ADMISSION_MATRIX_UNAVAILABLE"


def test_incompatible_routing_is_rejected_and_legacy_inputs_keep_their_policy():
    client = TestClient(app)
    assert client.post("/v1/qc-simulation", json={"arrivalSplitPolicy": "markov_proximity", "allocationPolicy": "optimized"}).status_code == 422
    assert QCInput(allocationPolicy="optimized").arrivalSplitPolicy == "nearest_three_equal"
    assert QCInput(arrivalSplitPolicy="nearest").allocationPolicy == "nearest"
