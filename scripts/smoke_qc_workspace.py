"""HTTP contracts for the production QC forecast UI and capacity sidebar."""
import argparse
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-url", default="http://127.0.0.1:3000")
    args = parser.parse_args()

    def request(path, body=None):
        req = Request(args.web_url + path, data=json.dumps(body).encode() if body is not None else None,
            headers={"content-type": "application/json"})
        try:
            with urlopen(req, timeout=60) as response:
                raw = response.read()
                return response.status, json.loads(raw) if "json" in response.headers.get("content-type", "") else raw.decode()
        except HTTPError as error:
            return error.code, json.load(error)

    for page in ["/", "/dashboard", "/outbreak-response", "/simulate"]:
        status, html = request(page)
        assert status == 200, (page, status)
        # The legacy route can stream a Next.js redirect after sending HTTP 200.
        if page == "/simulate" and "Simulation timeline and playback" not in html:
            assert "__next-page-redirect" in html and "/outbreak-response" in html, "Missing simulation redirect"
        elif page in {"/outbreak-response", "/simulate"}:
            assert "SurgeWise" in html and "Base cases for selected date" in html and "QC expected bed demand" in html, page
            assert "Simulation not started" in html
            assert "Historical replay" in html and "Future forecast" in html
            assert "Simulation timeline and playback" in html and "Nearest hospital" in html
            assert "Expansion origin" not in html
    status, country = request("/data/philippines-context.geojson")
    assert status == 200 and len(country["features"]) == 17
    status, data = request("/api/research/qc-simulation")
    assert status == 200, data
    assert data["scope"] == "QUEZON_CITY" and data["forecastEvidence"]["caseSourceKind"] == "gp_reconstruction"
    assert data["progressionMethod"] == "gp_weekly_barangay_reconstruction"
    assert len(data["context"]["hotspotRanking"]["candidateIds"]) == 10
    assert {b["id"] for b in data["context"]["barangays"] if b["isHighBurdenCandidate"]} == set(data["days"][-1]["hotspotIds"])
    assert len(data["periodSummary"]["barangays"]) == 142 and len(data["days"][-1]["facilities"]) == 46
    assert any(len(b["hospitalsWithinBarangay"]) > 1 for b in data["context"]["barangays"])
    assert all(f["nearestHotspot"] is None for f in data["days"][0]["facilities"])
    assert all(f["nearestHotspot"]["barangayId"] in data["days"][-1]["hotspotIds"] for f in data["days"][-1]["facilities"])
    assert data["forecastEvidence"]["observedSourceYearToDateCases"] > 0
    assert [(w["startDate"], w["endDate"]) for w in data["historicalWindows"]] == [("2012-01-01", "2023-01-01")]
    status, partial = request("/api/research/qc-simulation", {**data["controlValues"],
        "startDate": "2012-01-06", "endDate": "2012-01-15"})
    assert status == 200, partial
    assert abs(partial["periodSummary"]["expectedCases"] - sum(d["expectedCases"] for d in data["days"][6:15])) < 1e-7
    status, missing = request("/api/research/qc-simulation", {**data["controlValues"],
        "startDate": "2025-03-01", "endDate": "2025-03-08"})
    assert status == 422 and missing["detail"]["code"] == "HISTORICAL_WINDOW_UNAVAILABLE", missing
    for frame in data["days"]:
        assert "caseRange" not in frame
        assert abs(frame["balanceError"]) < 1e-7
        assert frame["bedForecast"]["hospitalBedsShort"] == sum(f["bedForecast"]["additionalStaffedBedsNeeded"] for f in frame["facilities"])
    for days, end in [(7, "2012-01-08"), (14, "2012-01-15"), (28, "2012-01-29")]:
        controls = {**data["controlValues"], "endDate": end}
        status, window = request("/api/research/qc-simulation", controls)
        assert status == 200 and len(window["days"]) == days + 1, window
        assert window["periodSummary"]["expectedCases"] == window["days"][-1]["cumulativeCases"]
    controls = {**data["controlValues"], "endDate": "2012-01-08", "compareAllocation": True}
    status, comparison = request("/api/research/qc-simulation", controls)
    assert status == 200 and {r["arrivalSplitPolicy"] for r in comparison["firstAdmissionComparison"]} == {"markov_preference", "markov_proximity"}
    status, ranked = request("/api/research/qc-simulation", {**controls, "allocationPolicy": "next_probability"})
    assert status == 200 and ranked["assignmentEncoding"] == "hospital_totals_with_ranked_origin_placements"
    status, _ = request("/api/research/qc-simulation", {**controls, "area": "NCR"})
    assert status == 422
    status, future = request("/api/research/future-simulation")
    assert status == 200, future
    assert future["workspaceTab"] == "future" and future["futureForecast"]["trainingCutoffBlock"]["YR"] == 2022
    assert future["futureForecast"]["selectedModel"] == "RF_shallow"
    assert future["futureForecast"]["parameterAudit"]["horizonDays"] == 28
    assert future["forecastEvidence"]["issueBlock"] == {"YR": 2022, "WN": 52}
    assert future["bedProjection"]["arrivalSplitPolicy"] == "markov_preference"
    assert len(future["bedProjection"]["placePeaks"]) == 142
    assert all(len(p["hospitals"]) == 46 and all(h["share"] > 0 for h in p["hospitals"]) and abs(sum(h["share"] for h in p["hospitals"]) - 1) < 1e-9 for p in future["bedProjection"]["placePeaks"])
    assert future["progressionMethod"] == "production_weekly_barangay_forecast"
    assert all(f["nearestHotspot"]["barangayId"] in future["days"][-1]["hotspotIds"] for f in future["days"][-1]["facilities"])
    assert future["bedProjection"]["staffedBedsRequired"] >= 0
    for day in future["days"]:
        for facility in day["facilities"]:
            beds = facility["bedForecast"]
            capacity = beds["assumedSupportedDengueCapacity"]
            if capacity > 0:
                assert abs(beds["demandUtilizationPct"] - beds["expectedBeds"] / capacity * 100) < 1e-7
            else:
                assert beds["demandUtilizationPct"] is None
    baseline_january = None
    for days in [7, 14, 21, 28]:
        status, window = request("/api/research/future-simulation", {"startDate": "2027-01-01", "horizonDays": days, "surgeEnabled": False})
        assert status == 200 and len(window["days"]) == days + 1, window
        assert window["futureForecast"]["sourcePeriodStart"] == "2023-01-01"
        assert window["days"][-1]["bedForecast"]["staffedBedsRequired"] >= 0
        assert all(abs(d["balanceError"]) < 1e-7 for d in window["days"])
        if days == 28:
            baseline_january = window["periodSummary"]["expectedCases"]
    status, today = request("/api/research/future-simulation", {"surgeEnabled": False})
    assert status == 200, today
    assert baseline_january == today["periodSummary"]["expectedCases"]
    assert future["periodSummary"]["expectedCases"] > today["periodSummary"]["expectedCases"]
    assert future["bedProjection"]["peakAdditionalStaffedBedsDueToSurge"] > 0
    assert today["bedProjection"]["peakAdditionalStaffedBedsDueToSurge"] == 0
    for patch in [{"horizonDays": 29}, {"area": "NCR"}, {"facilities": []}]:
        status, _ = request("/api/research/future-simulation", patch)
        assert status == 422
    print("PASS: pages/two tabs, Philippines context, historical QC forecasts/46 hospitals, 7/14/28-day replay, allocation comparison, future 7/14/21/28-day windows, production forecast origin, surge, bed demand, conservation and invalid-input/QC-scope rejection.")


if __name__ == "__main__":
    main()
