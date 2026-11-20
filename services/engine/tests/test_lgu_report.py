import csv
import io
import math

from fastapi.testclient import TestClient
import pytest

from services.engine.api.qc_simulation import default_workspace
from services.engine.domain.lgu_report import availability, daily_records, report_summary
from services.engine.main import app


@pytest.mark.parametrize(("value", "flag"), [(0, "Full"), (.00001, "Low availability"), (10, "Low availability"),
                                            (math.nextafter(10, math.inf), "No flag"), (11, "No flag")])
def test_classification_uses_unrounded_remaining_staffed_beds(value, flag):
    assert availability(value) == (value, flag)


@pytest.fixture(scope="module")
def simulation():
    return default_workspace()


@pytest.mark.parametrize(("source", "mode"), [
    ("qc-rf-archive-", "Future forecast"), ("qc-rf-planning-", "Future forecast"),
    ("qc-rf-replay-", "Historical replay"), ("qc-holdout-replay-", "Historical replay"),
    ("qc-gp-replay-", "Historical replay"), ("qc-weekly-", "Saved weekly forecast"),
])
def test_report_uses_saved_forecast_source_and_applied_weekly_factors(simulation, source, mode):
    movie = {**simulation, "seasonalModelSha256": None,
             "parameters": {**simulation["parameters"], "forecastRunId": source + "example"},
             "days": [{**day, "surgeFactor": 1.5 if day["dayIndex"] <= 7 else 2} for day in simulation["days"]]}
    summary = report_summary(movie, list(daily_records(movie)))
    assert summary["mode"] == mode
    if source == "qc-weekly-":
        assert dict(summary["settings"])["Case scenario"] == "1.5× to 2× baseline across the saved forecast weeks"


def test_register_and_watchlist_cover_full_run(simulation):
    rows = list(daily_records(simulation))
    assert len(rows) == 46 * simulation["durationDays"]
    assert {r["day"] for r in rows} == set(range(1, simulation["durationDays"] + 1))
    assert len({(r["day"], r["hospital_id"]) for r in rows}) == len(rows)
    # Construct explicit daily reporting cases without changing the engine result.
    for r in rows:
        r.update(remaining_staffed_dengue_beds=15, availability_flag="No flag")
    assert report_summary(simulation, rows)["watchlist"] == []
    a = [r for r in rows if r["hospital_id"] == rows[0]["hospital_id"]]
    for r, beds in zip(a[:3], [10, 0, 0]):
        value, flag = availability(beds)
        r.update(remaining_staffed_dengue_beds=value, availability_flag=flag)
    for r in a:
        r.update(expected_unplaced_today=0, expected_in_holding=0)
    summary = report_summary(simulation, rows)
    only, = summary["watchlist"]
    assert (only["status"], only["daysFlagged"], only["minimumBeds"]) == ("Full", 3, 0)
    assert only["firstFlag"] == a[0]["snapshot_qc"][:10]
    assert only["firstFull"] == a[1]["snapshot_qc"][:10]
    assert only["peakHolding"] == only["totalUnplaced"] == 0
    a[-1]["expected_unplaced_today"] = None
    assert report_summary(simulation, rows)["watchlist"][0]["totalUnplaced"] is None
    with pytest.raises(ValueError):
        list(daily_records({**simulation, "days": simulation["days"][:-1]}))


def test_downloads_and_preview_read_the_same_saved_scenario(simulation):
    client = TestClient(app)
    base = f'/v1/outbreak-scenarios/{simulation["scenarioId"]}/report.'
    preview = client.get(base + "json")
    assert preview.status_code == 200
    summary = preview.json()
    assert summary["scenarioId"] == simulation["scenarioId"]
    download = client.get(base + "csv")
    assert download.status_code == 200 and "attachment" in download.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(download.content.decode("utf-8-sig"))))
    assert summary["recordCount"] == len(rows) == 46 * simulation["durationDays"]
    visited = {r["hospital_id"] for r in rows if r["availability_flag"] != "No flag"}
    assert {h["id"] for h in summary["watchlist"]} == visited
    peak = max(simulation["days"][1:], key=lambda d: d["bedForecast"]["hospitalBedsShort"])
    assert summary["metrics"][3][1] == f'{peak["bedForecast"]["hospitalBedsShort"]:,}'
    pdf = client.get(base + "pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-") and pdf.content.rstrip().endswith(b"%%EOF")
    assert client.get("/v1/outbreak-scenarios/invalid/report.pdf").status_code == 404
