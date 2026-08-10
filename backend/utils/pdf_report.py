import io
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from models.schemas import FinalReport


def generate_report_pdf(report: FinalReport) -> bytes:
    """Generate a PDF from a FinalReport and return as bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    elements.append(Paragraph(f"Interview Report: {escape(report.candidate_name)}", styles["Title"]))
    elements.append(Spacer(1, 12))

    # Score and recommendation
    elements.append(Paragraph(f"Overall Score: {report.overall_score}/100", styles["Heading2"]))
    elements.append(Paragraph(f"Recommendation: {report.recommendation}", styles["Heading2"]))
    elements.append(Spacer(1, 12))

    # Section grades table
    table_data = [["Section", "Score", "Comments"]]
    for g in report.section_grades:
        table_data.append([g.section_name, str(g.score), g.comments])
    table = Table(table_data, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 12))

    # Strengths
    elements.append(Paragraph("Strengths", styles["Heading3"]))
    for s in report.strengths:
        elements.append(Paragraph(f"• {escape(s)}", styles["Normal"]))
    elements.append(Spacer(1, 8))

    # Weaknesses
    elements.append(Paragraph("Weaknesses", styles["Heading3"]))
    for w in report.weaknesses:
        elements.append(Paragraph(f"• {escape(w)}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    # Summary
    elements.append(Paragraph("Summary", styles["Heading3"]))
    elements.append(Paragraph(escape(report.summary), styles["Normal"]))

    doc.build(elements)
    return buf.getvalue()
