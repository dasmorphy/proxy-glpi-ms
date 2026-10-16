import os
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from io import BytesIO
from xml.sax.saxutils import escape

from loguru import logger
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
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
from svglib.svglib import svg2rlg

# Generación del PDF de la proforma (cotización comercial)

LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources",
    "static",
    "logo_telearseg.svg",
)
# Ancho del ícono dentro del viewBox del logo (el resto es el texto "TeleArseg")
LOGO_ICON_WIDTH = 190

COMPANY_PHONE = "+593 93 919 6903"
COMPANY_EMAIL = "ventas@telearseg.net"
COMPANY_ADDRESS = "Urdesa, Av Las Aguas 1111 entre Jiguas y Laureles"
SELLER_ROLE = "Asesor Comercial"

BLUE = colors.HexColor("#0B3CC1")
BLUE_DARK = colors.HexColor("#082A8C")
BLUE_LIGHT = colors.HexColor("#1F63F0")
BLUE_TITLE = colors.HexColor("#1A5BE0")
BLUE_TEXT_HEX = "#1D3FBF"
LABEL_COLOR = colors.HexColor("#1B2A7A")
DARK_GRAY = colors.HexColor("#3A3A3A")

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 22
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN
HEADER_TOP = PAGE_HEIGHT - 30
HEADER_HEIGHT = 82
HEADER_BOTTOM = HEADER_TOP - HEADER_HEIGHT

# Ítem, Modelo, Descripción, Cant., PVP ($ + valor), Total ($ + valor)
ITEM_COLUMNS = [29, 86, 269, 32, 12, 52, 12, 59]

_description_style = ParagraphStyle(
    "description", fontName="Helvetica", fontSize=7, leading=8.6, alignment=TA_CENTER
)
_cell_style = ParagraphStyle(
    "cell", fontName="Helvetica", fontSize=7, leading=8.6, alignment=TA_CENTER
)
_info_label_style = ParagraphStyle(
    "info_label", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=LABEL_COLOR
)
_info_value_style = ParagraphStyle(
    "info_value", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5
)


@lru_cache(maxsize=1)
def _load_logo():
    try:
        return svg2rlg(LOGO_PATH)
    except Exception as exception:
        logger.error("No se pudo cargar el logo de la proforma: {}", str(exception))
        return None


def format_money(value):
    """Formato 1.968,33 usado en la proforma."""
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_quantity(value):
    if value is None:
        return ""
    amount = Decimal(str(value))
    if amount == amount.to_integral_value():
        return str(int(amount))
    return format_money(amount).rstrip("0").rstrip(",")


def format_date(value):
    return f"{value.day}/{value.month}/{value.year}" if value else ""


def _text(value):
    return escape(str(value)) if value not in (None, "") else ""


def _corner_path(canv, x, y, width, height, radius, corner):
    """Rectángulo con una sola esquina redondeada ("bottom_left" o "bottom_right")."""
    kappa = 0.5523 * radius
    path = canv.beginPath()
    if corner == "bottom_left":
        path.moveTo(x + radius, y)
        path.lineTo(x + width, y)
        path.lineTo(x + width, y + height)
        path.lineTo(x, y + height)
        path.lineTo(x, y + radius)
        path.curveTo(x, y + radius - kappa, x + radius - kappa, y, x + radius, y)
    else:
        path.moveTo(x, y)
        path.lineTo(x + width - radius, y)
        path.curveTo(x + width - radius + kappa, y, x + width, y + radius - kappa, x + width, y + radius)
        path.lineTo(x + width, y + height)
        path.lineTo(x, y + height)
    path.close()
    return path


def _draw_logo(canv, x, y, height, icon_only=False):
    logo = _load_logo()
    if logo is None:
        return
    scale = height / logo.height
    canv.saveState()
    if icon_only:
        clip = canv.beginPath()
        clip.rect(x, y, LOGO_ICON_WIDTH * scale, height)
        canv.clipPath(clip, stroke=0, fill=0)
    canv.translate(x, y)
    canv.scale(scale, scale)
    renderPDF.draw(logo, canv, 0, 0)
    canv.restoreState()


