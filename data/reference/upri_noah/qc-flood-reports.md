# Quezon City flood report inventory, 2010–2025

This public-source collection records documented flooding within Quezon City. Search and review took place on 17 November 2026 (Philippine time). The inventory has dated observations for each year from 2010 to 2025. News archive availability, social-post retention, and the geographic coverage of monitoring vary over time. There is no verified measure of archive completeness.

## Finding and reviewing reports

- Searches covered individual years, named storms and monsoon episodes, and recurring locations such as Araneta Avenue and the Aurora Boulevard tunnel. Queries combined “Quezon City” or named roads with “flood,” “flooding,” “baha,” and “MMDA.” Sources included city road updates, national situation reports, news archives, and indexed public posts.
- Include a report when it documents actual floodwater or direct flood impacts in Quezon City. A flood warning, heavy rain, or preemptive evacuation alone does not establish an observation. Reports about Quezon Province or unclear city boundaries were excluded.
- `event_date` records the observation day in the Philippines. `published_date` records the publication day when available. Leave uncertain dates blank and describe the known period in `evidence`. Reports without an exact observation date remain in the inventory and are excluded from the weekly join.
- Each row links to one source for an observation date. Multiple sources may describe the same flood. Source and day counts describe the evidence collected. A linked `verification_url` preserves a parent article for social posts available through its embeds. Some legacy articles were reviewed through public search excerpts when their original page was inaccessible.
- MMDA approved requests for historical records and indicated private delivery. Those records were unavailable in this collection. MapaKalamidad documents a public archive endpoint, but no usable extract was obtained. These sources cannot establish coverage for the unobserved weeks. [MMDA 2010–2024 records request](https://www.foi.gov.ph/agencies/mmda/the-list-of-floods-in-metro-manila-from-2010-to-2024/), [MMDA 2015–2025 records request](https://www.foi.gov.ph/agencies/mmda/history-of-flood-reports-in-metro-manila-20152025/), [MapaKalamidad archive documentation](https://docs.mapakalamidad.ph/routes/reportsarchive)

The inventory contains URLs, source metadata, and original summaries. The source publishers retain rights to the underlying articles, photos, and videos. The workbook is pinned in `sources.json` under the upstream ODC-ODbL-1.0 declaration.

## Weekly alignment

The script preserves all 832 rows and all original fields from the workbook's `QC Data` sheet, including dengue counts and NASA rainfall. It links reports by `event_date` to the workbook's `YR` and `WN` using SurgeWise's existing provisional calendar. Blocks start January 1, and block 52 ends December 31. The workbook documents conflicting week conventions. The weekly output includes inclusive block dates and counts of distinct reported observation days whose ISO year or week differ from this mapping.

| Weekly evidence status | `reported_qc_flood_provisional` |
| --- | --- |
| `official_or_news` | `1` if at least one dated government or news source reports observed flooding |
| `social_only` | Blank. The recovered evidence is limited to dated public social posts |
| `no_recovered_report` | Blank. Flood status is unknown |

Use `flood_report_ids` to look up the dated source records. Zero in `flood_dated_report_count` or `flood_documented_day_count` describes the available evidence. This inventory has no verified flood-free weeks.

Carvajal et al. used MMDA social alerts cross-checked with news to identify weeks when widespread flooding made almost every major Metro Manila road impassable. This collection captures documented flooding at any qualifying QC location. An equivalent severity measure would require an agreed set of major QC roads and documented monitoring coverage. The date mapping and report availability at forecast issue time also require verification before use in a forecast. [Carvajal et al., flood data methods](https://link.springer.com/article/10.1186/s12879-018-3066-0#Sec2)

## Rebuild

From the SurgeWise repository root, use the existing virtual environment:

```bash
.venv/bin/python scripts/align_qc_flood_reports.py
```

The script reads `data/reference/upri_noah/qc-flood-reports.csv` and the pinned workbook. It writes `data/processed/upri_noah/qc-flood-weekly-evidence.csv` and the accompanying JSON manifest with hashes, input schemas, and counts by year.
