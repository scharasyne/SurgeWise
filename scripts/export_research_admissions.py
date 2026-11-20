"""Package the two reviewed destination matrices for the Research page.

Run from the repository root with python -m scripts.export_research_admissions.
"""
import json

from services.engine.api.outbreak import inputs
from services.engine.domain.outbreak import distance_km
from services.engine.repositories.first_admission import GEOMETRY_PATH, MATRICES, load_matrix
from services.engine.upri_data import ROOT

DESTINATION = ROOT / "apps/web/app/research/data/first-admission.v1.json"


def build():
    folder = ROOT / "data/processed" / MATRICES["markov_preference"][0]
    manifest = json.loads((folder / "manifest.json").read_text())
    _, context, sources = inputs(manifest["runId"])
    hospitals = sorted(context["hospitals"], key=lambda h: h["id"])
    origins = sorted(context["barangays"], key=lambda b: b["name"].casefold())
    ids = [h["id"] for h in hospitals]
    geometry_hash = sources["outputs"][GEOMETRY_PATH]
    baseline, _ = load_matrix("markov_proximity", origins, ids, geometry_hash)
    adjusted, preferred = load_matrix("markov_preference", origins, ids, geometry_hash)
    rows = []
    for origin in origins:
        ident = origin["id"]
        base = dict(baseline[ident])
        final = dict(adjusted[ident])
        if preferred[ident] is None and final != base:
            raise ValueError(f"Unknown preference changed the saved row for {ident}")
        rows.append({
            "id": ident, "name": origin["name"], "preferredId": preferred[ident],
            "km": [round(distance_km(origin["coordinates"], h["coordinates"]), 2) for h in hospitals],
            "distanceOnly": [base[h] for h in ids],
            "withPreference": [final[h] for h in ids] if preferred[ident] else None,
        })
    return {
        "matrices": {policy: digest for policy, (_, digest) in MATRICES.items()},
        "halfDistanceKm": manifest["assumptions"]["halfDistanceKm"],
        "preferredMultiplier": manifest["assumptions"]["matchedFavoriteWeightMultiplier"],
        "hospitals": [{"id": h["id"], "name": h["name"]} for h in hospitals],
        "barangays": rows,
    }


if __name__ == "__main__":
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(json.dumps(build(), indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                           encoding="utf-8")
