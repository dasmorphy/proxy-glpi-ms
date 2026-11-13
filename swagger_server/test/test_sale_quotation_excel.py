from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

from swagger_server.test.test_sale_quotation_pdf import FakeRepository
from swagger_server.uses_cases.internal_management_use_case import (
    InternalManagementUseCase,
)
from swagger_server.utils.proforma_excel import generate_proforma_excel


class TestSaleQuotationExcel(unittest.TestCase):
    def setUp(self):
        seller = SimpleNamespace(user="obarba", attributes={"fullname": "Odalis Barba"})
        self.use_case = InternalManagementUseCase(FakeRepository(seller))

    def _data(self):
        with patch(
            "swagger_server.uses_cases.internal_management_use_case.generate_proforma_excel",
            side_effect=lambda data: data,
        ):
            return self.use_case.generate_sale_quotation_excel(7, "int", "ext")

    def test_name_and_header_fields(self):
        data, name = self._data()
        self.assertEqual(name, "proforma_10150159.xlsx")
        self.assertEqual(data["client"], "INDUSTRIAL PESQUERA SANTA PRISCILA S.A.")
        self.assertEqual(data["ruc"], "0991257721001")
        self.assertEqual(data["project"], "IMPLEMENTACION DE SISTEMA CCTV PERIMETRAL - TAURA 2")

    def test_margin_rate_from_cost_and_margin(self):
        repository = self.use_case.internal_management_repository
        original = repository.get_sale_quotation_document

        def with_costs(*args):
            result = original(*args)
            catalog, _, bundle, labor = result[4]
            catalog.base_price, catalog.profit_margin_dollar = Decimal("82"), Decimal("24.60")
            catalog.profit_margin = Decimal("0.30")
            bundle.base_price, bundle.profit_margin_dollar = Decimal("51.45"), Decimal("15.62")
            labor.base_price, labor.profit_margin_dollar = None, None
            labor.profit_margin = Decimal("0.40")
            return result

        repository.get_sale_quotation_document = with_costs
        data, _ = self._data()
        catalog, _, bundle, labor = data["items"]
        self.assertAlmostEqual(float(catalog["profit_margin"]), 0.30)
        # Margen sobre la venta: 15.62 / (51.45 + 15.62)
        self.assertAlmostEqual(float(bundle["profit_margin"]), 0.2329, places=4)
        self.assertEqual(labor["profit_margin"], Decimal("0.40"))

    def test_generates_workbook(self):
        data, _ = self._data()
        data["items"][0].update(
            base_price=Decimal("82.00"), profit_margin=Decimal("0.30"),
            profit_margin_dollar=Decimal("24.60"),
        )
        content = generate_proforma_excel(data)
        sheet = load_workbook(BytesIO(content)).active

        values = {
            sheet.cell(row=row, column=1).value: sheet.cell(row=row, column=3).value
            for row in range(3, 9)
        }
        self.assertEqual(values["Cliente"], "INDUSTRIAL PESQUERA SANTA PRISCILA S.A.")
        self.assertEqual(values["RUC"], "0991257721001")
        self.assertEqual(values["Proyecto"], "IMPLEMENTACION DE SISTEMA CCTV PERIMETRAL - TAURA 2")

        header = [cell.value for cell in sheet[10]]
        self.assertEqual(header[:3], ["Ítem", "Modelo", "Descripción"])
        first = [cell.value for cell in sheet[11]]
        self.assertEqual(first[1:3], ["DS-2TD2617-10/QA", "CAMARA IP TUBO TERMICA"])
        self.assertEqual(first[4:8], [6, 82.0, 0.3, 24.6])
        self.assertEqual(sheet[14][3].value, "Mano de obra")

        totals = {
            sheet.cell(row=row, column=9).value: sheet.cell(row=row, column=10).value
            for row in range(15, sheet.max_row + 1)
        }
        self.assertEqual(totals["Total"], 12094.06)


if __name__ == "__main__":
    unittest.main()
