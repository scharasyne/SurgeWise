"""Synthetic QC flood-report and weekly dengue fixtures."""
from datetime import date

import pandas as pd
import pytest

from scripts.align_qc_flood_reports import align_evidence, read_reports, validate_source_blocks


def test_unknown_weeks_social_only_and_late_reports():
    observed = pd.DataFrame({"YR": [2010] * 3, "WN": [1, 2, 3], "DC_QC": [12, 14, 9]})
    reports = [
        {"report_id": "r1", "event_date": date(2010, 1, 1), "source_type": "news"},
        {"report_id": "r2", "event_date": date(2010, 1, 1), "source_type": "official"},
        {"report_id": "r3", "event_date": date(2010, 1, 8), "source_type": "social"},
        {"report_id": "r4", "event_date": None, "source_type": "news"},
    ]

    aligned = align_evidence(observed, reports)

    pd.testing.assert_frame_equal(aligned[observed.columns], observed)
    assert aligned.flood_evidence_status.tolist() == [
        "official_or_news", "social_only", "no_recovered_report"
    ]
    assert aligned.reported_qc_flood_provisional.iloc[0] == 1
    assert aligned.reported_qc_flood_provisional.iloc[1:].isna().all()
    assert aligned.flood_report_ids.tolist() == ["r1|r2", "r3", ""]
    assert aligned.flood_dated_report_count.tolist() == [2, 1, 0]
    assert aligned.flood_documented_day_count.tolist() == [1, 1, 0]
    assert aligned.flood_iso_disagreement_day_count.tolist() == [1, 1, 0]


def test_leap_year_tail_stays_in_source_block_52():
    observed = pd.DataFrame({"YR": [2024, 2025], "WN": [52, 1]})
    reports = [{"report_id": "r1", "event_date": date(2024, 12, 31), "source_type": "news"}]

    aligned = align_evidence(observed, reports)

    assert aligned.provisional_block_start.tolist() == ["2024-12-23", "2025-01-01"]
    assert aligned.provisional_block_end.tolist() == ["2024-12-31", "2025-01-07"]
    assert aligned.flood_report_ids.tolist() == ["r1", ""]


def test_invalid_or_missing_source_blocks():
    observed = pd.DataFrame({"YR": [2010, 2010, 2010], "WN": [1, 2, 2]})
    with pytest.raises(ValueError, match="2010–2025"):
        validate_source_blocks(observed)


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        ("r1,2010-01-01,2009-12-31,news,Test News,https://example.test/qc,QC,Reported flooding",
         "publication precedes"),
        ("r1,2010-01-01,,news,Test News,not-a-url,QC,Reported flooding", "source URL"),
        ("r1,2010-01-01,,news,Test News,https://example.test/qc,QC,Reported flooding\n"
         "r2,2010-01-01,,news,Test News,https://example.test/qc,QC,Reported flooding",
         "Duplicate report"),
    ],
)
def test_report_validation(tmp_path, data, reason):
    path = tmp_path / "fixture.csv"
    columns = ("report_id,event_date,published_date,source_type,publisher,url,"
               "location,evidence,verification_url")
    rows = "".join(f"{line},\n" for line in data.splitlines())
    path.write_text(columns + "\n" + rows, encoding="utf-8")
    with pytest.raises(ValueError, match=reason):
        read_reports(path)
