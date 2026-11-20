"""Reproducible simulation inputs from the released weekly barangay forecaster."""
from datetime import date, timedelta
import hashlib
import json
import math
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


def simulation_predictions(forecast, schedule, cutoff):
    weekly = [{**row, "YR": row["year"], "WN": row["week"], "meanCases": row["expected_cases"],
               "barangayCases": {}} for row in forecast["city"]]
    for row in forecast["barangays"]:
        local = weekly[row["horizon"] - 1]
        if ((local["year"], local["week"]) != (row["year"], row["week"]) or
                row["barangay_code"] in local["barangayCases"] or
                not math.isfinite(row["expected_cases"]) or row["expected_cases"] < 0):
            raise ValueError("Invalid weekly barangay forecast")
        weekly[row["horizon"] - 1]["barangayCases"][row["barangay_code"]] = row["expected_cases"]
    for week in weekly:
        counts = week["barangayCases"]
        if len(counts) != 142 or not math.isclose(math.fsum(counts.values()), week["meanCases"], abs_tol=1e-9):
            raise ValueError("Weekly barangay forecasts do not reconcile to the QC forecast")
    days = [{"sourceDate": day.isoformat(), "weekIndex": block - cutoff - 1, "sourceBlockDays": divisor,
             "meanCases": weekly[block - cutoff - 1]["meanCases"] / divisor}
            for day, block, divisor in schedule]
    return weekly, days


def production_run(start, duration, planning):
    try:
        return _production_run(start, duration, planning, archive=planning)
    except (OSError, ValueError, KeyError, IndexError, TypeError, BadZipFile, EOFError) as error:
        raise ProductionForecastUnavailable(
            "Could not generate production dengue forecasts. Check the production/surgewise release files and audited QC observations."
        ) from error


def _production_run(start, duration, planning, *, archive=False):
    if not 1 <= duration <= 28 or not 2024 <= start.year <= 2035:
        raise ValueError("Invalid production scenario window")
    metadata, _, snapshot, _ = predictor.assets()
    first_year = metadata["forecast_year"]
    if archive:
        cutoff = first_year * 52 - 1
        updates = []
        last_count = float(snapshot["city"][-1])
        year_total = float(snapshot["city"][-52:].sum())
    else:
        # Earlier saved runs keep their original UPRI source and content IDs.
        records = artifact(OBSERVATIONS)["records"]
        if planning:
            cutoff = max(r["YR"] * 52 + r["WN"] - 1 for r in records)
        else:
            end = start + timedelta(days=duration)
            window = next((s for s, e in replay_windows() if s <= start and end <= e), None)
            if window is None:
                raise ValueError("Choose dates within a historical forecast period.")
            cutoff = source_block(window) - 1
        updates = [{"year": r["YR"], "week": r["WN"], "city_cases": r["DC_QC"]}
                   for r in records if r["YR"] >= first_year and r["YR"] * 52 + r["WN"] - 1 <= cutoff]
        last_count = updates[-1]["city_cases"]
        year_total = sum(r["city_cases"] for r in updates if r["year"] == predictor.calendar_week(cutoff)["year"])
    origin = predictor.calendar_week(cutoff)
    first = predictor.calendar_week(cutoff + 1)
    forecast_start = block_start(first["year"], first["week"]) if planning else start
    schedule = day_schedule(forecast_start, duration)
    forecast = predictor.predict(weeks_ahead=schedule[-1][1] - cutoff, city_updates=updates)
    if forecast["as_of"] != origin:
        raise ValueError("QC observations do not reach the requested forecast origin")
    weekly, days = simulation_predictions(forecast, schedule, cutoff)
    mode = "archive" if archive else "planning" if planning else "replay"
    run = {"area": "QUEZON_CITY", "mode": "hypothetical_shock" if planning else "historical_replay",
           "model": forecast["model"], "trainedThrough": forecast["trained_through"],
           "featureHistoryThrough": forecast["feature_history_through"],
           "issueBlock": {"YR": origin["year"], "WN": origin["week"]},
           "observedCasesAtOrigin": last_count,
           "observedSourceYearToDateCases": year_total,
           "environmentalInputs": [], "intervalCoverageTarget": None, "intervalCaveat": INTERVAL_NOTE,
           "spatialCaveat": SPATIAL_NOTE, "availabilityAssumption": "Reported QC source blocks are assumed available at their end.",
           "weeklyPredictions": weekly, "dailyPredictions": days, "scenarioStart": start.isoformat(),
           "sourceSha256": sha256(predictor.PACKAGE / "data/history.npz"),
           "modelSha256": sha256(predictor.PACKAGE / "models/forest.npz"),
           "cityUpdatesSha256": hashlib.sha256(json.dumps(updates, sort_keys=True).encode()).hexdigest()}
    if archive:
        run["observationSource"] = "2012–2022 training archive · reported QC weekly city totals"
        run["annualContextYear"] = origin["year"]
        run["availabilityAssumption"] = "Case forecasts follow the final archive week. Hospital planning dates are hypothetical."
    digest = hashlib.sha256(json.dumps(run, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {**run, "id": f"qc-rf-{mode}-{start.isoformat()}-{duration}-{digest}", "runSha256": digest}


def load_production_run(ident):
    match = re.fullmatch(r"qc-rf-(archive|planning|replay)-(\d{4}-\d{2}-\d{2})-(\d{1,2})-([0-9a-f]{64})", ident)
    if not match:
        raise ValueError("Invalid production forecast ID")
    run = _production_run(date.fromisoformat(match[2]), int(match[3]), match[1] != "replay", archive=match[1] == "archive")
    if run["id"] != ident:
        raise ValueError("Production forecast inputs changed")
    return run


def evidence(run):
    first = run["dailyPredictions"][0]["weekIndex"]
    last = run["dailyPredictions"][-1]["weekIndex"]
    # The weekly input may extend beyond the hospital window (up to six source weeks).
    # Replay origins can also precede a selected partial window.
    source_weeks = run["weeklyPredictions"][first:] if run["id"].startswith("qc-weekly-") else run["weeklyPredictions"][first:last + 1]
    weekly_cases = []
    for week in source_weeks:
        row = {"year": week["year"], "week": week["week"], "cityCases": week["meanCases"],
               "barangayCases": week["barangayCases"]}
        if week.get("scenario_multiplier", 1) != 1:
            row["scenarioCityCases"] = week["scenario_expected_cases"]
            row["scenarioBarangayCases"] = {code: value * week["scenario_multiplier"] for code, value in week["barangayCases"].items()}
        weekly_cases.append(row)
    return {key: run[key] for key in ("id", "issueBlock", "model", "trainedThrough", "featureHistoryThrough",
            "environmentalInputs", "observedCasesAtOrigin", "observedSourceYearToDateCases",
            "intervalCoverageTarget", "intervalCaveat", "spatialCaveat", "availabilityAssumption")} | {
            **{k: run[k] for k in ("observedReferenceBlock", "unassignedWindowCases", "observationSource") if k in run},
            "caseSourceKind": run.get("caseSourceKind", "forecast"),
            "weeklyCases": weekly_cases,
            "targetWeeks": [{"year": w["year"], "week": w["week"]} for w in run["weeklyPredictions"][first:last + 1]]}
