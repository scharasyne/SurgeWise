"""Reviewed QC destination probabilities for an admission within the active network."""
import csv
import hashlib
import io
import math
from typing import Literal

from ..upri_data import ROOT
from .facility import HOSPITAL_SHA256

ArrivalPolicy = Literal["nearest", "nearest_three_equal", "markov_proximity", "markov_preference"]
AllocationPolicy = Literal["nearest", "optimized", "first_hospital"]
# Pin the reviewed destination block, independently of the example forecast used in its export.
MATRICES = {
    "markov_proximity": ("qc_first_admission_v1", "fe0d87cb07d39246e61f283585e5afa767afe1cce89cf45ec1ad0eb7241b0135"),
    "markov_preference": ("qc_first_admission_preference_v1", "0b50422dda48df7066f81d87738040a88bc31439e67f0429a23f8f3249467a41"),
}


GEOMETRY_PATH = "apps/web/public/data/qc-barangays.geojson"
GEOMETRY_HASH = "886381cbcb97c405d3a260cd74fa256ba9e963e64e5fc972570003cdc79b51b9"
PREFERENCE_HASH = "f5416d319459add055f5aa1fec06c51e81a5813dc242702ffc78483e09413c6c"


def load_matrix(policy, barangays, facility_ids, geometry_hash):
    if HOSPITAL_SHA256 != "929cbeb97a0edffdfeb8257ad5857347b9b56661004dbdaa364f4873fbd620c5":
        raise ValueError("Hospital register differs from the reviewed first-admission network")
    if geometry_hash != GEOMETRY_HASH:
        raise ValueError("Barangay geometry differs from the reviewed first-admission network")
    folder, expected = MATRICES[policy]
    path = ROOT / "data/processed" / folder / "first_hospital_probabilities.csv"
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("First-admission matrix checksum mismatch")
    reader = csv.reader(io.StringIO(data.decode("utf-8")))
    _, _, *hospitals = next(reader)
    if len(hospitals) != 46 or set(hospitals) != set(facility_ids):
        raise ValueError("First-admission matrix requires the complete QC hospital network")
    shares = {}
    for origin, _, *values in reader:
        probabilities = list(map(float, values))
        if (origin in shares or any(not math.isfinite(p) or p <= 0 for p in probabilities)
                or not math.isclose(math.fsum(probabilities), 1, rel_tol=1e-12)):
            raise ValueError("Invalid first-admission probabilities")
        shares[origin] = sorted(zip(hospitals, probabilities, strict=True), key=lambda item: (-item[1], item[0]))
    if len(shares) != 142 or set(shares) != {b["id"] for b in barangays}:
        raise ValueError("First-admission matrix does not cover the scenario barangays")
    crosswalk = (ROOT / "data/reference/qc_emergency_hospital_preferences_figure4.csv").read_bytes()
    if hashlib.sha256(crosswalk).hexdigest() != PREFERENCE_HASH:
        raise ValueError("Emergency preference crosswalk checksum mismatch")
    favorites = {row["barangayId"]: row["preferredHospitalId"] or None
                 for row in csv.DictReader(io.StringIO(crosswalk.decode("utf-8")))}
    if favorites.keys() != shares.keys() or any(h and h not in hospitals for h in favorites.values()):
        raise ValueError("Emergency preference evidence does not match the network")
    return shares, favorites
