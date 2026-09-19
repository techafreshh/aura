"""Styled PDF export of an interview report.

The PDF is the artifact recruiters and candidates download and the one
archived to MinIO, so it is built as a real document — vector text, wrapped
paragraphs, section meters — rather than a screenshot of the web dashboard.
All LLM-derived strings pass through escape() so they cannot inject ReportLab
markup, and every free-text block is a Paragraph so long content wraps instead
of overflowing the page.
"""

import io
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth as pdfmetrics_stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from models.schemas import FinalReport

# Palette — light theme with Aura's indigo accent.
_INK = colors.HexColor("#18181B")
_MUTED = colors.HexColor("#52525B")
_FAINT = colors.HexColor("#A1A1AA")
_BORDER = colors.HexColor("#E4E4E7")
_SOFT = colors.HexColor("#F4F4F5")
_ACCENT = colors.HexColor("#4F46E5")
_ACCENT_SOFT = colors.HexColor("#EEF2FF")
_GREEN = colors.HexColor("#15803D")
_GREEN_SOFT = colors.HexColor("#DCFCE7")
_AMBER = colors.HexColor("#B45309")
_AMBER_SOFT = colors.HexColor("#FEF3C7")
_RED = colors.HexColor("#B91C1C")
_RED_SOFT = colors.HexColor("#FEE2E2")

_RECOMMENDATION_COLORS = {
    "Strong Hire": (_GREEN, _GREEN_SOFT),
    "Hire": (_GREEN, _GREEN_SOFT),
    "Hold": (_AMBER, _AMBER_SOFT),
    "No Hire": (_RED, _RED_SOFT),
}

_MARGIN = 18 * mm
_CONTENT_WIDTH = A4[0] - 2 * _MARGIN


def _base_styles() -> dict[str, ParagraphStyle]:
    helvetica = "Helvetica"
    return {
        "eyebrow": ParagraphStyle("eyebrow", fontName=helvetica, fontSize=8, leading=11,
                                  textColor=_ACCENT, spaceAfter=2),
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=24, leading=29,
                                textColor=_INK),
        "meta": ParagraphStyle("meta", fontName=helvetica, fontSize=9, leading=13,
                               textColor=_MUTED),
        "brand": ParagraphStyle("brand", fontName="Helvetica-Bold", fontSize=13, leading=16,
                                textColor=_INK, alignment=TA_RIGHT),
        "brand-sub": ParagraphStyle("brand-sub", fontName=helvetica, fontSize=8, leading=11,
                                    textColor=_FAINT, alignment=TA_RIGHT),
        "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=12, leading=15,
                                  textColor=_INK, spaceBefore=14, spaceAfter=6),
        "subhead": ParagraphStyle("subhead", fontName="Helvetica-Bold", fontSize=10.5, leading=14,
                                  textColor=_INK, spaceAfter=4),
        "body": ParagraphStyle("body", fontName=helvetica, fontSize=10, leading=15,
                               textColor=_MUTED),
        "bullet": ParagraphStyle("bullet", fontName=helvetica, fontSize=10, leading=15,
                                 textColor=_MUTED, leftIndent=12, bulletIndent=2, spaceAfter=3),
        "score-num": ParagraphStyle("score-num", fontName="Helvetica-Bold", fontSize=34, leading=38,
                                    textColor=_INK, alignment=TA_RIGHT),
        "score-denom": ParagraphStyle("score-denom", fontName=helvetica, fontSize=11, leading=14,
                                      textColor=_FAINT, alignment=TA_RIGHT),
        "cell": ParagraphStyle("cell", fontName=helvetica, fontSize=9.5, leading=13,
                               textColor=_MUTED),
        "cell-strong": ParagraphStyle("cell-strong", fontName="Helvetica-Bold", fontSize=9.5,
                                      leading=13, textColor=_INK),
        "cell-score": ParagraphStyle("cell-score", fontName="Helvetica-Bold", fontSize=9.5,
                                     leading=13, textColor=_INK, alignment=TA_RIGHT),
        "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, leading=10,
                             textColor=colors.white),
        "th-r": ParagraphStyle("th-r", fontName="Helvetica-Bold", fontSize=8, leading=10,
                               textColor=colors.white, alignment=TA_RIGHT),
        "footer": ParagraphStyle("footer", fontName=helvetica, fontSize=8, leading=10,
                                 textColor=_FAINT),
    }