def _draw_header(canv, data):
    # Bloque azul con degradado y el logo
    blue_width = PAGE_WIDTH * 0.50 - MARGIN
    canv.saveState()
    canv.clipPath(
        _corner_path(canv, MARGIN, HEADER_BOTTOM, blue_width, HEADER_HEIGHT, 30, "bottom_right"),
        stroke=0,
        fill=0,
    )
    canv.linearGradient(
        MARGIN, HEADER_BOTTOM, MARGIN + blue_width, HEADER_TOP,
        (BLUE_DARK, BLUE_LIGHT),
        extend=True,
    )
    canv.restoreState()
    _draw_logo(canv, MARGIN + 38, HEADER_BOTTOM + 10, 36)

    # Bloque gris con el asesor comercial y los datos de contacto
    gray_x = PAGE_WIDTH * 0.40
    gray_height = 62
    canv.saveState()
    canv.setFillColor(DARK_GRAY)
    canv.drawPath(
        _corner_path(canv, gray_x, HEADER_TOP - gray_height, PAGE_WIDTH - MARGIN - gray_x, gray_height, 34, "bottom_left"),
        stroke=0,
        fill=1,
    )
    canv.setFillColor(colors.white)
    name_x = gray_x + 40
    canv.setFont("Helvetica-Bold", 15)
    canv.drawString(name_x, HEADER_TOP - 28, data["seller_name"])
    canv.setFont("Helvetica", 10)
    canv.drawString(name_x, HEADER_TOP - 42, SELLER_ROLE)

    separator_x = PAGE_WIDTH * 0.705
    canv.setStrokeColor(colors.white)
    canv.setLineWidth(0.6)
    canv.line(separator_x, HEADER_TOP - 52, separator_x, HEADER_TOP - 12)
    canv.setFont("Helvetica", 5.6)
    for index, line in enumerate((COMPANY_PHONE, COMPANY_EMAIL, COMPANY_ADDRESS)):
        canv.drawString(separator_x + 8, HEADER_TOP - 20 - index * 12, line)

    canv.setFillColor(BLUE_TITLE)
    canv.setFont("Helvetica-Bold", 17)
    canv.drawCentredString(
        PAGE_WIDTH * 0.74,
        HEADER_TOP - gray_height - 25,
        "COTIZACIÓN COMERCIAL",
    )
    canv.restoreState()


class PaymentDetails(Flowable):
    """Recuadro azul "DETALLES DEL PAGO" con el ícono del logo de fondo."""

    def __init__(self, lines):
        super().__init__()
        self.lines = lines
        self.width = CONTENT_WIDTH
        self.height = 84

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def draw(self):
        canv = self.canv
        canv.saveState()
        canv.setFillColor(BLUE)
        canv.rect(0, 0, self.width, self.height, stroke=0, fill=1)

        clip = canv.beginPath()
        clip.rect(0, 0, self.width, self.height)
        canv.clipPath(clip, stroke=0, fill=0)
        _draw_logo(canv, self.width - 115, -38, 120, icon_only=True)
        canv.restoreState()

        canv.saveState()
        canv.setFillColor(colors.white)
        canv.setFont("Helvetica-BoldOblique", 15)
        canv.drawString(4, self.height - 20, "DETALLES DEL PAGO:")
        canv.setFont("Helvetica-Bold", 7)
        for index, line in enumerate(self.lines):
            canv.drawString(4, self.height - 40 - index * 15, line)
        canv.restoreState()


def _info_table(data):
    def label(text):
        return Paragraph(text, _info_label_style)

    def value(text):
        return Paragraph(_text(text), _info_value_style)

    rows = [
        [label("Cotización:"), value(data["quote_number"]), label("Fecha:"), value(format_date(data["date"]))],
        [label("Ruc:"), value(data["ruc"]), "", ""],
        [label("Cliente:"), value(data["client"]), label("Solicita:"), value(data["requested_by"])],
        [label("Proyecto:"), value(data["project"]), "", ""],
    ]
    table = Table(rows, colWidths=[110, 300, 46, 95])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    return table


def _description(item):
    label = item.get("label")
    description = _text(item.get("description")).replace("\n", "<br/>")
    if not label:
        return Paragraph(description, _description_style)
    return Paragraph(
        f'<b>{escape(label)}:</b> <font color="{BLUE_TEXT_HEX}">{description}</font>',
        _description_style,
    )


