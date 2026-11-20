from datetime import date, timedelta
import csv
import math

from fastapi.testclient import TestClient
import pytest

from services.engine.api.qc_simulation import QCInput, workspace
from services.engine.domain.optimizer import overflow_plan
from services.engine.domain.outbreak import build_movie, distance_km
from services.engine.main import app
from services.engine.repositories import first_admission
from services.engine.upri_data import ROOT


@pytest.fixture
def two_site_inputs():
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
               "hospitals": [{"id": "A", "coordinates": [121, 14]}, {"id": "B", "coordinates": [121.2, 14]}]}
    run = {"weeklyPredictions": [{"meanCases": 77} for _ in range(4)],
           "dailyPredictions": [{"meanCases": 11, "lowerCases": 8, "upperCases": 14} for _ in range(28)]}
    matrix = {b: [("A", 10/11), ("B", 1/11)] for b in ("X", "Y")}
    return run, context, config, matrix


def test_local_shortage_survives_spare_beds_elsewhere(two_site_inputs):
    run, context, config, matrix = two_site_inputs
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


@pytest.mark.parametrize("policy,folder", [(k, v[0]) for k, v in first_admission.MATRICES.items()])
def test_live_historical_run_matches_every_exported_hospital_day(policy, folder):
    movie = workspace(QCInput(arrivalSplitPolicy=policy))
    assert movie["parameters"]["allocationPolicy"] == "first_hospital"
    assert movie["firstAdmissionMatrixSha256"] == first_admission.MATRICES[policy][1]
    assert len([b for b in movie["context"]["barangays"] if b["mappedFavoriteHospitalId"]]) == 14
    with (ROOT / "data/processed" / folder / "daily_hospital_beds.csv").open() as stream:
        reference = list(csv.DictReader(stream))
    assert len(reference) == 28 * 46
    # The export labels interval starts. The movie labels the end snapshot.
    observations = {(d["intervalStart"][:10], f["facilityId"]): f for d in movie["days"][1:] for f in d["facilities"]}
    for row in reference:
        f = observations[(row["scenarioDate"], row["hospitalId"])]
        assert f["firstAdmissionsToday"] == pytest.approx(float(row["expectedFirstAdmissions"]), abs=1e-12)
        assert f["bedForecast"]["expectedBeds"] == pytest.approx(float(row["expectedOccupiedDengueBedsIfAdmitted"]), abs=1e-12)
    places = movie["bedProjection"]["placePeaks"]
    origins = {b["id"]: b for b in movie["context"]["barangays"]}
    sites = {h["id"]: h["coordinates"] for h in movie["context"]["hospitals"]}
    with (ROOT / "data/processed/qc_first_admission_v1/first_hospital_probabilities.csv").open() as stream:
        base = {row["barangayId"]: row for row in csv.DictReader(stream)}
    assert len(places) == 142
    for place in places:
        origin = origins[place["barangayId"]]
        choices = place["hospitals"]
        assert {row["facilityId"] for row in choices} == sites.keys() and len(choices) == 46
        weights = []
        for row in choices:
            h = row["facilityId"]
            info = row["breakdown"]
            assert info["proximityShare"] == float(base[origin["id"]][h])
            assert info["distanceKm"] == pytest.approx(distance_km(origin["coordinates"], sites[h]))
            boost = policy == "markov_preference" and h == origin["mappedFavoriteHospitalId"]
            assert info["preferenceMultiplier"] == (1.5 if boost else 1)
            weights.append(info["proximityShare"] * info["preferenceMultiplier"])
        total = math.fsum(weights)
        assert [r["share"] for r in choices] == pytest.approx([w / total for w in weights], abs=1e-14)


def test_future_first_hospital_stress_and_paired_comparison():
    client = TestClient(app)
    from services.engine.api.future_simulation import today_qc
    start = today_qc() + timedelta(days=1)
    resp = client.post("/v1/future-simulation", json={"startDate": start.isoformat(), "horizonDays": 3,
        "compareAllocation": True, "baselineOccupancy": 1, "surgeCapacity": 0, "holdingCapacity": 0})
    assert resp.status_code == 200
    result = resp.json()
    assert result["bedProjection"]["placePeaks"][0]["hospitals"][-1]["breakdown"]["proximityShare"] > 0
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


