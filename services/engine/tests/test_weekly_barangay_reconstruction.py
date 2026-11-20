"""Small synthetic fixtures; no observations or clinical assumptions."""
import importlib
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def math_tools():
    path = Path(__file__).resolve().parents[3] / "scripts/generate_weekly_barangay.py"
    assert path.is_file(), "Weekly reconstruction mathematics has not been implemented"
    return importlib.import_module("scripts.generate_weekly_barangay")


def test_median_recovery_preserves_observed_zero_and_raw_missing(math_tools):
    data = pd.DataFrame({"barangay_code": ["A"] * 5, "year": range(2010, 2015),
                         "annual_cases": [0, 10, 20, np.nan, 1000]})
    original = data.copy(deep=True)
    out = math_tools.median_recover(data, pd.Series(1000, index=range(2010, 2015)))
    assert out.annual_used.tolist() == [0, 10, 20, 15, 1000]
    assert out.imputed.tolist() == [False, False, False, True, False]
    assert out.donor_years.iloc[3] == "2010|2011|2012|2014"
    assert pd.isna(out.annual_cases.iloc[3])
    pd.testing.assert_frame_equal(data, original)


def test_share_median_and_cutoff_exclude_future_donors(math_tools):
    data = pd.DataFrame({"barangay_code": ["A"] * 5, "year": range(2010, 2015),
                         "annual_cases": [10, 20, 30, np.nan, 900]})
    totals = pd.Series([100, 200, 300, 1000, 1000], index=range(2010, 2015))
    out = math_tools.median_recover(data, totals, method="share_median", donor_cutoff=2012)
    assert out.annual_used.iloc[3] == 100
    assert out.donor_years.iloc[3] == "2010|2011|2012"
    assert not out.imputed.iloc[4]


def test_no_donors_stays_unknown(math_tools):
    data = pd.DataFrame({"barangay_code": ["A", "B"], "year": [2010, 2010],
                         "annual_cases": [np.nan, 12]})
    out = math_tools.median_recover(data, pd.Series({2010: 100}))
    assert pd.isna(out.annual_used.iloc[0])
    assert out.recovery_method.iloc[0] == "unknown_insufficient_donors"


def test_largest_remainder_conserves_total_and_ties_are_stable(math_tools):
    assert math_tools.largest_remainder([1, 1, 1], 5).tolist() == [2, 2, 1]
    assert math_tools.largest_remainder([0, 2, 3], 0).tolist() == [0, 0, 0]
    with pytest.raises(ValueError):
        math_tools.largest_remainder([0, 0], 1)


def test_ipf_independence_zero_margins_and_incompatible_totals(math_tools):
    x, diag = math_tools.ipf(np.ones((3, 3)), [2, 4, 0], [3, 3, 0])
    np.testing.assert_allclose(x, [[1, 1, 0], [2, 2, 0], [0, 0, 0]], atol=1e-8)
    assert diag["max_margin_error"] < 1e-8
    with pytest.raises(ValueError, match="totals"):
        math_tools.ipf(np.ones((2, 2)), [2, 4], [3, 4])
    with pytest.raises(ValueError, match="positive"):
        math_tools.ipf(np.array([[0, 0], [1, 1]]), [1, 1], [1, 1])


def test_ipf_does_not_return_unconverged_results(math_tools):
    with pytest.raises(ValueError, match="converge"):
        math_tools.ipf([[1, 2], [3, 4]], [20, 1], [5, 16], max_iter=1)


def test_controlled_rounding_conserves_both_margins_and_zero_cells(math_tools):
    x = np.array([[0.6, 0.4, 0], [0.4, 0.6, 0]])
    result = math_tools.controlled_round(x, [1, 1], [1, 1, 0])
    np.testing.assert_array_equal(result, [[1, 0, 0], [0, 1, 0]])
    np.testing.assert_array_equal(result.sum(axis=1), [1, 1])
    np.testing.assert_array_equal(result.sum(axis=0), [1, 1, 0])


@pytest.mark.parametrize("bad", [[-1, 2], [np.inf, 1], [np.nan, 1]])
def test_invalid_numbers_fail(math_tools, bad):
    with pytest.raises(ValueError):
        math_tools.largest_remainder(bad, 4)


