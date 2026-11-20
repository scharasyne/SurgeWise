"""QC hospital-demand inputs from archive reconstructions and pre-origin RF forecasts."""
from bisect import bisect_right
from datetime import date, datetime, timedelta
from functools import lru_cache
import hashlib
import io
import json
import math
import re

import numpy as np

from production.surgewise import history
from ..upri_data import ROOT, sha256
from .forecast_runs import ForecastRunNotFound

FIRST_DAY = date(2012, 1, 1)
END_EXCLUSIVE = date(2023, 1, 1)
GP_SHA256 = "d3b1d8934d046b97fa474f531b2d0d0085b0f986dcd3385e6c5b9dc4f0fd85f4"
RF_START = date(2021, 1, 1)
RF_PATH = ROOT / "data/processed/qc-archive-rf-replay.npz"
RF_SHA256 = "7306bb9047b8a65b1bbadb408c9f09936900779d7bb1df6526d29b2bc88547fa"
RF_NOTE = ("The evaluation forest was fitted through 2020. Each replay uses one forecast origin before "
           "the first selected source week. Completed-year features assume availability at year end.")
CALENDAR_NOTE = ("Daily demand is spread evenly from each corrected source date until the next one. "
                 "The final interval ends on January 1, 2023.")
GP_NOTE = ("Retrospective GP estimates use reported annual barangay totals and observed QC weekly counts. "
           "Only cases assigned to mapped barangays enter the hospital simulation.")
GP_RANGE_NOTE = "The GP release describes historical reconstruction uncertainty. Hospital prediction intervals are unavailable."


def reconstruction_weeks(first_block, count):
    if sha256(history.DATA) != GP_SHA256:
        raise ValueError("GP reconstruction file failed verification")
    weeks = []
    names = {}
    for block in range(first_block, first_block + count):
        year, offset = divmod(block, 52)
        source = history.gp_history(year=year, week=offset + 1)
        city, = source["city"]
        if not names:
            names = {row["barangay_code"]: row["barangay"] for row in source["barangays"]}
        cases = {r["barangay_code"]: r["gp_expected_cases"] for r in source["barangays"]}
        residual = city["unassigned_expected_cases"]
        mapped = math.fsum(cases.values())
        if (len(cases) != 142 or len(source["barangays"]) != 142 or cases.keys() != names.keys()
                or any(not math.isfinite(v) or v < 0 for v in [*cases.values(), residual])
                or not math.isclose(mapped + residual, city["observed_city_week_cases"], abs_tol=1e-7)):
            raise ValueError("GP estimates do not reconcile to the reported QC total")
        weeks.append({"year": year, "week": offset + 1, "YR": year, "WN": offset + 1,
                      "meanCases": mapped, "barangayCases": cases, "observedCityCases": city["observed_city_week_cases"],
                      "unassignedCases": residual})
    return weeks, names


def reconstruction_prediction(first, count, multiplier):
    weeks, names = reconstruction_weeks(first, count)
    city, local = [], []
    for horizon, week in enumerate(weeks, 1):
        period = {"year": week["year"], "week": week["week"], "horizon": horizon, "scenario_multiplier": multiplier}
        city.append({**period, "expected_cases": week["meanCases"], "scenario_expected_cases": week["meanCases"] * multiplier,
                     "observed_city_cases": week["observedCityCases"], "unassigned_cases": week["unassignedCases"]})
        for code, cases in week["barangayCases"].items():
            local.append({**period, "barangay_code": code, "barangay": names[code],
                          "expected_cases": cases, "scenario_expected_cases": cases * multiplier})
    return {"model": "GP reconstruction", "timing_basis": "gp_reconstruction", "weeks_ahead": count,
            "city": city, "barangays": local, "as_of": None, "trained_through": None, "feature_history_through": None}


