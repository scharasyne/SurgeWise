"""Join a reviewed QC flood evidence inventory to UPRI source weeks."""
import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from itertools import product
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.engine.domain.source_calendar import block_days, block_start, source_week
from services.engine.upri_data import WORKBOOK, load_weekly, sha256

YEARS = range(2010, 2026)
WEEKS = range(1, 53)
REPORT_COLUMNS = (
    "report_id", "event_date", "published_date", "source_type", "publisher",
    "url", "location", "evidence", "verification_url",
)
SOURCE_TYPES = {"news", "official", "social"}
REPORTS = ROOT / "data/reference/upri_noah/qc-flood-reports.csv"
PROCESSED = ROOT / "data/processed/upri_noah"
FLAG = "reported_qc_flood_provisional"


def read_reports(path):
    reports = []
    seen_ids = set()
    seen_reports = set()
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != REPORT_COLUMNS:
            raise ValueError("Flood report inventory schema mismatch")
        for line, report in enumerate(reader, start=2):
            if None in report or any(report[key] is None for key in REPORT_COLUMNS):
                raise ValueError(f"Malformed report on line {line}")
            for key in REPORT_COLUMNS:
                report[key] = report[key].strip()
            for key in ("event_date", "published_date"):
                value = report[key]
                if value and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError(f"Invalid {key} on line {line}: {value}")
                report[key] = date.fromisoformat(value) if value else None
            event = report["event_date"]
            published = report["published_date"]
            if event and event.year not in YEARS:
                raise ValueError(f"Event date outside study period on line {line}")
            if event and published and event > published:
                raise ValueError(f"Report publication precedes observation on line {line}")
            for value in (report["url"], report["verification_url"] or report["url"]):
                url = urlsplit(value)
                if url.scheme not in {"https", "http"} or not url.hostname:
                    raise ValueError(f"Invalid source URL on line {line}")
            if report["source_type"] not in SOURCE_TYPES or not all(
                report[key] for key in ("report_id", "publisher", "location", "evidence")
            ):
                raise ValueError(f"Missing or invalid evidence metadata on line {line}")
            evidence_key = (event, report["url"])
            if report["report_id"] in seen_ids or evidence_key in seen_reports:
                raise ValueError(f"Duplicate report on line {line}")
            seen_ids.add(report["report_id"])
            seen_reports.add(evidence_key)
            reports.append(report)
    if not reports:
        raise ValueError("The flood report inventory is empty")
    return reports


def validate_source_blocks(observed):
    expected = list(product(YEARS, WEEKS))
    if list(observed[["YR", "WN"]].itertuples(index=False, name=None)) != expected:
        raise ValueError("QC workbook must contain each 2010–2025 source block in order")


def align_evidence(observed, reports):
    by_block = defaultdict(list)
    for report in reports:
        event = report["event_date"]
        if event:
            by_block[event.year, source_week(event)].append(report)

    evidence = []
    for year, week in observed[["YR", "WN"]].itertuples(index=False, name=None):
        year, week = int(year), int(week)
        block = by_block[year, week]
        start = block_start(year, week)
        end = start + timedelta(days=block_days(year, week) - 1)
        documented_days = {report["event_date"] for report in block}
        types = {report["source_type"] for report in block}
        confirmed = bool(types & {"official", "news"})
        status = "official_or_news" if confirmed else (
            "social_only" if block else "no_recovered_report"
        )
        evidence.append({
            "provisional_block_start": start.isoformat(),
            "provisional_block_end": end.isoformat(),
            "flood_evidence_status": status,
            FLAG: 1 if confirmed else None,
            "flood_dated_report_count": len(block),
            "flood_documented_day_count": len(documented_days),
            "flood_iso_disagreement_day_count": sum(
                day.isocalendar()[:2] != (year, week) for day in documented_days
            ),
            "flood_source_types": "|".join(sorted(types)),
            "flood_report_ids": "|".join(sorted(report["report_id"] for report in block)),
        })

    weekly = pd.DataFrame(evidence, index=observed.index)
    weekly[FLAG] = weekly[FLAG].astype("Int64")
    return pd.concat([observed, weekly], axis=1)


def manifest(reports, aligned, workbook, inventory, output):
    source_catalog = ROOT / "data/reference/upri_noah/sources.json"
    workbook_hash = sha256(workbook)
    source = next(
        (item for item in json.loads(source_catalog.read_text())["sources"]
         if item["sha256"] == workbook_hash),
        {},
    )
    coverage = {
        str(int(year)): frame.flood_evidence_status.value_counts().sort_index().to_dict()
        for year, frame in aligned.groupby("YR")
    }
    workbook_columns = list(aligned.columns[:aligned.columns.get_loc("provisional_block_start")])
    return {
        "schema_version": 1,
        "transform": {"file": Path(__file__).name, "sha256": sha256(__file__)},
        "geography": "Quezon City, Philippines",
        "source_workbook": {
            "file": workbook.name,
            "sheet": "QC Data",
            "sha256": workbook_hash,
            "url": source.get("sourceUrl"),
            "license": "ODC-ODbL-1.0 (source README)" if source else None,
            "columns": workbook_columns,
        },
        "report_inventory": {
            "file": inventory.name,
            "sha256": sha256(inventory),
            "columns": list(REPORT_COLUMNS),
            "records": len(reports),
            "sources_by_type": dict(sorted(
                pd.Series([report["source_type"] for report in reports]).value_counts().items()
            )),
            "undated_records_excluded_from_weekly_join": sum(
                report["event_date"] is None for report in reports
            ),
            "licensing": "Source URLs and original summaries only. Publishers retain source rights.",
        },
        "weekly_output": {
            "file": output.name,
            "sha256": sha256(output),
            "columns": list(aligned.columns),
            "weeks": len(aligned),
            "coverage_by_year": coverage,
            "iso_disagreement_days": int(aligned.flood_iso_disagreement_day_count.sum()),
        },
        "alignment": {
            "calendar": "Provisional Jan 1 blocks, last block ends December 31",
            "date_field": "event_date, never filled with publication date",
            "positive": "At least one dated official or news flood observation in the block",
            "missing": "Social-only evidence or no recovered dated evidence",
            "archive_coverage": "Unmeasured; missing evidence cannot identify flood-free weeks.",
            "use": "Retrospective evidence audit; report availability and week boundaries remain unresolved.",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=WORKBOOK)
    parser.add_argument("--reports", type=Path, default=REPORTS)
    parser.add_argument("--output", type=Path, default=PROCESSED / "qc-flood-weekly-evidence.csv")
    parser.add_argument("--manifest", type=Path, default=PROCESSED / "qc-flood-weekly-evidence-manifest.json")
    args = parser.parse_args()

    paths = {path.resolve() for path in (args.workbook, args.reports, args.output, args.manifest)}
    if len(paths) != 4:
        parser.error("Workbook, inventory, weekly CSV and manifest paths must be distinct")

    reports = read_reports(args.reports)
    observed, _, _ = load_weekly("QUEZON_CITY", args.workbook)
    validate_source_blocks(observed)
    aligned = align_evidence(observed, reports)
    aligned.to_csv(args.output, index=False, lineterminator="\n")
    metadata = manifest(reports, aligned, args.workbook, args.reports, args.output)
    args.manifest.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
