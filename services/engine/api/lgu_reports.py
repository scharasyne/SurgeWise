"""Read-only reports for an existing, provenance-checked simulation."""
from fastapi import APIRouter, HTTPException, Response
from typing import Literal

from .outbreak import saved_movie
from ..domain.lgu_report import daily_records, report_csv, report_summary

router = APIRouter(prefix="/v1")


@router.get("/outbreak-scenarios/{ident}/report.{format}")
def lgu_report(ident: str, format: Literal["json", "pdf", "csv"]):
    movie = saved_movie(ident)
    try:
        records = list(daily_records(movie))
        if format == "csv":
            content, mime = report_csv(records), "text/csv"
        else:
            report = report_summary(movie, records)
            if format == "json":
                return report
            from ..reports.lgu_pdf import briefing_pdf
            content, mime = briefing_pdf(report), "application/pdf"
    except (ValueError, KeyError, TypeError, IndexError):
        raise HTTPException(503, detail={"message": "This saved run has incomplete hospital records. Run the simulation again to generate a report."}) from None
    filename = f'qc-dengue-{movie["parameters"]["startDate"]}-{ident[:12]}.{format}'
    return Response(content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