def test_calendar_requires_all_source_blocks_and_rejects_duplicates(math_tools):
    week = pd.DataFrame({"YR": [2010] * 52, "WN": range(1, 53),
                         "DC_QC": [10] * 52, "RF_NASA": [1.0] * 52})
    assert len(math_tools.validate_calendar(week)) == 52
    for bad in [week.iloc[:-1], pd.concat([week, week.iloc[:1]])]:
        with pytest.raises(ValueError):
            math_tools.validate_calendar(bad)


def test_gis_codes_use_explicit_crosswalk_and_preserve_source_null(math_tools):
    annual = pd.DataFrame({"ADM4_PCODE": ["PH1307404001", "PH1307404031"],
                           "Barangay": ["Alicia", "DoÃ±a Imelda"]})
    gis = pd.DataFrame({"barangay_code": ["PH1307404001", None],
                        "barangay_name": ["Alicia", "Doña Imelda"], "year": [2010, 2010]})
    crosswalk = {"Doña Imelda": "PH1307404031"}
    out = math_tools.reconcile_gis(gis, annual, crosswalk)
    assert out.barangay_code.tolist() == ["PH1307404001", "PH1307404031"]
    assert pd.isna(out.source_barangay_code.iloc[1])
    assert out.identifier_method.iloc[1] == "explicit_project_name_crosswalk"
    with pytest.raises(ValueError):
        math_tools.reconcile_gis(gis, annual, {})
    with pytest.raises(ValueError):
        math_tools.reconcile_gis(pd.concat([gis, gis.iloc[:1]]), annual, crosswalk)


def test_allocation_keeps_missing_barangays_and_separate_weekly_targets(math_tools):
    annual = pd.DataFrame({"barangay_code": ["A", "B", "C"], "year": [2010] * 3,
                           "annual_cases": [2, 4, np.nan], "annual_used": [2, 4, np.nan]})
    gis = pd.DataFrame({"barangay_code": ["A", "B", "C"], "year": [2010] * 3,
                        "settlement_proportion": [0.1, 0.9, 0.5],
                        "value_status": ["satellite_derived"] * 3})
    weekly = pd.DataFrame({"YR": [2010] * 52, "WN": range(1, 53),
                          "DC_QC": [1] * 52, "RF_NASA": np.arange(52, dtype=float)})
    result, audit = math_tools.allocate(annual, gis, weekly, beta=0.5)
    assert len(result) == 156
    assert result.loc[result.barangay_code == "C", "synthetic_cases"].isna().all()
    assert result.loc[result.barangay_code == "A", "synthetic_cases"].sum() == 2
    assert result.loc[result.barangay_code == "B", "synthetic_cases"].sum() == 4
    assert audit.annual_total_used.iloc[0] == 6
    assert audit.qc_observed_total.iloc[0] == 52
    assert audit.scaled_weekly_total.iloc[0] == 6
    assert result.rainfall_lag_missing.groupby(result.source_week).first().sum() == 4
    missing_gis = gis.copy(); missing_gis.loc[0, "settlement_proportion"] = np.nan
    with pytest.raises(ValueError, match="settlement"):
        math_tools.allocate(annual, missing_gis, weekly)


def test_cli_exports_provenance_and_checksums(tmp_path, math_tools):
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/generate_weekly_barangay.py"),
         "--root", str(root), "--output", str(tmp_path), "--recovery", "count_median"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    path = tmp_path / "manifest_count_median.json"
    assert path.is_file(), "CLI-derived counts require their own provenance manifest"
    manifest = json.loads(path.read_text())
    assert manifest["measurementKind"] == "modeled_allocation"
    assert manifest["recovery"] == "count_median"
    assert manifest["inputs"]
    for entry in manifest["outputs"]:
        assert hashlib.sha256((tmp_path / entry["name"]).read_bytes()).hexdigest() == entry["sha256"]
    counts = pd.read_csv(tmp_path / "weekly_count_median.csv.gz", low_memory=False)
    assert counts.annual_input_kind.eq("assumption").sum() == 39 * 52
    assert counts.units.eq("cases per source block").all()
