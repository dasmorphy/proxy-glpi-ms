from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Generación del Excel de la proforma (mismas columnas que la pantalla de Comercial)

NAVY = "0B2F68"
LABEL = "34445F"
MUTED = "7C899D"
BORDER_COLOR = "DBE3EE"
ROW_ALT = "F6F8FB"

MONEY = '"$"#,##0.00'
PERCENT = "0.00%"
QUANTITY = "#,##0.##"

# (título, ancho)
COLUMNS = [
    ("Ítem", 6),
    ("Modelo", 22),
    ("Descripción", 60),
    ("Tipo", 16),
    ("Cant.", 8),
    ("Costo", 13),
    ("Ganancia %", 12),
    ("Ganancia $", 13),
    ("PVP", 13),
    ("Total", 14),
]
LAST_COLUMN = get_column_letter(len(COLUMNS))

_thin = Side(style="thin", color=BORDER_COLOR)
_border = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
_wrap_top = Alignment(vertical="top", wrap_text=True)


def _number(value):
    if value is None:
        return None
    return float(value) if isinstance(value, Decimal) else value


def _quantity(value):
    number = _number(value)
    if isinstance(number, float) and number.is_integer():
        return int(number)
    return number


def _info_row(sheet, row, label, value):
    sheet.cell(row=row, column=1, value=label).font = Font(bold=True, color=LABEL)
    sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
    cell = sheet.cell(row=row, column=3, value=value if value not in (None, "") else "—")
    cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet.merge_cells(start_row=row, start_column=3, end_row=row, end_column=len(COLUMNS))


def generate_proforma_excel(data):
    """
    data: quote_number, date, ruc, client, requested_by, project, seller_name,
    items (item_number, model, label, description, quantity, base_price,
    profit_margin, profit_margin_dollar, price, total), subtotal, iva_rate, iva,
    total, delivery_time, payment_terms, validity_days.
    Retorna el .xlsx en bytes.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Proforma"
    sheet.sheet_view.showGridLines = False

    for index, (_, width) in enumerate(COLUMNS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width

    # Encabezado
    title = f"Proforma {data.get('quote_number') or ''}".strip()
    sheet["A1"] = title
    sheet["A1"].font = Font(bold=True, size=14, color=NAVY)
    sheet.merge_cells(f"A1:{LAST_COLUMN}1")
    sheet.row_dimensions[1].height = 22

    date = data.get("date")
    info = [
        ("Cliente", data.get("client")),
        ("RUC", data.get("ruc")),
        ("Proyecto", data.get("project")),
        ("Solicita", data.get("requested_by")),
        ("Asesor", data.get("seller_name")),
        ("Fecha", date.strftime("%d/%m/%Y") if date else None),
    ]
    row = 3
    for label, value in info:
        _info_row(sheet, row, label, value)
        row += 1

    # Tabla de ítems
    row += 1
    header_row = row
    for index, (name, _) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=row, column=index, value=name)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _border
    sheet.row_dimensions[row].height = 20

    for position, item in enumerate(data.get("items") or []):
        row += 1
        values = [
            item.get("item_number"),
            item.get("model"),
            item.get("description"),
            item.get("label") or "Producto",
            _quantity(item.get("quantity")),
            _number(item.get("base_price")),
            _number(item.get("profit_margin")),
            _number(item.get("profit_margin_dollar")),
            _number(item.get("price")),
            _number(item.get("total")),
        ]
        formats = [None, None, None, None, QUANTITY, MONEY, PERCENT, MONEY, MONEY, MONEY]
        fill = PatternFill("solid", fgColor=ROW_ALT) if position % 2 else None
        for index, (value, number_format) in enumerate(zip(values, formats), start=1):
            cell = sheet.cell(row=row, column=index, value=value)
            cell.border = _border
            cell.alignment = _wrap_top
            if number_format:
                cell.number_format = number_format
            if fill:
                cell.fill = fill
        sheet.cell(row=row, column=1).alignment = Alignment(horizontal="center", vertical="top")
        sheet.cell(row=row, column=4).font = Font(color=MUTED, italic=True)
        sheet.cell(row=row, column=9).font = Font(bold=True)
        sheet.cell(row=row, column=10).font = Font(bold=True)

    sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
    sheet.auto_filter.ref = f"A{header_row}:{LAST_COLUMN}{max(row, header_row)}"

    # Totales
    iva_rate = _number(data.get("iva_rate"))
    iva_label = "IVA"
    if iva_rate is not None:
        # iva_rate puede venir como 15 o como 0.15
        rate = iva_rate * 100 if iva_rate <= 1 else iva_rate
        iva_label = f"IVA ({rate:g}%)"

    row += 1
    for label, value, bold in (
        ("Subtotal", data.get("subtotal"), False),
        (iva_label, data.get("iva"), False),
        ("Total", data.get("total"), True),
    ):
        row += 1
        label_cell = sheet.cell(row=row, column=9, value=label)
        value_cell = sheet.cell(row=row, column=10, value=_number(value))
        value_cell.number_format = MONEY
        label_cell.alignment = Alignment(horizontal="right")
        if bold:
            for cell in (label_cell, value_cell):
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor=NAVY)
        else:
            label_cell.font = Font(color=MUTED)
            value_cell.font = Font(bold=True)

    # Condiciones
    validity = data.get("validity_days")
    conditions = [
        ("Tiempo de entrega", data.get("delivery_time")),
        ("Forma de pago", data.get("payment_terms")),
        ("Validez", f"{validity} días" if validity else None),
    ]
    if any(value for _, value in conditions):
        row += 2
        sheet.cell(row=row, column=1, value="Condiciones de la proforma").font = Font(
            bold=True, color=NAVY
        )
        for label, value in conditions:
            row += 1
            _info_row(sheet, row, label, value)

    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
