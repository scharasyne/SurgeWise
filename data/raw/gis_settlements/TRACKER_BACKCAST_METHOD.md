# Tracker-based annual settlement estimation scenario, 2010–2025

This separate scenario uses only WSF Tracker annual aggregates from 2016–2025 to estimate 2010–2015. The original Evolution/Tracker master remains unchanged. No Evolution values influence the estimates; they appear only in a comparison CSV.

## Main dataset

qc_tracker_based_annual_2010_2025.csv contains 2,272 rows: 142 barangays × 16 years.

- 2010–2015: 852 modelled estimates, value_status=extrapolated_estimate.
- 2016–2025: 1,420 preserved satellite-derived measurements, value_status=satellite_derived.
- 32 rows retain missing official codes for Doña Imelda and Doña Josefa.
- No bounds were applied in practice: all estimated proportions were already in [0,1].

These are barangay aggregate areas/proportions, NOT reconstructed historical settlement pixels. The GeoPackage supports barangay-level choropleths. It cannot tell which specific buildings or land parcels existed in 2010–2015.

## Estimation method, fixed before backtest evaluation

Fit a separate ordinary least-squares slope to each barangay's 10 annual Tracker proportions (label years 2016–2025). Retain that slope, but anchor the extrapolation to the actual earliest annual value, p2016, rather than replacing observed values with the fitted regression line:

p_estimated(y) = clip[p2016 + slope × (y − 2016), 0, 1], for y = 2010,...,2015.

The nonnegative slope is in proportion per year; the parameter table also supplies percentage points per year. Area is estimated proportion × the same supplied full barangay area. The bound is a physical constraint; it is recorded if triggered (zero estimates triggered it here). All actual 2016–2025 areas, proportions and percentages remain numerically unchanged.

Assumptions: the later linear growth rate is informative about earlier development; the cumulative classification is a useful mapped-extent measure; the same supplied QC boundary geography is usable across years. These assumptions do not reconstruct demolition, historical boundary changes, occupancy, population or dengue exposure.

## Dates

The annual Tracker table uses following-January-1 snapshots. The 2016 anchor is therefore the snapshot 2017-01-01, not a measurement from the start of 2016. The 2025 row represents snapshot 2026-01-01; no full-year 2026 observation was used.

For estimated rows, target_date is the analogous following January 1 and actual_snapshot_date is blank because no Tracker snapshot exists there. All estimates use future information relative to 2010–2015. This is a retrospective scenario and must not be presented as a covariate available for a historical real-time forecast. Forecast experiments require an explicit feature-availability policy and evaluation that acknowledges this reconstruction.

## Backward prediction checks

Four predeclared folds fit only later Tracker years, then predict withheld earlier Tracker years:

Training period | Withheld label years | Purpose
--- | --- | ---
2019–2025 | 2016–2018 | 1–3-year backward prediction
2020–2025 | 2016–2019 | 1–4-year backward prediction
2021–2025 | 2016–2020 | 1–5-year backward prediction
2022–2025 | 2016–2021 | 1–6-year backward prediction

The comparator holds the earliest training-period value constant for all earlier withheld years. Both methods use the same training/withheld splits. The pooled mean absolute error is 0.417623 percentage points for anchored linear extrapolation versus 0.491619 for constant carry-back. The linear method is better on aggregate in all four folds. It has lower pooled per-barangay error for 95 of 142 barangays; it does not improve every barangay.

Backtest folds overlap, so their 2,556 prediction errors are not independent observations. These are descriptive within-Tracker errors, not a calibrated confidence interval or proof of actual pre-2016 accuracy. Historical urbanization can differ from the later trend. No claim is made that the method predicts dengue better. The original 2010–2015 Evolution values have different measurement scales and are not used as direct ground truth for this scenario.

The constant_2016_sensitivity_percent field supplies an alternative historical scenario. The difference between this and the linear estimate illustrates model-choice sensitivity; it does not cover all historical uncertainty.

## Quality checks

The known-slope synthetic test, flat-series test, negative-bound test, observed-anchor check and target-year guard passed. Full outputs passed 2,272 unique keys; 142 barangays per year; finite, bounded and consistent proportions/areas; nondecreasing values; exact preservation of the 2016–2025 input values; and 142-feature GeoPackage readback. audit.json records the input checksum and numerical results.

## Files

- qc_tracker_based_annual_2010_2025.csv: main long-format dataset.
- qc_extrapolated_2010_2015.csv: only the 852 new estimates.
- Annual_CSV/: 16 yearly CSVs.
- qc_city_tracker_based_annual.csv: area-weighted city totals.
- barangay_trend_parameters.csv: slopes, anchors and bounds diagnostics.
- backtest_summary.csv, backtest_by_horizon.csv, backtest_by_barangay.csv and backtest_predictions.csv: test outcomes and individual predictions.
- original_evolution_vs_estimates.csv: preserved-source comparison only, not validation.
- qc_tracker_based_annual.gpkg: 142 polygons with annual percentages.
- tracker_backcast_city.png: dashed estimated segment and solid satellite-derived segment.
- Pipeline/: code, tests, pinned dependencies and commands.

## Scientific interpretation

Using one source family avoids directly concatenating the incompatible Evolution and Tracker percentages, but replaces six years with model assumptions. A smooth series alone is not evidence that the estimates are accurate. Keep the status flag when joining this environmental input to dengue data. Settlement extent alone does not establish breeding habitat or a settlement-to-dengue coefficient.

Verdict: feasible with modifications as a labelled retrospective estimation scenario. Actual 2010–2015 Tracker-scale settlement extent remains unvalidated.

## Provider documentation

WSF Tracker date indices, native resolution and zero/background caveat: https://source.coop/mindearth/wsf
Official access: https://worldsettlementfootprint.com/raster-download
Dataset DOI: https://doi.org/10.5281/zenodo.20424537
Credit MindEarth / DLR. The extrapolation is our modelling step, not a provider-supplied historical Tracker product.
