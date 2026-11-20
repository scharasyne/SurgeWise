# QC annual settlement mapping — start here

Completed 2010–2025: 142 barangays per year, 2,272 unique barangay-year rows.

## Main deliverables

- [Master annual CSV, 2010–2025](https://drive.google.com/file/d/1A5CN8wy8rkuRvf03TSYlhu9swVt4dkvw/view)
- [Complete downloadable bundle](https://drive.google.com/file/d/19H_7qYkXvA-YziBrPP1hP5c1-gNJUCY8/view)
- [Master results, GIS, audits and methodology](https://drive.google.com/drive/folders/1k0qvRaT-3xJcosZcR-qdn0EkS-QJWR4u)
- [2016–2025 yearly CSVs, maps and quality files](https://drive.google.com/drive/folders/1gduWHLr2yt50JeNAGxWVhm9__JyBXBiy)
- [2010–2015 original completed results](https://drive.google.com/drive/folders/1ExgxIAxra7Pjdy4cC2OzGSp9n6Gfq3Zg)
- [Reusable pipeline, download script, tests and commands](https://drive.google.com/drive/folders/1Zbc35RqoMOu0JuMHhkQZTUEuuf9IU-Rd)

## Read before modelling

The master joins WSF Evolution (2010–2015) with WSF Tracker (2016–2025). It retains source, nominal resolution and snapshot date. QC mapped coverage differs substantially at the product change: 79.91% in Evolution's 2015 row versus 47.98% in Tracker's 2016-labelled row. These values do not establish a real one-year settlement loss, and the products have NOT been harmonized. The combined table must not be treated as a homogeneous growth series.

Tracker rows use following-January-1 snapshots as approximate previous-year-end values, not annual averages or measurements known at the start of the year. The same supplied barangay boundaries are used for all years. Missing source codes for Doña Imelda and Doña Josefa remain missing. No dengue counts are generated or imputed by this pipeline.

01_Source_Data preserves original inputs, including the new Tracker subset. 03_Pipeline includes the original pipeline and the new all-years integration pipeline. 90_Manual_Work_Archive preserves earlier manual intermediates; it is not the final dataset. Existing local QGIS file paths are not automatically rewritten when Drive files are organized.


## Additional scenario: Tracker-only backward extrapolation

[06_Tracker_Backcast_2010_2025](https://drive.google.com/drive/folders/1y42OwLhgW9v1HgemiPk3Ucpv-q51oUkJ) contains a separate scenario using the 2016–2025 Tracker trend to estimate 2010–2015. It preserves all 1,420 satellite-derived Tracker rows and adds 852 explicitly labelled extrapolated estimates. The original master above is unchanged.

- [Tracker-based scenario CSV](https://drive.google.com/file/d/1QUDwjiMMfRFQ4iLwEu_k-0bsEmVkTXR-/view?usp=drivesdk)
- [Scenario bundle with pipeline, yearly CSVs, GIS and backtests](https://drive.google.com/file/d/1nHOvDx5-Z4Yyf5ueR_UhsduOHWXJ_IlV/view?usp=drivesdk)

The anchored per-barangay linear trend had pooled within-Tracker backward-test MAE 0.417623 percentage points versus 0.491619 for a constant carry-back. This does not validate actual pre-2016 accuracy. These retrospective estimates use later information and cannot be presented as observed historical satellite pixels or as features available for real-time forecasts in the past.