@pytest.mark.parametrize("policy", ["optimized", "nearest"])
def test_only_first_choice_overflow_is_redirected(two_site_inputs, policy):
    run, context, config, matrix = two_site_inputs
    config["allocationPolicy"] = policy
    movie = build_movie(run, context, config, matrix)
    frame = movie["days"][2]
    a, b = frame["facilities"]
    assert [a["firstAdmissionsToday"], b["firstAdmissionsToday"]] == [10, 1]
    assert [a["supportedCensus"], b["supportedCensus"]] == [6, 5]
    routes = {(r["firstFacilityId"], r["facilityId"]): r["supportedPlacements"] for r in frame["firstHospitalRoutes"]}
    assert routes == {("A", "A"): 6, ("A", "B"): 4, ("B", "B"): 1}
    assert frame["unresolvedToday"] == frame["bedForecast"]["additionalStaffedBedsNeeded"] == 0
    assert frame["bedForecast"]["hospitalBedsShort"] == 4  # before diversion
    assert all(abs(d["balanceError"]) < 1e-8 for d in movie["days"])
    assert all(r["firstFacilityId"] == r["facilityId"] for r in movie["days"][4]["firstHospitalRoutes"])
    config["facilities"][1].update(normalCapacity=1, holdingCapacity=2)
    config["facilities"][0]["holdingCapacity"] = 1
    full = build_movie(run, context, config, matrix)["days"][2]
    assert [f["holdingPlacementsToday"] for f in full["facilities"]] == [1, 2]
    assert [f["unplacedToday"] for f in full["facilities"]] == [1, 0]
    assert full["supportedCensus"] + full["holdingCensus"] + full["unresolvedToday"] == full["arrivals"]


def test_optimized_overflow_accounts_for_competing_destinations():
    # Four sites on a line. A and B overflow by one each, C and D each have one spare.
    positions = [0, 3, 2, -3]
    costs = [[abs(a - b) for b in positions] for a in positions]
    demand, capacity = [2, 2, 1, 1], [1, 1, 2, 2]
    optimized = overflow_plan(demand, capacity, costs, range(4), True)
    nearest = overflow_plan(demand, capacity, costs, range(4), False)
    assert [optimized[i][i] for i in range(4)] == [1, 1, 1, 1]
    assert optimized[0][3] == optimized[1][2] == 1  # 3 + 1 extra km
    assert nearest[0][2] == nearest[1][3] == 1  # 2 + 6 extra km


@pytest.mark.parametrize("endpoint", ["qc-simulation", "future-simulation"])
@pytest.mark.parametrize("policy", ["markov_proximity", "markov_preference"])
def test_optimized_workspace_preserves_choice(endpoint, policy):
    from services.engine.api.future_simulation import today_qc

    dates = {"endDate": "2025-02-01"} if endpoint == "qc-simulation" else {
        "startDate": (today_qc() + timedelta(days=1)).isoformat(), "horizonDays": 3}
    response = TestClient(app).post("/v1/" + endpoint, json={**dates, "allocationPolicy": "optimized",
        "arrivalSplitPolicy": policy, "compareAllocation": True})
    assert response.status_code == 200, response.text[:500]
    result = response.json()
    assert result["controlValues"]["arrivalSplitPolicy"] == result["bedProjection"]["arrivalSplitPolicy"] == policy
    assert result["firstAdmissionMatrixSha256"] == first_admission.MATRICES[policy][1]
    assert result["assignmentEncoding"] == "first_hospital_routes_with_origin_shares"
    places = result["bedProjection"]["placePeaks"]
    assert len(places) == 142 and all(len(p["hospitals"]) == 46 for p in places)
    placed_km = sum(d["expectedPlacementPatientKm"] for d in result["days"])
    assert placed_km > 0 and result["allocationComparison"]["optimized"]["expectedPatientKm"] == pytest.approx(placed_km)
    assert result["allocationComparison"]["nearest"]["expectedPatientKm"] > 0


def test_incompatible_routing_is_rejected_and_explicit_legacy_inputs_keep_their_policy():
    client = TestClient(app)
    assert client.post("/v1/qc-simulation", json={"arrivalSplitPolicy": "nearest_three_equal", "allocationPolicy": "first_hospital"}).status_code == 422
    assert QCInput(allocationPolicy="optimized").arrivalSplitPolicy == "markov_preference"
    assert QCInput(allocationPolicy="optimized", arrivalSplitPolicy="nearest_three_equal").arrivalSplitPolicy == "nearest_three_equal"
    assert QCInput(arrivalSplitPolicy="nearest").allocationPolicy == "nearest"