class _ScoreMeter(Flowable):
    """A slim horizontal bar filled to score/10, drawn in the section table."""

    def __init__(self, score: int, width: float, height: float = 5):
        super().__init__()
        self.score = max(0, min(10, score))
        self.width = width
        self.height = height

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(_SOFT)
        c.roundRect(0, 0, self.width, self.height, self.height / 2, stroke=0, fill=1)
        fill_w = self.width * (self.score / 10.0)
        if fill_w > 0:
            c.setFillColor(_ACCENT)
            c.roundRect(0, 0, fill_w, self.height, self.height / 2, stroke=0, fill=1)


class _RecommendationPill(Flowable):
    """Rounded pill with the hiring recommendation, sized to its label."""

    PAD_X = 10
    HEIGHT = 20

    def __init__(self, recommendation: str):
        super().__init__()
        self.recommendation = recommendation
        fg, bg = _RECOMMENDATION_COLORS.get(recommendation, (_MUTED, _SOFT))
        self.fg, self.bg = fg, bg
        self.label_width = pdfmetrics_stringWidth(
            recommendation.upper(), "Helvetica-Bold", 9
        ) if recommendation else 30

    def wrap(self, availWidth, availHeight):
        self.width = self.label_width + 2 * self.PAD_X
        self.height = self.HEIGHT
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(self.bg)
        c.roundRect(0, 0, self.width, self.height, self.height / 2, stroke=0, fill=1)
        c.setFillColor(self.fg)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(self.width / 2, (self.height - 9) / 2 + 2, self.recommendation.upper())


def _score_block(report: FinalReport, styles: dict[str, ParagraphStyle]) -> Table:
    """Right-hand summary: big score and the recommendation pill."""
    pill = _RecommendationPill(report.recommendation)
    block = Table(
        [[
            Paragraph(
                f"{report.overall_score}<font size=11 color='#A1A1AA'> / 100</font>",
                styles["score-num"],
            ),
            pill,
        ]],
        colWidths=[_CONTENT_WIDTH * 0.62 * 0.45, _CONTENT_WIDTH * 0.62 * 0.55],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
        hAlign="LEFT",
    )
    return block


def _identity_block(report: FinalReport, styles: dict[str, ParagraphStyle]) -> Table:
    """Left-hand card: avatar initials, candidate name, and modality meta lines."""
    initials = "".join(w[0] for w in report.candidate_name.split()[:2]).upper() or "C"
    avatar = Table(
        [[Paragraph(initials, ParagraphStyle(
            "avatar", fontName="Helvetica-Bold", fontSize=14, leading=17,
            textColor=_ACCENT, alignment=1,
        ))]],
        colWidths=[34],
        rowHeights=[34],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _ACCENT_SOFT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]),
    )
    identity = [
        Paragraph(escape(report.candidate_name),
                  ParagraphStyle("cand", fontName="Helvetica-Bold", fontSize=14, leading=18,
                                 textColor=_INK)),
        Paragraph("Candidate · Voice interview", styles["meta"]),
        Spacer(1, 4),
        Paragraph("Conducted by Aura, the AI interviewer", styles["meta"]),
    ]
    card = Table(
        [[avatar, identity]],
        colWidths=[44, _CONTENT_WIDTH * 0.38 - 44],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
            ("RIGHTPADDING", (0, 0), (0, 0), 10),
            ("LEFTPADDING", (1, 0), (1, 0), 0),
            ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]),
        hAlign="LEFT",
    )
    return card


def _section_table(report: FinalReport, styles: dict[str, ParagraphStyle]) -> Table:
    meter_width = 60
    header = [
        Paragraph("SECTION", styles["th"]),
        Paragraph("SCORE", styles["th-r"]),
        Paragraph("ASSESSMENT", styles["th"]),
    ]
    rows = [header]
    for g in report.section_grades:
        rows.append([
            Paragraph(escape(g.section_name), styles["cell-strong"]),
            _ScoreMeter(g.score, meter_width),
            Paragraph(escape(g.comments), styles["cell"]),
        ])
    table = Table(
        rows,
        colWidths=[
            _CONTENT_WIDTH * 0.22,
            _CONTENT_WIDTH * 0.18,
            _CONTENT_WIDTH - _CONTENT_WIDTH * 0.40,
        ],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("VALIGN", (1, 1), (1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, _BORDER),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _SOFT]),
    ]))
    return table


