"""Apply the reviewed Figure 4 crosswalk to a saved QC proximity scenario."""
import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.build_first_admission_matrix import write_csv
from services.engine.domain.bed_forecast import rolling_bed_demand
from services.engine.repositories.facility import DATASET_ID
from services.engine.upri_data import ROOT, sha256

BASELINE = ROOT / "data/processed/qc_first_admission_v1"
PREFERENCES = ROOT / "data/reference/qc_emergency_hospital_preferences_figure4.csv"
OUTPUT = ROOT / "data/processed/qc_first_admission_preference_v1"
FIGURE = ("https://ncts.upd.edu.ph/tssp/wp-content/uploads/2021/12/"
          "06-TSSP2021_Study-on-GIS-based-suitability-analysis-of-hospitals-in-QC-from-transport-perspective.pdf#page=10")
UNKNOWN = {"unknown_no_clear_fill", "unknown_map_text_conflict", "unknown_unmatched_facility"}


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def apply_preference(shares, favorite_index, multiplier):
    """Apply a relative weight to the favorite, preserving a distance-only row exactly."""
    if not math.isfinite(multiplier) or multiplier < 1:
        raise ValueError("Choose a finite preference multiplier of at least 1")
    if (any(not math.isfinite(p) or p <= 0 for p in shares)
            or not math.isclose(math.fsum(shares), 1, rel_tol=1e-12)):
        raise ValueError("Expected strictly positive destination shares summing to one")
    if favorite_index is None or multiplier == 1:
        return shares
    weights = shares.copy()
    weights[favorite_index] *= multiplier
    total = math.fsum(weights)
    adjusted = [w / total for w in weights]
    if min(adjusted) <= 0 or not math.isclose(math.fsum(adjusted), 1, rel_tol=1e-12):
        raise ValueError("Multiplier cannot preserve a positive probability for every destination")
    return adjusted


def load_preferences(path, origins, hospitals):
    favorites = {}
    for row in read_csv(path):
        b, h, status = row["barangayId"], row["preferredHospitalId"], row["preferenceStatus"]
        if b in favorites or origins.get(b) != row["barangayName"]:
            raise ValueError(f"Unrecognized or repeated barangay in preference crosswalk: {b}")
        if status == "matched":
            if h not in hospitals or not row["figureHospitalLabel"]:
                raise ValueError(f"Missing hospital evidence or register ID for {b}")
        elif status not in UNKNOWN or h:
            raise ValueError(f"Unresolved preferences require an unknown status and empty ID: {b}")
        favorites[b] = h or None
    if favorites.keys() != origins.keys():
        raise ValueError("Preference crosswalk must cover every baseline barangay")
    return favorites


