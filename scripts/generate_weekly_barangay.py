"""Offline retrospective allocation, never observed weekly barangay surveillance.

Pure functions are shared by notebook 06 and focused numerical tests. No runtime
forecast, API, hospital or source observation artifacts are changed.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import unicodedata

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def nonnegative(values, name="values"):
    values = np.asarray(values, dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError(f"{name} must be finite and nonnegative")
    return values


def unique_keys(frame, keys):
    if frame.empty or frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError(f"Empty, missing or duplicate keys: {keys}")


def largest_remainder(weights, total):
    """Hamilton apportionment, stable index tie order, integer grand total."""
    weights = nonnegative(weights)
    if weights.ndim != 1 or not len(weights):
        raise ValueError("Weights must be a nonempty vector")
    if not np.isfinite(total) or total < 0 or total != int(total):
        raise ValueError("Total must be a nonnegative integer")
    if total == 0:
        return np.zeros(len(weights), dtype=np.int64)
    if weights.sum() <= 0:
        raise ValueError("Positive total requires positive weights")
    expected = weights / weights.sum() * total
    result = np.floor(expected).astype(np.int64)
    remaining = int(total - result.sum())
    order = np.argsort(-(expected - result), kind="stable")
    result[order[:remaining]] += 1
    return result


def median_recover(annual, city_totals, method="count_median", donor_cutoff=None, min_donors=3):
    """Fill only null counts; donors always come from original, known rows.

    No cutoff means retrospective donors, including later years. donor_cutoff is
    an explicit latest donor year, not a claim about historical publication dates.
    Shares are annual barangay counts / QC weekly annual totals; these sources
    disagree, so those ratios are normalization features, not validated incidence.
    """
    unique_keys(annual, ["barangay_code", "year"])
    nonnegative(annual.annual_cases.dropna(), "annual cases")
    if method not in {"count_median", "share_median"} or min_donors < 1:
        raise ValueError("Unsupported median method or donor minimum")
    if city_totals.index.has_duplicates:
        raise ValueError("Duplicate QC annual totals")
    nonnegative(city_totals, "QC annual totals")
    out = annual.copy().reset_index(drop=True)
    out["annual_used"] = out.annual_cases.astype(float)
    out["imputed"] = False
    out["recovery_method"] = np.where(out.annual_cases.notna(), "observed_unchanged", "unknown_insufficient_donors")
    out["donor_years"] = ""
    out["donor_count"] = 0
    out["estimate_unrounded"] = np.nan
    out["donor_iqr_scaled"] = np.nan
    for i in out.index[out.annual_cases.isna()]:
        row = out.loc[i]
        donors = annual.loc[(annual.barangay_code == row.barangay_code) & annual.annual_cases.notna()].sort_values("year")
        if donor_cutoff is not None:
            donors = donors.loc[donors.year <= donor_cutoff]
        estimates = donors.annual_cases.astype(float).copy()
        if method == "share_median":
            denominators = donors.year.map(city_totals)
            usable = denominators.notna() & denominators.gt(0)
            donors = donors.loc[usable]
            estimates = donors.annual_cases / donors.year.map(city_totals)
            target = city_totals.get(row.year, np.nan)
            if not np.isfinite(target) or target <= 0:
                continue
            estimates = estimates * target
        out.loc[i, "donor_years"] = "|".join(donors.year.astype(int).astype(str))
        out.loc[i, "donor_count"] = len(donors)
        if len(donors) < min_donors:
            continue
        value = float(estimates.median())
        out.loc[i, "estimate_unrounded"] = value
        out.loc[i, "donor_iqr_scaled"] = float(estimates.quantile(.75) - estimates.quantile(.25))
        out.loc[i, "annual_used"] = int(np.floor(value + .5))
        out.loc[i, "imputed"] = True
        out.loc[i, "recovery_method"] = method + ("_retrospective" if donor_cutoff is None else f"_donors_through_{donor_cutoff}")
    return out


def ipf(seed, row_targets, column_targets, tol=1e-8, max_iter=10000):
    """Alternating proportional fitting; positive active support is required."""
    x = nonnegative(seed, "seed").copy()
    rows = nonnegative(row_targets, "row targets")
    cols = nonnegative(column_targets, "column targets")
    if rows.ndim != 1 or cols.ndim != 1 or x.shape != (len(rows), len(cols)):
        raise ValueError("Seed and margin shapes disagree")
    if not np.isclose(rows.sum(), cols.sum(), atol=tol, rtol=0):
        raise ValueError("Incompatible grand totals")
    active = np.outer(rows > 0, cols > 0)
    if (x[active] <= 0).any():
        raise ValueError("Seed must be positive on all positive-margin cells")
    x[~active] = 0
    if rows.sum() == 0:
        return x, {"iterations": 0, "max_margin_error": 0.0}
    for iteration in range(1, max_iter + 1):
        factors = np.divide(rows, x.sum(axis=1), out=np.zeros_like(rows), where=x.sum(axis=1) > 0)
        x *= factors[:, None]
        factors = np.divide(cols, x.sum(axis=0), out=np.zeros_like(cols), where=x.sum(axis=0) > 0)
        x *= factors[None, :]
        error = max(np.max(np.abs(x.sum(axis=1) - rows)), np.max(np.abs(x.sum(axis=0) - cols)))
        if error <= tol:
            return x, {"iterations": iteration, "max_margin_error": float(error)}
    raise ValueError("IPF did not converge; no allocation returned")


def controlled_round(expected, row_targets, column_targets):
    """Floor + min-cost bipartite transportation increments, preserving margins.

    The transportation constraints are totally unimodular; HiGHS dual simplex
    gives integral increments for integral deficits. Integrality is checked before
    use. Structural zero cells have upper bound zero. No independent np.round.
    """
    expected = nonnegative(expected, "expectations")
    rows = nonnegative(row_targets, "row targets")
    cols = nonnegative(column_targets, "column targets")
    if (rows % 1).any() or (cols % 1).any() or expected.shape != (len(rows), len(cols)):
        raise ValueError("Integer margins and matching dimensions required")
    if not np.allclose(expected.sum(axis=1), rows, atol=1e-6, rtol=0) or not np.allclose(expected.sum(axis=0), cols, atol=1e-6, rtol=0):
        raise ValueError("Expected matrix does not match margins")
    floor = np.floor(expected).astype(np.int64)
    row_need = rows.astype(np.int64) - floor.sum(axis=1)
    col_need = cols.astype(np.int64) - floor.sum(axis=0)
    if row_need.sum() == 0:
        return floor
    n, m = expected.shape
    indices = np.arange(n * m)
    constraints = coo_matrix((np.ones(2 * n * m),
                              (np.r_[np.repeat(np.arange(n), m), n + np.tile(np.arange(m), n)],
                               np.r_[indices, indices])), shape=(n + m, n * m)).tocsr()
    fractions = (expected - floor).ravel()
    bounds = np.column_stack([np.zeros(n * m), (fractions > 0).astype(float)])
    solution = linprog(1 - 2 * fractions, A_eq=constraints, b_eq=np.r_[row_need, col_need],
                       bounds=bounds, method="highs-ds")
    if not solution.success:
        raise ValueError("Controlled rounding transportation problem failed: " + solution.message)
    increments = np.rint(solution.x)
    if not np.allclose(increments, solution.x, atol=1e-6, rtol=0):
        raise ValueError("Controlled rounding solution is nonintegral")
    result = floor + increments.astype(np.int64).reshape(n, m)
    if not np.array_equal(result.sum(axis=1), rows) or not np.array_equal(result.sum(axis=0), cols):
        raise ValueError("Rounded margins disagree")
    return result


def validate_calendar(weekly):
    required = {"YR", "WN", "DC_QC", "RF_NASA"}
    if not required.issubset(weekly):
        raise ValueError("Missing QC source columns")
    unique_keys(weekly, ["YR", "WN"])
    for col in required:
        nonnegative(weekly[col], col)
    if (weekly.YR % 1).any() or (weekly.WN % 1).any() or (weekly.DC_QC % 1).any():
        raise ValueError("Fractional source years, weeks or counts")
    actual = set(zip(weekly.YR.astype(int), weekly.WN.astype(int)))
    expected = {(y, w) for y in range(int(weekly.YR.min()), int(weekly.YR.max()) + 1) for w in range(1, 53)}
    if actual != expected:
        raise ValueError("Incomplete or invalid 52-block source calendar")
    return weekly.sort_values(["YR", "WN"]).reset_index(drop=True).copy()


def clean_name(value):
    value = str(value).strip()
    try:
        value = value.encode("latin1").decode("utf8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return unicodedata.normalize("NFC", value).casefold()


def reconcile_gis(gis, annual_wide, crosswalk):
    """Project crosswalk only; never invent official identifiers or fuzzy-match."""
    unique_keys(annual_wide, ["ADM4_PCODE"])
    out = gis.copy()
    out["source_barangay_code"] = out.barangay_code
    out["identifier_method"] = "source_code"
    lookup = annual_wide.set_index("ADM4_PCODE").Barangay.map(clean_name).to_dict()
    names = {clean_name(k): v for k, v in crosswalk.items()}
    for i, row in out.iterrows():
        code = row.barangay_code
        if pd.isna(code):
            code = names.get(clean_name(row.barangay_name))
            if code is None:
                raise ValueError("Unresolved GIS identifier: " + row.barangay_name)
            out.loc[i, "barangay_code"] = code
            out.loc[i, "identifier_method"] = "explicit_project_name_crosswalk"
        if code not in lookup or lookup[code] != clean_name(row.barangay_name):
            raise ValueError("GIS code/name disagreement: " + str(code))
    unique_keys(out, ["barangay_code", "year"])
    return out


def zscore(values):
    values = np.asarray(values, dtype=float)
    sd = np.nanstd(values, ddof=0)
    return np.zeros_like(values) if sd == 0 else (values - np.nanmean(values)) / sd


def allocate(annual, settlement, weekly, beta=.5, lag=4):
    """Annual-preserving trial with unknown rows retained and scaled QC margins."""
    unique_keys(annual, ["barangay_code", "year"])
    unique_keys(settlement, ["barangay_code", "year"])
    if not np.isfinite(beta) or abs(beta) > 2 or not isinstance(lag, int) or lag < 0:
        raise ValueError("Use finite |beta| <= 2 and a nonnegative integer lag")
    weekly = validate_calendar(weekly)
    annual = annual.copy()
    if "annual_used" not in annual:
        annual["annual_used"] = annual.annual_cases
    nonnegative(annual.annual_used.dropna(), "annual targets")
    if (annual.annual_used.dropna() % 1).any():
        raise ValueError("Annual targets must be integers")
    merged = annual.merge(settlement, on=["barangay_code", "year"], how="left", validate="one_to_one")
    values = merged.settlement_proportion
    if values.isna().any() or not np.isfinite(values).all() or not values.between(-1e-12, 1 + 1e-12).all():
        raise ValueError("Missing or invalid settlement proportion; review source, do not silently impute")
    if set(merged.year.unique()) != set(weekly.YR.unique()):
        raise ValueError("Annual and weekly years disagree")
    weekly["lagged_rainfall_mm"] = weekly.RF_NASA.shift(lag)
    weekly["rainfall_lag_missing"] = weekly.lagged_rainfall_mm.isna()
    outputs, audits = [], []
    for year, group in merged.groupby("year", sort=True):
        group = group.sort_values("barangay_code").reset_index(drop=True)
        w = weekly.loc[weekly.YR == year].copy()
        known = group.annual_used.notna()
        if not known.any():
            raise ValueError("No known annual demand in year " + str(year))
        rows = group.loc[known, "annual_used"].to_numpy()
        observed = w.DC_QC.to_numpy()
        targets = largest_remainder(observed, int(rows.sum()))
        zs = zscore(group.loc[known, "settlement_proportion"])
        zr = zscore(w.lagged_rainfall_mm)
        zr = np.nan_to_num(zr, nan=0.0)  # neutral interaction, not rainfall imputation
        seed = np.exp(beta * np.outer(zs, zr))
        expected, diag = ipf(seed, rows, targets)
        integer = controlled_round(expected, rows, targets)
        all_expected = np.full((len(group), 52), np.nan)
        all_integer = np.full((len(group), 52), np.nan)
        all_expected[known] = expected
        all_integer[known] = integer
        table = group.loc[group.index.repeat(52)].reset_index(drop=True)
        table["source_week"] = np.tile(w.WN.to_numpy(), len(group))
        table["source_block"] = table.year * 52 + table.source_week - 1
        table["qc_observed_weekly_cases"] = np.tile(observed, len(group))
        table["trial_weekly_target"] = np.tile(targets, len(group))
        table["rainfall_lag_missing"] = np.tile(w.rainfall_lag_missing.to_numpy(), len(group))
        table["synthetic_expected_cases"] = all_expected.ravel()
        table["synthetic_cases"] = pd.array(all_integer.ravel(), dtype="Int64")
        table["scenario_beta"] = beta
        table["rainfall_lag_blocks"] = lag
        table["measurementKind"] = np.where(table.synthetic_cases.isna(), "unknown", "modeled_allocation")
        table["allocation_policy"] = "annual_preserving_scaled_qc_weeks"
        outputs.append(table)
        audits.append({"year": int(year), "annual_total_used": int(rows.sum()),
                       "known_barangays": int(known.sum()), "unknown_barangays": int((~known).sum()),
                       "qc_observed_total": int(observed.sum()), "scaled_weekly_total": int(targets.sum()),
                       "weekly_scale_factor": float(rows.sum() / observed.sum()) if observed.sum() else None,
                       "integer_row_margin_error": int(np.abs(integer.sum(axis=1) - rows).max()),
                       "integer_column_margin_error": int(np.abs(integer.sum(axis=0) - targets).max()), **diag})
    return pd.concat(outputs, ignore_index=True), pd.DataFrame(audits)


def load_inputs(root=ROOT):
    from services.engine.upri_data import load_annual, verify_sources
    root = Path(root)
    verify_sources(root)
    manifest = json.loads((root / "data/reference/weekly_barangay_reconstruction/drive-sources.json").read_text())
    for source in manifest["sources"]:
        if hashlib.sha256((root / source["path"]).read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("Drive source checksum mismatch: " + source["path"])
    wide = load_annual(root / "data/raw/upri_noah/QC_YearlyData-Barangay(CSV).csv")
    annual = wide.melt(id_vars=["ADM4_PCODE", "Barangay"], value_vars=[f"DC_{y}" for y in range(2010, 2026)],
                       var_name="year", value_name="annual_cases").rename(columns={"ADM4_PCODE": "barangay_code", "Barangay": "barangay_name"})
    annual["year"] = annual.year.str[-4:].astype(int)
    crosswalk = json.loads((root / "data/reference/upri_noah/barangay-crosswalk.json").read_text())
    crosswalk = {r["sourceADM4_EN"]: r["ADM4_PCODE"] for r in crosswalk["records"]}
    gis = pd.read_csv(root / "data/raw/gis_settlements/qc_tracker_based_annual_2010_2025.csv")
    gis = reconcile_gis(gis, wide, crosswalk)
    # Keep only the fields needed here. Notebook audits the complete source table.
    gis = gis[["barangay_code", "year", "settlement_proportion", "value_status", "source_barangay_code", "identifier_method"]]
    weekly = pd.read_excel(root / "data/raw/upri_noah/Dengue_Environmental Vars_Dataset.xlsx", sheet_name="QC Data")
    return annual, gis, validate_calendar(weekly)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/weekly_barangay_reconstruction")
    parser.add_argument("--recovery", choices=["none", "count_median", "share_median"], default="none")
    parser.add_argument("--beta", type=float, default=.5)
    parser.add_argument("--lag", type=int, default=4)
    args = parser.parse_args()
    annual, gis, weekly = load_inputs(args.root)
    if args.recovery != "none":
        annual = median_recover(annual, weekly.groupby("YR").DC_QC.sum(), method=args.recovery)
    result, audit = allocate(annual, gis, weekly, beta=args.beta, lag=args.lag)
    result["scenario"] = "source_nulls_preserved" if args.recovery == "none" else args.recovery + "_assumption"
    result["assumptionVersion"] = "weekly-reconstruction-v1"
    result["annual_input_kind"] = np.where(result.annual_cases.notna(), "observed",
                                          np.where(result.annual_used.notna(), "assumption", "unknown"))
    result["units"] = "cases per source block"
    result["geography"] = "Quezon City barangay"
    result["asOf"] = result.year.astype(str) + " source year; publication date unknown"
    args.output.mkdir(parents=True, exist_ok=True)
    data_path = args.output / f"weekly_{args.recovery}.csv.gz"
    audit_path = args.output / f"margins_{args.recovery}.csv"
    result.to_csv(data_path, index=False, float_format="%.12g", compression={"method": "gzip", "mtime": 0})
    audit.to_csv(audit_path, index=False)
    inputs = []
    for filename in ["data/reference/upri_noah/sources.json", "data/reference/weekly_barangay_reconstruction/drive-sources.json"]:
        inputs.extend(json.loads((args.root / filename).read_text())["sources"])
    crosswalk = "data/reference/upri_noah/barangay-crosswalk.json"
    inputs.append({"path": crosswalk, "sha256": hashlib.sha256((args.root / crosswalk).read_bytes()).hexdigest()})
    manifest = {
        "schemaVersion": "1.0", "assumptionVersion": "weekly-reconstruction-v1",
        "measurementKind": "modeled_allocation", "recovery": args.recovery,
        "beta": args.beta, "rainfallLagSourceBlocks": args.lag,
        "policy": "annual_preserving_scaled_qc_weeks", "unknownWeeklyCells": int(result.synthetic_cases.isna().sum()),
        "limitations": ["Retrospective: whole-year and future covariates", "Incompatible annual and city totals; weekly targets are scaled",
                        "Median estimates are assumptions", "Unknown weekly barangay ground truth", "Pre-2016 Tracker values are extrapolated"],
        "inputs": inputs, "codeSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "software": {p: importlib.metadata.version(p) for p in ["numpy", "pandas", "scipy", "openpyxl"]},
        "outputs": [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in [data_path, audit_path]],
    }
    (args.output / f"manifest_{args.recovery}.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    print(audit.to_string(index=False))


if __name__ == "__main__":
    main()