def _header_block(report: FinalReport, styles: dict[str, ParagraphStyle]) -> list:
    # Zero-padded %d renders "Sep 05"; drop the leading zero when present.
    generated = date.today().strftime("%b %d, %Y").replace(" 0", " ")

    left = [
        Paragraph("INTERVIEW REPORT", styles["eyebrow"]),
        Paragraph(escape(report.candidate_name), styles["title"]),
        Spacer(1, 4),
        Paragraph(f"Voice interview · {generated}", styles["meta"]),
    ]
    right = [
        Paragraph("AURA", styles["brand"]),
        Paragraph("AI Interviewer", styles["brand-sub"]),
    ]
    banner = Table(
        [[left, right]],
        colWidths=[_CONTENT_WIDTH * 0.7, _CONTENT_WIDTH * 0.3],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
        hAlign="LEFT",
    )
    rule = Table(
        [[""]],
        colWidths=[_CONTENT_WIDTH],
        rowHeights=[2],
        style=TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 2, _ACCENT),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
    )
    return [banner, Spacer(1, 10), rule, Spacer(1, 14)]


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(_MARGIN, 14 * mm, A4[0] - _MARGIN, 14 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_FAINT)
    canvas.drawString(_MARGIN, 9 * mm, "Generated by Aura · AI Interviewer")
    canvas.drawRightString(A4[0] - _MARGIN, 9 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def generate_report_pdf(report: FinalReport) -> bytes:
    """Generate a PDF from a FinalReport and return as bytes."""
    styles = _base_styles()
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        title=f"Interview Report — {report.candidate_name}",
        author="Aura AI Interviewer",
    )
    doc.addPageTemplates([
        PageTemplate(
            id="main",
            frames=[Frame(_MARGIN, _MARGIN, _CONTENT_WIDTH, A4[1] - 2 * _MARGIN, id="body")],
            onPage=_footer,
        ),
    ])

    elements: list = []
    elements.extend(_header_block(report, styles))

    # Overview row: identity card (left) and score/summary block (right).
    overview = Table(
        [[_identity_block(report, styles), _score_block(report, styles)]],
        colWidths=[_CONTENT_WIDTH * 0.38, _CONTENT_WIDTH * 0.62],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
        hAlign="LEFT",
    )
    elements.append(overview)
    elements.append(Spacer(1, 10))

    # Summary flows on its own (never inside a fixed table) so a long summary
    # simply continues onto the next page instead of breaking layout.
    summary_block = [
        Paragraph("Overall performance summary", styles["subhead"]),
        Paragraph(escape(report.summary), styles["body"]),
    ]
    elements.append(KeepTogether(summary_block))
    elements.append(Spacer(1, 4))

    # Strengths and weaknesses as paired rows — one row per bullet pair — so a
    # long list splits between rows across pages instead of overflowing.
    header = [
        Paragraph("Key strengths", styles["subhead"]),
        Paragraph("Areas for improvement", styles["subhead"]),
    ]
    count = max(len(report.strengths), len(report.weaknesses))
    rows = [header]
    for i in range(count):
        s = report.strengths[i] if i < len(report.strengths) else ""
        w = report.weaknesses[i] if i < len(report.weaknesses) else ""
        rows.append([
            Paragraph(escape(s), styles["bullet"], bulletText="•") if s else "",
            Paragraph(escape(w), styles["bullet"], bulletText="•") if w else "",
        ])
    if count == 0:
        rows.append([
            Paragraph("None noted.", styles["body"]),
            Paragraph("None noted.", styles["body"]),
        ])
    two_col = Table(
        rows,
        colWidths=[_CONTENT_WIDTH / 2, _CONTENT_WIDTH / 2],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, -1), 14),
            ("LEFTPADDING", (1, 0), (1, -1), 14),
            ("RIGHTPADDING", (1, 0), (1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LINEABOVE", (0, 0), (-1, 0), 0.5, _BORDER),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, _BORDER),
        ]),
        hAlign="LEFT",
    )
    elements.append(two_col)

    if report.section_grades:
        elements.append(Paragraph("Section breakdown", styles["section"]))
        elements.append(_section_table(report, styles))

    # The overview table carries the summary; keep pages from splitting it.
    doc.build(elements)
    return buf.getvalue()
