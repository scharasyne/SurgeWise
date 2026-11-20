"""Immutable, server-generated weekly predictions for the hospital workspace."""
from datetime import timedelta
import hashlib
import json
import re
from uuid import uuid4

from production.surgewise import predictor
from ..domain.source_calendar import block_start, day_schedule, source_block
from ..upri_data import sha256
from .forecast_runs import FOLDER, ForecastRunNotFound
from .production_runs import INTERVAL_NOTE, SPATIAL_NOTE, simulation_predictions

ARCHIVE_ONLY_NOTE = "Simulation uses the weekly archive ending at 2022 week 52. Choose an archive forecast."

ID_PATTERN = r"qc-weekly-([a-f0-9]{64})"


def save_handoff(forecast, updates, local_updates):
    first, last = forecast["city"][0], forecast["city"][-1]
    if first["year"] > 2035 or any(w["scenario_multiplier"] > 10 for w in forecast["city"]):
        return {"unavailableReason": "Hospital planning supports starts through 2035 and scenario multipliers up to 10."}
    start = block_start(first["year"], first["week"])
    next_year, offset = divmod(last["year"] * 52 + last["week"], 52)
    duration = min(28, (block_start(next_year, offset + 1) - start).days)
    weekly, days = simulation_predictions(forecast, day_schedule(start, duration), source_block(start) - 1)
    for day in days:
        day["scenarioMultiplier"] = weekly[day["weekIndex"]]["scenario_multiplier"]
    origin = forecast["as_of"]
    if updates:
        year_rows = sorted((r for r in updates if r["year"] == origin["year"]), key=lambda row: row["week"])
        observed = year_rows[-1]["city_cases"]
        year_total = sum(r["city_cases"] for r in year_rows) if year_rows[0]["week"] == 1 else None
        source = "User-supplied aggregate observations (unverified)"
    else:
        city = predictor.assets()[2]["city"]
        observed, year_total = float(city[-1]), float(city[-52:].sum())
        source = "Training archive QC weekly city observations"
    run = {"area": "QUEZON_CITY", "mode": "hypothetical_shock", "caseSourceKind": "forecast",
           "model": forecast["model"], "trainedThrough": forecast["trained_through"],
           "featureHistoryThrough": forecast["feature_history_through"], "issueBlock": {"YR": origin["year"], "WN": origin["week"]},
           "observedCasesAtOrigin": observed, "observedSourceYearToDateCases": year_total, "observationSource": source,
           "environmentalInputs": [], "intervalCoverageTarget": None, "intervalCaveat": INTERVAL_NOTE, "spatialCaveat": SPATIAL_NOTE,
           "availabilityAssumption": source + ". Forecast targets follow the final supplied week on the assumed January 1 calendar.",
           "scenarioStart": start.isoformat(), "weeklyPredictions": weekly, "dailyPredictions": days,
           "sourceSha256": sha256(predictor.PACKAGE / "data/history.npz"), "modelSha256": sha256(predictor.PACKAGE / "models/forest.npz"),
           "updatesSha256": hashlib.sha256(json.dumps([updates, local_updates], sort_keys=True).encode()).hexdigest()}
    data = json.dumps(run, sort_keys=True, allow_nan=False).encode()
    digest = hashlib.sha256(data).hexdigest()
    folder = FOLDER / "scenarios/weekly"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (digest + ".json")
    if not target.exists():
        pending = folder / (uuid4().hex + ".tmp")
        try:
            pending.write_bytes(data)
            target.hardlink_to(pending)
        except FileExistsError:
            pass
        finally:
            pending.unlink(missing_ok=True)
    return {"forecastRunId": "qc-weekly-" + digest, "startDate": start.isoformat(),
            "endDate": (start + timedelta(days=duration)).isoformat(), "days": duration}


def load_weekly_run(ident):
    match = re.fullmatch(ID_PATTERN, ident)
    if not match:
        raise ForecastRunNotFound("Invalid weekly forecast ID")
    path = FOLDER / "scenarios/weekly" / (match[1] + ".json")
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise ForecastRunNotFound("Unknown weekly forecast") from None
    if hashlib.sha256(data).hexdigest() != match[1]:
        raise ValueError("Weekly forecast checksum mismatch")
    return {**json.loads(data), "id": ident, "runSha256": match[1]}
