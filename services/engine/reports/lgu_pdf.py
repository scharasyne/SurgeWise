"""Paginated A4 briefing, using the same summary as the on-screen report."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..domain.lgu_report import display_number, short_date


def briefing_pdf(report):
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, title="Quezon City dengue bed capacity briefing",
                            author="SurgeWise", leftMargin=36, rightMargin=36, topMargin=44, bottomMargin=44)
    teal = colors.HexColor("#215d59")
    ink = colors.HexColor("#233e45")
    soft = colors.HexColor("#eaf2ef")
    styles = {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=ink, spaceAfter=6),
        "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=13, leading=16, spaceBefore=13,
                                  spaceAfter=5, textColor=teal, keepWithNext=True),
        "text": ParagraphStyle("text", fontName="Helvetica", fontSize=9, leading=12, textColor=ink),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8, leading=10, textColor=ink),
        "bold": ParagraphStyle("bold", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=ink),
        "head": ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white),
    }

    def p(value, style="text"):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])

    def table(rows, widths, header=False):
        t = Table(rows, colWidths=[doc.width * w for w in widths], repeatRows=int(header), hAlign="LEFT")
        rules = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, int(header)), (-1, -1), [colors.white, soft]),
                 ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
        if header:
            rules.append(("BACKGROUND", (0, 0), (-1, 0), teal))
        t.setStyle(TableStyle(rules))
        return t

    story = [p("Quezon City dengue bed capacity", "title"),
             p(f'{report["mode"]}  |  {report["window"]}  |  {report["days"]}-day simulation'),
             p("Simulation summary", "section"),
             table([[p(label), p(value, "bold"), p(detail, "small")] for label, value, detail in report["metrics"]],
                   [.43, .16, .41]),
             Spacer(1, 5), p(report["note"], "small"),
             p("Hospitals for follow-up", "section"), p(report["followUp"]), Spacer(1, 6)]
    if report["watchlist"]:
        headings = ["Hospital / status", "First flag / first full", "Days flagged", "Fewest beds left",
                    "Peak beds short", "Peak holding", "Total unplaced"]
        rows = [[p(h, "head") for h in headings]]
        for f in report["watchlist"]:
            full = short_date(f["firstFull"]) if f["firstFull"] else "Never full"
            rows.append([p(f'{f["hospital"]}\n{f["id"]} · {f["status"]}', "bold"),
                         p(f'{short_date(f["firstFlag"])}\n{full}', "small"),
                         *[p(display_number(f[k]), "small") for k in
                           ("daysFlagged", "minimumBeds", "peakShortage", "peakHolding", "totalUnplaced")]])
        story.append(table(rows, [.32, .156, .093, .104, .111, .104, .112], True))
    story.extend([Spacer(1, 6), p(report["definitions"], "small"), p("Scenario settings", "section"),
                  table([[p(k, "bold"), p(v)] for k, v in report["settings"]], [.39, .61]),
                  p("Run record", "section"),
                  p(f'Scenario ID  {report["scenarioId"]}', "small"),
                  p(f'Forecast run  {report["forecastRunId"]}', "small"),
                  p(f'Run timestamp  {report["runTimestamp"]}', "small")])

    def footer(canvas, document):
        canvas.setFillColor(teal)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(36, A4[1] - 27, "SurgeWise   /   Local government briefing")
        canvas.setFont("Helvetica", 8)
        canvas.drawString(36, 23, f'Quezon City  |  Simulation {report["scenarioId"][:12]}')
        canvas.drawRightString(A4[0] - 36, 23, f"Page {document.page}")

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