def build(folder, baseline, preferences, multiplier):
    parent = json.loads((baseline / "manifest.json").read_text())
    files = ("first_hospital_probabilities.csv", "markov_chain.csv", "barangay_demand.csv", "daily_hospital_beds.csv")
    if parent["scenario"] != "QC hypothetical first admission v1" or parent["hospitalDatasetId"] != DATASET_ID:
        raise ValueError("Choose a QC first-admission baseline using the active register")
    for name in files:
        if sha256(baseline / name) != parent["outputHashes"][name]:
            raise ValueError(f"Saved proximity baseline failed its checksum for {name}")

    base_rows = read_csv(baseline / files[0])
    origins = {r["barangayId"]: r["barangayName"] for r in base_rows}
    hospitals = list(base_rows[0])[2:]
    if len(base_rows) != len(origins) or len(origins) != 142 or len(set(hospitals)) != 46:
        raise ValueError("Expected a 142 by 46 proximity matrix")
    favorites = load_preferences(preferences, origins, hospitals)
    matrix = {}
    for row in base_rows:
        b = row["barangayId"]
        index = hospitals.index(favorites[b]) if favorites[b] else None
        matrix[b] = apply_preference([float(row[h]) for h in hospitals], index, multiplier)
    write_csv(folder / files[0], list(base_rows[0]), ([b, origins[b], *matrix[b]] for b in origins))

    states = list(origins) + hospitals
    # Only barangay-to-hospital transitions can change in the saved absorbing chain.
    square = read_csv(baseline / files[1])
    for row in square:
        if row["fromState"] in origins:
            row.update(zip(hospitals, matrix[row["fromState"]], strict=True))
    write_csv(folder / files[1], ["fromState", *states], ([r["fromState"], *(r[s] for s in states)] for r in square))

    demand = defaultdict(dict)
    for row in read_csv(baseline / files[2]):
        demand[row["scenarioDate"]][row["barangayId"]] = float(row["expectedAdmissions"])
    dates = sorted(demand)
    arrivals = {h: [math.fsum(demand[d][b] * matrix[b][j] for b in origins) for d in dates]
                for j, h in enumerate(hospitals)}
    census = {h: rolling_bed_demand(series, parent["assumptions"]["stayDays"]) for h, series in arrivals.items()}
    original = read_csv(baseline / files[3])
    previous = defaultdict(dict)
    labels = {}
    for row in original:
        h = row["hospitalId"]
        labels[h] = row["hospitalName"]
        previous[row["scenarioDate"]][h] = float(row["expectedOccupiedDengueBedsIfAdmitted"])
    if set(previous) != set(dates) or any(day.keys() != set(hospitals) for day in previous.values()):
        raise ValueError("Baseline bed series must cover the same dates and hospitals as admissions")
    for i, d in enumerate(dates):
        if (not math.isclose(math.fsum(a[i] for a in arrivals.values()), math.fsum(demand[d].values()), abs_tol=1e-10)
                or not math.isclose(math.fsum(c[i] for c in census.values()), math.fsum(previous[d].values()), abs_tol=1e-10)):
            raise ValueError(f"Admissions or bed demand do not reconcile on {d}")
    write_csv(folder / files[3], list(original[0]),
              ([d, h, labels[h], arrivals[h][i], census[h][i]] for i, d in enumerate(dates) for h in hospitals))

    peaks = {h: max(previous[d][h] for d in dates) for h in hospitals}
    adjusted = {h: max(census[h]) for h in hospitals}

    def rank(h, values):
        return 1 + sum(peak > values[h] for peak in values.values())

    write_csv(folder / "peak_bed_comparison.csv",
              ["hospitalId", "hospitalName", "baselinePeakBeds", "adjustedPeakBeds", "changeBeds",
               "baselineRank", "adjustedRank", "placesGained"],
              ([h, labels[h], peaks[h], adjusted[h], adjusted[h] - peaks[h], rank(h, peaks),
                rank(h, adjusted), rank(h, peaks) - rank(h, adjusted)] for h in hospitals))
    return {
        "scenario": "QC hypothetical first admission with Figure 4 preference v1",
        "geography": parent["geography"], "runId": parent["runId"], "startDate": parent["startDate"],
        "endDateExclusive": parent["endDateExclusive"], "hospitalDatasetId": DATASET_ID,
        "hospitalRegisterAsOf": parent["hospitalRegisterAsOf"], "parentScenario": parent["scenario"],
        "baselineManifestSha256": sha256(baseline / "manifest.json"), "baselineOutputHashes": parent["outputHashes"],
        "preferenceSource": FIGURE, "preferenceCrosswalkSha256": sha256(preferences),
        "assumptions": {**parent["assumptions"], "matchedFavoriteWeightMultiplier": multiplier,
                        "unknownPreferenceMultiplier": 1},
        "matchedBarangays": sum(h is not None for h in favorites.values()),
        "unknownBarangays": sum(h is None for h in favorites.values()),
        "measurementKinds": parent["measurementKinds"], "units": parent["units"],
        "builderSha256": sha256(Path(__file__)),
        "bedCalculationSha256": sha256(ROOT / "services/engine/domain/bed_forecast.py"),
        "outputHashes": {p.name: sha256(p) for p in sorted(folder.glob("*.csv"))},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--preferences", type=Path, default=PREFERENCES)
    parser.add_argument("--multiplier", type=float, default=1.5)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    dest = args.output.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=dest.parent) as tmp:
        stage = Path(tmp) / "scenario"
        stage.mkdir()
        manifest = build(stage, args.baseline, args.preferences, args.multiplier)
        if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
            if not (dest / "manifest.json").is_file():
                parser.error("Choose a fresh directory or a matching export")
            saved = json.loads((dest / "manifest.json").read_text())
            saved.pop("generatedAt", None)
            if saved != manifest or any(sha256(dest / name) != digest for name, digest in manifest["outputHashes"].items()):
                parser.error("A different export exists here. Choose a fresh --output")
        else:
            manifest["generatedAt"] = datetime.now(timezone.utc).isoformat()
            (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
            stage.rename(dest)
    print(dest)


if __name__ == "__main__":
    main()
