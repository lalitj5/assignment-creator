import io

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.platypus.flowables import KeepInFrame


def build_assignment_pdf(data: dict) -> bytes:
    """Render the assignment as a one-page PDF and return the raw bytes.

    `data` must have keys:
        key_ideas  – list of exactly 3 short concept name strings
        questions  – list of at least 8 open-ended question strings
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1 * inch,
        rightMargin=1 * inch,
        topMargin=1 * inch,
        bottomMargin=1 * inch,
    )

    styles = getSampleStyleSheet()
    heading_style = ParagraphStyle(
        "Heading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        spaceAfter=6,
    )
    idea_style = ParagraphStyle(
        "Idea",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leftIndent=14,
        spaceAfter=4,
    )
    question_style = ParagraphStyle(
        "Question",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        spaceAfter=8,
        leading=15,
    )

    story = []

    # Key ideas section
    story.append(Paragraph("Key Ideas:", heading_style))
    for idea in data["key_ideas"]:
        story.append(Paragraph(f"– {idea}", idea_style))

    story.append(Spacer(1, 0.2 * inch))

    # Questions section
    story.append(Paragraph("Questions:", heading_style))
    for i, question in enumerate(data["questions"], start=1):
        story.append(Paragraph(f"{i}.&nbsp; {question}", question_style))

    # Constrain everything to one page
    page_width, page_height = letter
    usable_width = page_width - 2 * inch
    usable_height = page_height - 2 * inch

    frame = KeepInFrame(usable_width, usable_height, story, mode="shrink")
    doc.build([frame])

    return buffer.getvalue()
