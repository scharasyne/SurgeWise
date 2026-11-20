"""Build the QC simulation's offline replay from the selected Drive experiment."""
import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[1]
FOLDER = "https://drive.google.com/drive/folders/1gfU3DU0itB6u1X5DNw-yOhCjeg_fqmxM"
HASHES = {
    "predictions": "46a1a689043bce33925eba765b37ecf8a82023c6faa20632323da4b47735a094",
    "model": "07ae2cc3ec466c10785c7a428b72885e11df209b98743f3a855a55d8a38cac90",
    "metadata": "b71d20a213039ec109980bc8db41f59f0e2084215cd9ba80d6eb216268f2eca2",
}


def collect(rows, approved_ids):
    origins = {}
    for row in rows:
        if row["model"] != "RandomForest":
            continue
        code = row["barangay_code"]
        origin, target, horizon = (int(row[k]) for k in ("origin_block", "target_block", "horizon"))
        value = float(row["prediction"])
        if (code not in approved_ids or horizon not in range(1, 5) or target != origin + horizon
                or not math.isfinite(value) or value < 0):
            raise ValueError("Invalid RandomForest prediction key or count")
        values = origins.setdefault(origin, {}).setdefault(code, [None] * 4)
        if values[horizon - 1] is not None:
            raise ValueError("Duplicate barangay, origin and horizon")
        values[horizon - 1] = value
    if not origins or any(None in values for places in origins.values() for values in places.values()):
        raise ValueError("Incomplete four-horizon prediction")
    return origins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in HASHES:
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/upri_noah/synthetic-barangay-rf.json.gz")
    args = parser.parse_args()
    for name, expected in HASHES.items():
        if hashlib.sha256(getattr(args, name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Unexpected source bytes for {name}")
    metadata = json.loads(args.metadata.read_bytes())
    geometry = json.loads((ROOT / "apps/web/public/data/qc-barangays.geojson").read_bytes())
    codes = {f["properties"]["ADM4_PCODE"] for f in geometry["features"]}
    with args.predictions.open(encoding="utf-8", newline="") as stream:
        origins = collect(csv.DictReader(stream), codes)
    evidence = {"model": metadata["selected_model_using_2022"], "beta": metadata["scenario_beta"],
                "trainingYears": metadata["periods"]["train"], "selectionYear": 2022, "versions": metadata["versions"],
                "features": metadata["features"], "limitations": metadata["limitations"],
                "trainingInputs": {Path(k).name: v for k, v in metadata["input_files"].items()},
                "sourceFolder": FOLDER, "hashes": HASHES, "runVersion": "20261118_154549_934553_starter"}
    encoded = json.dumps({"evidence": evidence, "origins": origins}, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    with NamedTemporaryFile(dir=args.output.parent, delete=False) as temp:
        temp.write(gzip.compress(encoded, mtime=0))
    Path(temp.name).replace(args.output)
    print(f"{len(origins)} origins, {hashlib.sha256(encoded).hexdigest()} (uncompressed SHA-256)")


if __name__ == "__main__":
    main()
