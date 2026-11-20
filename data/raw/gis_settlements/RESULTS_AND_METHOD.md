# QC annual mapped settlement dataset, 2010–2025

Completed: 2026-11-18.

The master CSV contains 2,272 unique barangay-year records: 142 barangays for each of 16 years. The wide CSV and GeoPackage contain 142 records, with separate area and percentage fields for every year. Original 2010–2015 measurements are preserved. The 2016–2025 component contains 1,420 records, 10 yearly CSVs, 10 annual GeoTIFFs, a 142-feature GeoPackage and a map preview.

## Main files

- qc_settlement_master_2010_2025.csv: use this long-format table for analysis.
- qc_settlement_master_wide_2010_2025.csv: one row per barangay for spreadsheet comparisons.
- qc_settlement_master_2010_2025.gpkg: same 142 barangay geometries with all 16 years of measurements.
- qc_city_annual_summary_2010_2025.csv: citywide area-weighted summary, not the unweighted mean of barangay percentages.
- data_dictionary.csv: definition of every master-table field.
- product_transition_2015_2016_audit.csv: per-barangay differences across the source change. These differences are NOT validated physical growth/loss.
- master_audit.json: input hashes, software versions and computational checks.

## Material result: source discontinuity

Evolution maps 79.909906% of the supplied QC polygon as settlement in its 2015 row, while Tracker maps 47.980727% in the 2016-labelled row. All 142 barangays have lower mapped areas across that transition. This large discrepancy means raw source values cannot currently support a homogeneous 2010–2025 growth interpretation. No rescaling, interpolation, smoothing or inferred missing settlement was used to hide this break. The combined CSV retains source_product, nominal_resolution_m, snapshot_date, product_transition, and cross_product_harmonized=False.

A real one-year loss is not established by these maps. The products use different sensors, resolutions and methods. Comparable reference/overlap data and a justified harmonization procedure would be needed to establish a continuous measurement scale. Simply adding a source indicator to a model does not itself validate comparability. For modelling, report a sensitivity analysis by product/period before using the combined feature.

## Method

For Evolution, cumulative settlement is positive detection year <= the label year. Existing exact boundary-clipped measurements were verified against the same supplied polygon areas, names and official codes, then retained.

For Tracker, the native GeoZarr group 0 was downloaded only for QC, preserving date indices 0–20. Positive first-detection classes were polygonized in nonoverlapping 256-cell tiles. Every native pixel corner on polygon edges was restored before reprojecting to EPSG:32651. Classes were intersected once with the original barangay geometries. Their nonnegative areas were cumulatively summed to the selected date index. This gives consistent shared edges and avoids repeatedly projecting simplified cumulative outlines. It does not use a pixel-count-times-assumed-area shortcut. Source rasters remain at their native grid; no nearest-neighbour or interpolated harmonization was performed.

Tracker label year y uses codes 1 through 2*(y-2015). Thus label 2016 uses snapshot 2017-01-01 and label 2025 uses snapshot 2026-01-01. These are approximate previous-year-end snapshots, not annual averages. snapshot_date is a nominal measurement cutoff, not a known publication date or evidence of historical operational availability.

Mapped proportion is mapped intersection area / full barangay area. Source zero/background/NoData is excluded from the numerator and does not prove unbuilt or uninhabited land. Observational completeness and classification accuracy are not established by this extraction. Annual raster maps use pixel-centre masking (1 mapped, 0 not mapped including background, 255 outside QC); exact clipped vector measurements in the CSV are authoritative for areas.

## Validation

Independent small synthetic rasters passed partial-cell area, temporal cutoff, future-index exclusion, missing-code preservation and invalid-year/key checks. The full outputs passed 142 unique names per year, complete coverage of years 2010–2025, 2,272 unique keys, finite and consistent measures, 0–100% coverage within floating-point tolerance, fixed boundary areas and name/code matching, nondecreasing area within each source product, preserved prior Evolution measurements, and 142-row GeoPackage readback. Tiny values such as 100.00000000000009 reflect floating-point roundoff, not meaningful excess coverage.

The initial repeated-outline calculation triggered the within-product consistency check. It was replaced with the date-class area ledger described above, then tests and the full extraction were rerun. Failed intermediate tables are not delivered as results. This is a numerical/computational validation, not ground-truth validation of either satellite product or any dengue relationship.

## Boundaries and missing data

The same supplied QC-Brgy polygons are applied to all years. Historical barangay boundary changes are not reconstructed. Official codes for Doña Imelda and Doña Josefa are missing in the original boundary file and remain missing (32 master rows); the original unique barangay name is the within-layer join key. No dengue cases are copied into the master or imputed.

## Reuse

The runnable Python pipeline, pinned dependencies, optional native-resolution download script, tests and commands are in 03_Pipeline/Annual_2010_2025_Pipeline. Extraction and integration run from local input files in one command; they do not require manual QGIS processing. Drive uploads were completed separately with the connected account; no credentials are embedded in the scripts.

The master contains retrospective settlement extents, not settlement-to-dengue weights or synthetic weekly dengue counts. End-of-year predictors can leak future information when used for earlier weeks. See INTERPRETATION.md for implications for the proposed weekly allocation.

## Primary sources

- https://source.coop/mindearth/wsf (Tracker date-index model, native group, background caveat)
- https://worldsettlementfootprint.com/raster-download (official access instructions)
- https://doi.org/10.5281/zenodo.20424537 (Tracker dataset DOI)
- https://geoservice.dlr.de/web/dataguide/wsf-evolution/ (Evolution documentation)

Cite DLR WSF Evolution for 2010–2015 and WSF Tracker with MindEarth/DLR attribution for 2016–2025.

Verdict: feasible with modifications. The master is a combined source-labelled annual extent dataset; a homogeneous 2010–2025 growth series has not been established.

## City summary

Year | Product | Mapped settlement km² | QC area mapped (%)
--- | --- | ---: | ---:
2010 | WSF Evolution v1 | 129.376635 | 79.623930
2011 | WSF Evolution v1 | 129.449086 | 79.668520
2012 | WSF Evolution v1 | 129.591687 | 79.756283
2013 | WSF Evolution v1 | 129.672643 | 79.806106
2014 | WSF Evolution v1 | 129.722076 | 79.836530
2015 | WSF Evolution v1 | 129.841302 | 79.909906
2016 | WSF Tracker GeoZarr | 77.961299 | 47.980727
2017 | WSF Tracker GeoZarr | 78.592672 | 48.369301
2018 | WSF Tracker GeoZarr | 79.157399 | 48.716859
2019 | WSF Tracker GeoZarr | 79.647419 | 49.018438
2020 | WSF Tracker GeoZarr | 79.940948 | 49.199088
2021 | WSF Tracker GeoZarr | 80.252664 | 49.390931
2022 | WSF Tracker GeoZarr | 80.512769 | 49.551011
2023 | WSF Tracker GeoZarr | 80.600018 | 49.604708
2024 | WSF Tracker GeoZarr | 80.736557 | 49.688740
2025 | WSF Tracker GeoZarr | 80.806143 | 49.731566