def _items_table(data):
    header_style = ParagraphStyle(
        "header", fontName="Helvetica-Bold", fontSize=9, leading=11,
        alignment=TA_CENTER, textColor=colors.white,
    )
    title_style = ParagraphStyle(
        "title", parent=header_style, fontSize=8, leading=10,
    )
    rows = [
        [Paragraph(_text(data["project"]), title_style)] + [""] * 7,
        [Paragraph(text, header_style) for text in ("Ítem", "Modelo", "Descripción", "Cant.", "PVP")]
        + [""]
        + [Paragraph("Total", header_style), ""],
    ]
    for item in data["items"]:
        rows.append([
            item["item_number"],
            Paragraph(_text(item["model"]), _cell_style),
            _description(item),
            format_quantity(item["quantity"]),
            "$",
            format_money(item["price"]),
            "$",
            format_money(item["total"]),
        ])

    table = Table(rows, colWidths=ITEM_COLUMNS, repeatRows=2)
    line = 0.6
    style = [
        ("SPAN", (0, 0), (-1, 0)),
        ("SPAN", (4, 1), (5, 1)),
        ("SPAN", (6, 1), (7, 1)),
        ("BACKGROUND", (0, 0), (-1, 0), DARK_GRAY),
        ("BACKGROUND", (0, 1), (-1, 1), BLUE),
        ("BACKGROUND", (0, 2), (0, -1), DARK_GRAY),
        ("TEXTCOLOR", (0, 2), (0, -1), colors.white),
        ("FONTNAME", (0, 2), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 2), (-1, -1), 7),
        ("ALIGN", (0, 2), (3, -1), "CENTER"),
        ("ALIGN", (4, 2), (4, -1), "LEFT"),
        ("ALIGN", (6, 2), (6, -1), "LEFT"),
        ("ALIGN", (5, 2), (5, -1), "RIGHT"),
        ("ALIGN", (7, 2), (7, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 1), 6),
        ("TOPPADDING", (0, 2), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 2), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("BOX", (0, 0), (-1, -1), line, colors.black),
        ("LINEBELOW", (0, 0), (-1, -1), line, colors.black),
    ]
    # El símbolo $ y su valor comparten celda visual: sin línea entre ambos
    for column in (1, 2, 3, 4, 6):
        style.append(("LINEBEFORE", (column, 1), (column, -1), line, colors.black))
    table.setStyle(TableStyle(style))
    return table


def _totals_table(data):
    rows = [
        ["Subtotal", "$", format_money(data["subtotal"])],
        ["IVA", "$", format_money(data["iva"])],
        ["Total", "$", format_money(data["total"])],
    ]
    table = Table(rows, colWidths=[ITEM_COLUMNS[4] + ITEM_COLUMNS[5], ITEM_COLUMNS[6], ITEM_COLUMNS[7]], hAlign="RIGHT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLUE),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.black),
        ("LINEBEFORE", (1, 0), (1, -1), 0.6, colors.black),
    ]))
    return table


def _payment_lines(data):
    validity = data.get("validity_days")
    return [
        f"Tiempo de entrega: {data.get('delivery_time') or ''}",
        f"Forma de pago: {data.get('payment_terms') or ''}",
        "Esta proforma es válida hasta: "
        + (f"{validity} días después de su emisión" if validity is not None else ""),
    ]


def generate_proforma_pdf(data):
    """Genera el PDF de la proforma y retorna su contenido en bytes.

    data: quote_number, date, ruc, client, requested_by, project, seller_name,
    items [{item_number, model, description, label, quantity, price, total}],
    subtotal, iva, total, delivery_time, payment_terms, validity_days.
    """
    buffer = BytesIO()
    document = BaseDocTemplate(
        buffer,
        pagesize=A4,
        title=f"Cotización {data.get('quote_number') or ''}".strip(),
        author="TeleArseg",
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=30,
        bottomMargin=30,
    )
    first_frame = Frame(
        MARGIN, 30, CONTENT_WIDTH, HEADER_BOTTOM - 22 - 30, id="first", leftPadding=0, rightPadding=0
    )
    later_frame = Frame(
        MARGIN, 30, CONTENT_WIDTH, PAGE_HEIGHT - 60, id="later", leftPadding=0, rightPadding=0
    )
    document.addPageTemplates([
        PageTemplate(id="first", frames=[first_frame], onPage=lambda canv, _: _draw_header(canv, data), autoNextPageTemplate="later"),
        PageTemplate(id="later", frames=[later_frame]),
    ])
    document.build([
        _info_table(data),
        Spacer(1, 12),
        _items_table(data),
        Spacer(1, 4),
        KeepTogether([
            _totals_table(data),
            Spacer(1, 30),
            PaymentDetails(_payment_lines(data)),
        ]),
    ])
    return buffer.getvalue()
