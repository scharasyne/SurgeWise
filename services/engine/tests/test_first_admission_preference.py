import json
import math
from collections import defaultdict

import pytest

from scripts.build_first_admission_preference import (
    BASELINE, PREFERENCES, apply_preference, build, load_preferences, read_csv,
)
from scripts import export_research_admissions


def test_research_explorer_matches_reviewed_matrices():
    published = json.loads(export_research_admissions.DESTINATION.read_text(encoding="utf-8"))
    assert published == export_research_admissions.build()
    hospital_ids = [h["id"] for h in published["hospitals"]]
    for policy, column in [("markov_proximity", "distanceOnly"), ("markov_preference", "withPreference")]:
        folder, _ = export_research_admissions.MATRICES[policy]
        reference = read_csv(BASELINE.parent / folder / "first_hospital_probabilities.csv")
        rows = {r["id"]: r for r in published["barangays"]}
        assert {r["barangayId"] for r in reference} == rows.keys()
        for r in reference:
            origin = rows[r["barangayId"]]
            probabilities = origin[column] if origin[column] is not None else origin["distanceOnly"]
            assert probabilities == [float(r[h]) for h in hospital_ids]
            assert len(origin["km"]) == len(probabilities) == 46


def test_preference_is_relative_weight_before_normalization():
    shares = [.4, .4, .2]
    assert apply_preference(shares, 1, 1.5) == pytest.approx([1/3, .5, 1/6])
    assert apply_preference(shares, 1, 1) == apply_preference(shares, None, 2) == shares
    for bad in [float("nan"), float("inf"), .5]:
        with pytest.raises(ValueError, match="multiplier"):
            apply_preference(shares, None, bad)


def test_preferences_require_a_unique_evidenced_join(tmp_path):
    origins = {"a": "A", "b": "B"}
    hospitals = ["one", "two"]
    path = tmp_path / "preferences.csv"
    header = "barangayId,barangayName,figureHospitalLabel,preferredHospitalId,preferenceStatus\n"
    known = "a,A,First Hospital,one,matched\n"
    unknown = "b,B,,,unknown_no_clear_fill\n"
    path.write_text(header + known + unknown)
    assert load_preferences(path, origins, hospitals) == {"a": "one", "b": None}
    for invalid in [known, known + known, known + unknown.replace(",,,", ",,one,"),
                    known.replace("one", "absent") + unknown, known.replace("First Hospital", "") + unknown]:
        path.write_text(header + invalid)
        with pytest.raises(ValueError):
            load_preferences(path, origins, hospitals)


def test_reject_damaged_baseline(tmp_path):
    manifest = json.loads((BASELINE / "manifest.json").read_text())
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "first_hospital_probabilities.csv").write_text("truncated")
    with pytest.raises(ValueError, match="checksum"):
        build(tmp_path, tmp_path, PREFERENCES, 1.5)


def test_adjusted_chain_and_beds_on_same_qc_demand(tmp_path):
    meta = build(tmp_path, BASELINE, PREFERENCES, 1.5)
    base = {r["barangayId"]: r for r in read_csv(BASELINE / "first_hospital_probabilities.csv")}
    rows = {r["barangayId"]: r for r in read_csv(tmp_path / "first_hospital_probabilities.csv")}
    refs = {r["barangayId"]: r for r in read_csv(PREFERENCES)}
    square = {r["fromState"]: r for r in read_csv(tmp_path / "markov_chain.csv")}
    hospitals = set(square) - set(base)
    assert len(square) == 188 and len(hospitals) == 46
    assert len(rows) == 142 and rows.keys() == base.keys() == refs.keys()
    assert (meta["matchedBarangays"], meta["unknownBarangays"]) == (14, 128)
    for b, r in rows.items():
        assert all(float(square[b][origin]) == 0 for origin in base)
        shares = [float(r[h]) for h in hospitals]
        assert min(shares) > 0 and math.fsum(shares) == pytest.approx(1, abs=1e-12)
        assert all(square[b][h] == r[h] for h in hospitals)
        favorite = refs[b]["preferredHospitalId"]
        if favorite:
            assert float(r[favorite]) > float(base[b][favorite])
            assert all(float(r[h]) < float(base[b][h]) for h in hospitals - {favorite})
        else:
            assert r == base[b]
    for h in hospitals:
        assert all(float(square[h][state]) == float(h == state) for state in square)

    by_day = defaultdict(dict)
    for r in read_csv(BASELINE / "barangay_demand.csv"):
        by_day[r["scenarioDate"]][r["barangayId"]] = float(r["expectedAdmissions"])
    history = defaultdict(list)
    old_beds = defaultdict(float)
    for r in read_csv(BASELINE / "daily_hospital_beds.csv"):
        old_beds[r["scenarioDate"]] += float(r["expectedOccupiedDengueBedsIfAdmitted"])
    new_beds = defaultdict(float)
    days = read_csv(tmp_path / "daily_hospital_beds.csv")
    assert len(days) == len({(r["hospitalId"], r["scenarioDate"]) for r in days}) == 28 * 46
    for r in days:
        d, h = r["scenarioDate"], r["hospitalId"]
        arrive = math.fsum(by_day[d][b] * float(rows[b][h]) for b in rows)
        history[h].append(arrive)
        assert float(r["expectedFirstAdmissions"]) == pytest.approx(arrive)
        beds = float(r["expectedOccupiedDengueBedsIfAdmitted"])
        assert beds == pytest.approx(sum(history[h][-4:]))
        new_beds[d] += beds
    assert dict(new_beds) == pytest.approx(dict(old_beds))
    summary = read_csv(tmp_path / "peak_bed_comparison.csv")
    assert {r["hospitalId"] for r in summary} == hospitals
    for r in summary:
        assert float(r["adjustedPeakBeds"]) == max(
            float(day["expectedOccupiedDengueBedsIfAdmitted"]) for day in days if day["hospitalId"] == r["hospitalId"]
        )
        assert float(r["changeBeds"]) == pytest.approx(float(r["adjustedPeakBeds"]) - float(r["baselinePeakBeds"]))
