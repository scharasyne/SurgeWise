"""Read approved RandomForest outputs. Each run is one origin with four local forecasts."""
from functools import lru_cache
import gzip
import hashlib
import json
import math
import zlib

from ..upri_data import ROOT

PATH = ROOT / "data/processed/upri_noah/synthetic-barangay-rf.json.gz"
DIGEST = "068b9387275fbc9db026e9364187461178e0588aaf42e116475cd40c98d4aff3"
PREFIX = "synthetic-brgy-rf-"
CAVEAT = "RandomForest was trained on retrospective synthetic weekly counts. Accuracy against observed weekly barangay counts is unknown."
INTERVAL = "The synthetic experiment supplies point estimates only."


def block(number):
    year, index = divmod(number, 52)
    return {"YR": year, "WN": index + 1}


@lru_cache(maxsize=1)
def _decode(compressed):
    raw = gzip.decompress(compressed)
    if hashlib.sha256(raw).hexdigest() != DIGEST:
        raise ValueError("Synthetic forecast checksum mismatch")
    data = json.loads(raw)
    runs = {}
    for key, places in data["origins"].items():
        origin = int(key)
        ident = PREFIX + key
        weekly = [{**block(origin + h + 1), "meanCases": math.fsum(v[h] for v in places.values())} for h in range(4)]
        runs[ident] = {"id": ident, "area": "QUEZON_CITY", "model": "RandomForest", "issueBlock": block(origin),
            "weeklyPredictions": weekly, "weeklyByBarangay": places, "sourceSha256": data["evidence"]["hashes"]["predictions"],
            "syntheticEvidence": data["evidence"], "runSha256": DIGEST, "environmentalInputs": [],
            "observedCasesAtOrigin": None, "observedSourceYearToDateCases": None, "intervalCoverageTarget": None,
            "intervalCaveat": INTERVAL, "spatialCaveat": CAVEAT,
            "availabilityAssumption": "Replay uses synthetic case lags and city weather. Synthetic labels incorporate complete annual totals."}
    return runs


def approved_runs():
    try:
        return _decode(PATH.read_bytes())
    except (OSError, EOFError, ValueError, zlib.error) as error:
        raise ValueError("Approved synthetic RandomForest predictions unavailable. Restore the pinned artifact or rebuild with scripts/import_synthetic_barangay.py.") from error
