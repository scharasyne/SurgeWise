"""Export a hypothetical first-destination chain and unconstrained dengue census.

Run from the project root with python -m scripts.build_first_admission_matrix.
"""
import argparse
import csv
import json
import math
import platform
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from services.engine.api.outbreak import inputs
from services.engine.domain.bed_forecast import rolling_bed_demand
from services.engine.domain.outbreak import allocated_forecast_trajectory, distance_km
from services.engine.domain.source_calendar import align_historical_run, historical_window
from services.engine.repositories.facility import DATASET_ID, HOSPITAL_PATH
from services.engine.upri_data import ROOT, sha256


def choice_row(distances, half_distance):
    if not math.isfinite(half_distance) or half_distance <= 0:
        raise ValueError("Enter a finite positive distance in km")
    if not distances or any(not math.isfinite(d) or d < 0 for d in distances):
        raise ValueError("All destination distances must be finite and nonnegative")
    closest = min(distances)
    weights = [2 ** (-(d - closest) / half_distance) for d in distances]
    total = math.fsum(weights)
    probabilities = [w / total for w in weights]
    if min(probabilities) <= 0 or not math.isclose(math.fsum(probabilities), 1):
        raise ValueError("Distance decay too steep to preserve every destination")
    return probabilities


def write_csv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def build(folder, run_id, half_distance, rate, los):
    if not math.isfinite(rate) or not 0 <= rate <= 1 or not 1 <= los <= 30:
        raise ValueError("Admission fraction must be in [0,1] and stay in [1,30] days")
    run, context, source_manifest = inputs(run_id, use_xgboost=True)
    start, end = historical_window(run)
    duration = (end - start).days
    if duration != 28 or "calibrationResidualPaths" not in run:
        raise ValueError("Choose a saved 28-day QC environmental forecast reference")
    daily_run = align_historical_run(run, start, duration)
    days = allocated_forecast_trajectory(daily_run, context, {"extraCasesPerWeek": 0, "shockProfile": "step"}, duration)
    dates = [row["date"] for row in daily_run["dailyPredictions"]]
    hospitals = sorted(context["hospitals"], key=lambda h: h["id"])
    barangays = context["barangays"]
    hospital_ids = [h["id"] for h in hospitals]
    origin_ids = [b["id"] for b in barangays]
    if len(set(origin_ids)) != 142 or len(set(hospital_ids)) != 46:
        raise ValueError("Expected the complete QC network")
    matrix = {}
    for b in barangays:
        distances = [distance_km(b["coordinates"], h["coordinates"]) for h in hospitals]
        matrix[b["id"]] = choice_row(distances, half_distance)
    write_csv(folder / "first_hospital_probabilities.csv", ["barangayId", "barangayName", *hospital_ids],
              ([b["id"], b["name"], *matrix[b["id"]]] for b in barangays))

    # The destination block is the identity because the first admission ends the episode.
    zeros = [0] * len(origin_ids)
    square = [[b, *zeros, *matrix[b]] for b in origin_ids]
    square.extend([h, *zeros, *(int(h == dest) for dest in hospital_ids)] for h in hospital_ids)
    write_csv(folder / "markov_chain.csv", ["fromState", *origin_ids, *hospital_ids], square)

    arrivals = {h: [] for h in hospital_ids}
    origin_rows = []
    for day, label in zip(days, dates, strict=True):
        cases = {b["barangayId"]: b["expectedCases"] for b in day["barangays"]}
        origin_rows.extend([label, b["id"], b["name"], cases[b["id"]], cases[b["id"]] * rate] for b in barangays)
        for j, h in enumerate(hospital_ids):
            arrivals[h].append(rate * math.fsum(cases[b] * matrix[b][j] for b in origin_ids))
        if not math.isclose(math.fsum(a[-1] for a in arrivals.values()), day["expectedCases"] * rate, abs_tol=1e-10):
            raise ValueError("Daily hospital admissions do not reconcile to the QC forecast")
    write_csv(folder / "barangay_demand.csv",
              ["scenarioDate", "barangayId", "barangayName", "modeledCases", "expectedAdmissions"], origin_rows)
    beds = {h: rolling_bed_demand(a, los) for h, a in arrivals.items()}
    write_csv(folder / "daily_hospital_beds.csv",
              ["scenarioDate", "hospitalId", "hospitalName", "expectedFirstAdmissions", "expectedOccupiedDengueBedsIfAdmitted"],
              ([label, h["id"], h["name"], arrivals[h["id"]][i], beds[h["id"]][i]]
               for i, label in enumerate(dates) for h in hospitals))
    paths = [HOSPITAL_PATH, "apps/web/public/data/qc-barangays.geojson",
             "data/processed/upri_noah/qc-barangay-xgboost.json", "data/processed/upri_noah/qc-environmental-forecasts.json",
             "scripts/build_first_admission_matrix.py", "services/engine/domain/source_calendar.py",
             "services/engine/domain/bed_forecast.py", "services/engine/domain/outbreak.py"]
    manifest = {
        "scenario": "QC hypothetical first admission v1", "geography": "Quezon City",
        "method": "Conditional on admission in this network. Relative choice weight halves per halfDistanceKm. Hospitals absorb on first arrival.",
        "assumptions": {"halfDistanceKm": half_distance, "admissionFraction": rate, "stayDays": los, "admissionDelayDays": 0,
                        "initialDengueCensus": 0, "all46AssumedEligible": True, "unconstrainedAdmission": True,
                        "distance": context["distanceMethod"], "outsideNetworkDestinationsIncluded": False},
        "measurementKinds": {"probabilities": "assumption", "barangayCases": "modeled_allocation", "arrivalsAndBeds": "modeled_allocation"},
        "units": {"probabilities": "fraction conditional on in-network admission", "modeledCases": "expected cases/day",
                  "expectedAdmissions": "expected first admissions/day", "occupiedBeds": "expected end-of-day dengue census"},
        "startDate": start.isoformat(), "endDateExclusive": end.isoformat(), "calendarAssumption": run["calendarStatus"],
        "runId": run_id, "modelVersion": run["methodVersion"], "issueBlock": run["issueBlock"], "issueDate": run["issueDate"],
        "trainingCutoffBlock": run["trainingCutoffBlock"], "spatialFeatureCutoffYear": context["weightYear"],
        "spatialRanking": context["hotspotRanking"]["methodVersion"], "hospitalDatasetId": DATASET_ID,
        "hospitalRegisterAsOf": hospitals[0]["sourceAsOf"], "underlyingSources": source_manifest["sources"],
        "software": {"python": platform.python_version(), "forecastTraining": run["software"]},
        "simulationSeed": None, "randomness": "Deterministic expected counts", "inputHashes": {p: sha256(ROOT / p) for p in paths},
        "outputHashes": {p.name: sha256(p) for p in sorted(folder.glob("*.csv"))},
    }
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="qc-weather-residual-v2-QUEZON_CITY-2025-4")
    parser.add_argument("--half-distance-km", type=float, default=3)
    parser.add_argument("--admission-fraction", type=float, default=.15)
    parser.add_argument("--stay-days", type=int, default=4)
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/qc_first_admission_v1")
    args = parser.parse_args()
    dest = args.output.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=dest.parent) as tmp:
        stage = Path(tmp) / "scenario"
        stage.mkdir()
        manifest = build(stage, args.run_id, args.half_distance_km, args.admission_fraction, args.stay_days)
        if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
            if not (dest / "manifest.json").is_file():
                parser.error("Choose an empty directory or the matching scenario export for --output.")
            saved = json.loads((dest / "manifest.json").read_text())
            saved.pop("generatedAt", None)
            if saved != manifest or any(sha256(dest / name) != digest for name, digest in manifest["outputHashes"].items()):
                parser.error("This directory contains a different export. Choose a fresh --output for the new scenario.")
        else:
            manifest["generatedAt"] = datetime.now(timezone.utc).isoformat()
            (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            stage.rename(dest)
    print(dest)


if __name__ == "__main__":
    main()