@lru_cache(maxsize=1)
def archive_calendar():
    rows = history.city_history()
    starts = [datetime.strptime(row["source_date_corrected"], "%m/%d/%Y").date() for row in rows]
    if (len(rows) != 11 * 52 or starts[0] != FIRST_DAY
            or any((row["year"], row["week"]) != (2012 + i // 52, 1 + i % 52)
                   for i, row in enumerate(rows))):
        raise ValueError("Incomplete archive calendar")
    starts.append(END_EXCLUSIVE)
    if any(a >= b for a, b in zip(starts, starts[1:])):
        raise ValueError("Invalid archive source dates")
    return starts, rows


def archive_schedule(start, duration):
    if not (1 <= duration <= 28 and FIRST_DAY <= start and start + timedelta(days=duration) <= END_EXCLUSIVE):
        raise ValueError("Choose dates inside the 2012–2022 reconstruction")
    starts, cities = archive_calendar()
    # Treat each corrected source date as the start of its reporting interval.
    schedule = []
    for i in range(duration):
        day = start + timedelta(days=i)
        index = bisect_right(starts, day) - 1
        schedule.append((day, 2012 * 52 + index, (starts[index + 1] - starts[index]).days))
    return schedule, cities


def reconstruction_run(start, duration):
    schedule, cities = archive_schedule(start, duration)
    first, last = schedule[0][1], schedule[-1][1]
    weeks, _ = reconstruction_weeks(first, last - first + 1)
    # The GP release and the UPRI workbook report different weekly city series.
    days = [{"sourceDate": day.isoformat(), "weekIndex": block - first, "sourceBlockDays": divisor,
             "meanCases": weeks[block-first]["meanCases"] / divisor,
             "unassignedCases": weeks[block-first]["unassignedCases"] / divisor} for day, block, divisor in schedule]
    first_week = weeks[0]
    run = {"area": "QUEZON_CITY", "mode": "historical_replay", "caseSourceKind": "gp_reconstruction",
           "model": "GP reconstruction", "trainedThrough": None, "featureHistoryThrough": None, "issueBlock": None,
           "observedReferenceBlock": {"YR": start.year, "WN": first_week["week"]}, "annualContextYear": start.year,
           "observedCasesAtOrigin": None, "observedSourceYearToDateCases": sum(
               w["observed_city_week_cases"] for w in cities if w["year"] == start.year and w["week"] <= first_week["week"]),
           "environmentalInputs": [], "intervalCoverageTarget": None, "intervalCaveat": GP_RANGE_NOTE,
           "spatialCaveat": GP_NOTE, "availabilityAssumption": GP_NOTE + " " + CALENDAR_NOTE, "scenarioStart": start.isoformat(),
           "weeklyPredictions": weeks, "dailyPredictions": days, "sourceSha256": GP_SHA256,
           "unassignedWindowCases": math.fsum(d["unassignedCases"] for d in days)}
    return identify_run(run, "gp", start, duration)


def holdout_run(start, duration):
    if start < RF_START or sha256(history.DATA) != GP_SHA256:
        raise ValueError("Invalid evaluation forecast date or source history")
    schedule, cities = archive_schedule(start, duration)
    first, last = schedule[0][1], schedule[-1][1]
    binary = RF_PATH.read_bytes()
    if hashlib.sha256(binary).hexdigest() != RF_SHA256:
        raise ValueError("Historical RF predictions failed source verification")
    with np.load(io.BytesIO(binary), allow_pickle=False) as artifact:
        counts = artifact["cases"][first - 2021 * 52, :last - first + 1]
        codes = artifact["codes"].tolist()
    weeks = []
    for index, row in enumerate(counts):
        year, offset = divmod(first + index, 52)
        weeks.append({"year": year, "week": offset + 1, "YR": year, "WN": offset + 1,
                      "meanCases": math.fsum(row), "barangayCases": dict(zip(codes, row.tolist(), strict=True))})
    days = [{"sourceDate": day.isoformat(), "weekIndex": block - first, "sourceBlockDays": divisor,
             "meanCases": weeks[block - first]["meanCases"] / divisor} for day, block, divisor in schedule]
    origin = cities[first - 2012 * 52 - 1]
    origin_year = origin["year"]
    run = {"area": "QUEZON_CITY", "mode": "historical_replay", "caseSourceKind": "forecast", "model": "RF_shallow",
           "trainedThrough": 2020, "featureHistoryThrough": start.year - 1, "annualContextYear": start.year - 1,
           "issueBlock": {"YR": origin_year, "WN": origin["week"]}, "observedCasesAtOrigin": origin["observed_city_week_cases"],
           "observedSourceYearToDateCases": sum(w["observed_city_week_cases"] for w in cities
                                                if w["year"] == origin_year and w["week"] <= origin["week"]),
           "observationSource": "Training archive QC weekly city observations", "environmentalInputs": [],
           "intervalCoverageTarget": None, "intervalCaveat": "The evaluation forest supplies point forecasts.",
           "availabilityAssumption": RF_NOTE + " " + CALENDAR_NOTE, "spatialCaveat": "Each barangay uses its own weekly RF forecast.",
           "scenarioStart": start.isoformat(), "weeklyPredictions": weeks, "dailyPredictions": days,
           "sourceSha256": GP_SHA256, "forecastArtifactSha256": RF_SHA256}
    return identify_run(run, "holdout", start, duration)


def identify_run(run, source, start, duration):
    run["calendarStatus"] = "CORRECTED_SOURCE_DATES_ASSUMED_INTERVAL_STARTS"
    digest = hashlib.sha256(json.dumps(run, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {**run, "id": f"qc-{source}-replay-{start}-{duration}-{digest}", "runSha256": digest}


def load_archive_run(ident):
    match = re.fullmatch(r"qc-(gp|holdout)-replay-(\d{4}-\d{2}-\d{2})-(\d{1,2})-([0-9a-f]{64})", ident)
    if not match:
        raise ForecastRunNotFound("Invalid reconstruction ID")
    try:
        start = date.fromisoformat(match[2])
    except ValueError:
        raise ForecastRunNotFound("Invalid reconstruction date") from None
    duration = int(match[3])
    if not (FIRST_DAY <= start < END_EXCLUSIVE and 1 <= duration <= 28 and start + timedelta(days=duration) <= END_EXCLUSIVE):
        raise ForecastRunNotFound("Invalid reconstruction window")
    if match[1] == "holdout" and start < RF_START:
        raise ForecastRunNotFound("Invalid historical forecast window")
    run = holdout_run(start, duration) if match[1] == "holdout" else reconstruction_run(start, duration)
    if run["id"] != ident:
        raise ForecastRunNotFound("Unknown reconstruction")
    return run


load_reconstruction_run = load_archive_run
