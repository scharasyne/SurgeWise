"""Reproducible simulation inputs from the released weekly barangay forecaster."""
from datetime import date, timedelta
import hashlib
import json
import re
from zipfile import BadZipFile

from production.surgewise import predictor
from ..domain.source_calendar import block_start, source_block, day_schedule
from ..upri_data import sha256
from .forecast_runs import artifact

OBSERVATIONS = "QUEZON_CITY-observations.json"
INTERVAL_NOTE = "The production release supplies point forecasts. Case and bed prediction intervals are unavailable."
SPATIAL_NOTE = "Daily barangay cases divide each production barangay forecast evenly across its source week."


class ProductionForecastUnavailable(RuntimeError):
    """The released forecaster or its approved observation inputs could not be loaded."""


def replay_windows():
    # Keep the eight dated issue periods used by the historical workspace.
    starts = (block_start(year, week) for year in (2024, 2025) for week in (5, 18, 31, 44))
    return [(start, start + timedelta(days=28)) for start in starts]


def production_run(start, duration, planning):
    try:
        return _production_run(start, duration, planning)
    except (OSError, ValueError, KeyError, IndexError, TypeError, BadZipFile, EOFError) as error:
        raise ProductionForecastUnavailable(
            "Could not generate production dengue forecasts. Check the production/surgewise release files and audited QC observations."
        ) from error


def _production_run(start, duration, planning):
    if not 1 <= duration <= 28 or not 2024 <= start.year <= 2035:
        raise ValueError("Invalid production scenario window")
    records = artifact(OBSERVATIONS)["records"]
    metadata, _, _, _ = predictor.assets()
    first_year = metadata["forecast_year"]
    end = start + timedelta(days=duration)
    if planning:
        # Scenario dates are hypothetical. The actual forecast follows the latest
        # observed week and must never be advanced by filling in missing weeks.
        cutoff = max(r["YR"] * 52 + r["WN"] - 1 for r in records)
    else:
        window = next((s for s, e in replay_windows() if s <= start and end <= e), None)
        if window is None:
            raise ValueError("Choose dates within a historical forecast period.")
        cutoff = source_block(window) - 1
    updates = [{"year": r["YR"], "week": r["WN"], "city_cases": r["DC_QC"]}
               for r in records if r["YR"] >= first_year and r["YR"] * 52 + r["WN"] - 1 <= cutoff]
    origin = predictor.calendar_week(cutoff)
    first = predictor.calendar_week(cutoff + 1)
    forecast_start = block_start(first["year"], first["week"]) if planning else start
    schedule = day_schedule(forecast_start, duration)
    forecast = predictor.predict(weeks_ahead=schedule[-1][1] - cutoff, city_updates=updates)
    if forecast["as_of"] != origin:
        raise ValueError("QC observations do not reach the requested forecast origin")
    weekly = [{**row, "YR": row["year"], "WN": row["week"], "meanCases": row["expected_cases"],
               "barangayCases": {}} for row in forecast["city"]]
    for row in forecast["barangays"]:
        weekly[row["horizon"] - 1]["barangayCases"][row["barangay_code"]] = row["expected_cases"]
    days = [{"sourceDate": day.isoformat(), "weekIndex": block - cutoff - 1, "sourceBlockDays": divisor,
             "meanCases": weekly[block - cutoff - 1]["meanCases"] / divisor}
            for day, block, divisor in schedule]
    mode = "planning" if planning else "replay"
    run = {"area": "QUEZON_CITY", "mode": "hypothetical_shock" if planning else "historical_replay",
           "model": forecast["model"], "trainedThrough": forecast["trained_through"],
           "featureHistoryThrough": forecast["feature_history_through"],
           "issueBlock": {"YR": origin["year"], "WN": origin["week"]},
           "observedCasesAtOrigin": updates[-1]["city_cases"],
           "observedSourceYearToDateCases": sum(r["city_cases"] for r in updates if r["year"] == origin["year"]),
           "environmentalInputs": [], "intervalCoverageTarget": None, "intervalCaveat": INTERVAL_NOTE,
           "spatialCaveat": SPATIAL_NOTE, "availabilityAssumption": "Reported QC source blocks are assumed available at their end.",
           "weeklyPredictions": weekly, "dailyPredictions": days, "scenarioStart": start.isoformat(),
           "sourceSha256": sha256(predictor.PACKAGE / "data/history.npz"),
           "modelSha256": sha256(predictor.PACKAGE / "models/forest.npz"),
           "cityUpdatesSha256": hashlib.sha256(json.dumps(updates, sort_keys=True).encode()).hexdigest()}
    digest = hashlib.sha256(json.dumps(run, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {**run, "id": f"qc-rf-{mode}-{start.isoformat()}-{duration}-{digest}", "runSha256": digest}


def load_production_run(ident):
    match = re.fullmatch(r"qc-rf-(planning|replay)-(\d{4}-\d{2}-\d{2})-(\d{1,2})-([0-9a-f]{64})", ident)
    if not match:
        raise ValueError("Invalid production forecast ID")
    run = production_run(date.fromisoformat(match[2]), int(match[3]), match[1] == "planning")
    if run["id"] != ident:
        raise ValueError("Production forecast inputs changed")
    return run


def evidence(run):
    first = run["dailyPredictions"][0]["weekIndex"]
    last = run["dailyPredictions"][-1]["weekIndex"]
    return {key: run[key] for key in ("id", "issueBlock", "model", "trainedThrough", "featureHistoryThrough",
            "environmentalInputs", "observedCasesAtOrigin", "observedSourceYearToDateCases",
            "intervalCoverageTarget", "intervalCaveat", "spatialCaveat", "availabilityAssumption")} | {
            "targetWeeks": [{"year": w["year"], "week": w["week"]} for w in run["weeklyPredictions"][first:last + 1]]}
