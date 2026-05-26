from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.platypus.tables import Table, TableStyle


def generate_review_pdf(review_data):
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    elements = []

    title = Paragraph(
        "<b>Universidad Veracruzana</b><br/>"
        "Instituto de Investigaciones en Contaduría<br/><br/>"
        "<font size=16><b>DICTAMEN ACADÉMICO ASISTIDO POR IA</b></font>",
        styles["Title"],
    )

    elements.append(title)
    elements.append(Spacer(1, 20))

    data = [
        ["Archivo", review_data.get("filename", "")],
        ["Tipo", review_data.get("review_type", "")],
        ["Calificación", review_data.get("score", "")],
        ["IA", review_data.get("ai_probability", "")],
        ["Resultado", review_data.get("badge", "")],
    ]

    table = Table(data, colWidths=[150, 300])

    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )

    elements.append(table)
    elements.append(Spacer(1, 25))

    observations = Paragraph(
        f"""
        <b>Observaciones:</b><br/><br/>
        {review_data.get("observations", "Sin observaciones")}
        """,
        styles["BodyText"],
    )

    elements.append(observations)

    elements.append(Spacer(1, 30))

    final_text = Paragraph(
        """
        <b>Conclusión:</b><br/>
        Este dictamen fue generado mediante herramientas de inteligencia artificial
        para apoyo en revisión académica y arbitraje científico.
        """,
        styles["BodyText"],
    )

    elements.append(final_text)

    doc.build(elements)

    pdf = buffer.getvalue()
    buffer.close()

    return pdf