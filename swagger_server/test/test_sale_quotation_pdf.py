from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from swagger_server.uses_cases.internal_management_use_case import (
    InternalManagementUseCase,
)
from swagger_server.utils.proforma_pdf import (
    format_money,
    format_quantity,
    generate_proforma_pdf,
)


def _item(**values):
    defaults = dict(
        id_item=1, item_number=1, material_id=None, is_bundle=False,
        is_labor=False, is_new=False, model=None, description=None,
        quantity=Decimal("1"), total=Decimal("0"),
    )
    defaults.update(values)
    return SimpleNamespace(**defaults)


class FakeRepository:
    def __init__(self, seller):
        self.seller = seller

    def get_sale_quotation_document(self, id_quote, internal, external):
        quotation = SimpleNamespace(
            id_quote=id_quote, quote_number="10150159",
            created_at=datetime(2026, 9, 22), created_by="obarba",
            subtotal=Decimal("10516.58"), iva=Decimal("1577.49"),
            total=Decimal("12094.06"), delivery_time="4 Dias laborables.",
            payment_terms="100% Contra Entrega.", validity_days=30,
        )
        inspection = SimpleNamespace(
            contact="Ing. Marcelo Torres",
            title_ticket="IMPLEMENTACION DE SISTEMA CCTV PERIMETRAL - TAURA 2",
        )
        company = SimpleNamespace(
            company_name="INDUSTRIAL PESQUERA SANTA PRISCILA S.A.",
            identity="0991257721001",
        )
        items = [
            _item(id_item=1, item_number=1, material_id=10,
                  quantity=Decimal("6.00"), total=Decimal("1968.33")),
            _item(id_item=2, item_number=2, is_new=True, model="I/S",
                  description="INVERSOR SOLAR 2KVA - 24v",
                  quantity=Decimal("3"), total=Decimal("1755")),
            _item(id_item=3, item_number=3, is_bundle=True, total=Decimal("626.86")),
            _item(id_item=4, item_number=4, is_labor=True,
                  description="3 Tecnicos - 4 Dias", total=Decimal("897")),
        ]
        components = [
            SimpleNamespace(quotation_item_id=3, material_id=20, quantity=Decimal("80.00")),
            SimpleNamespace(quotation_item_id=3, material_id=21, quantity=Decimal("3")),
        ]
        equipment = {
            10: SimpleNamespace(model="DS-2TD2617-10/QA", product="CAMARA IP TUBO TERMICA"),
            20: SimpleNamespace(model="C10", product="metros de cable para panel #10"),
            21: SimpleNamespace(model="B16", product="breakers AC de 16 A"),
        }
        return quotation, inspection, company, self.seller, items, components, equipment


class TestSaleQuotationPdf(unittest.TestCase):
    def _generate(self, seller):
        use_case = InternalManagementUseCase(FakeRepository(seller))
        with patch(
            "swagger_server.uses_cases.internal_management_use_case.generate_proforma_pdf",
            side_effect=lambda data: data,
        ):
            return use_case.generate_sale_quotation_pdf(7, "int", "ext")

    def test_maps_quotation_to_pdf_fields(self):
        seller = SimpleNamespace(user="obarba", attributes={"fullname": "Odalis Barba"})
        data, name = self._generate(seller)

        self.assertEqual(name, "proforma_10150159.pdf")
        self.assertEqual(data["seller_name"], "Odalis Barba")
        self.assertEqual(data["requested_by"], "Ing. Marcelo Torres")
        self.assertEqual(data["client"], "INDUSTRIAL PESQUERA SANTA PRISCILA S.A.")
        self.assertEqual(data["ruc"], "0991257721001")
        self.assertEqual(data["project"], "IMPLEMENTACION DE SISTEMA CCTV PERIMETRAL - TAURA 2")
        self.assertEqual(data["validity_days"], 30)

        catalog, new, bundle, labor = data["items"]
        self.assertEqual((catalog["model"], catalog["description"]),
                         ("DS-2TD2617-10/QA", "CAMARA IP TUBO TERMICA"))
        self.assertEqual(catalog["price"], Decimal("328.055"))
        self.assertEqual((new["model"], new["description"]), ("I/S", "INVERSOR SOLAR 2KVA - 24v"))
        self.assertEqual(bundle["label"], "Materiales varios")
        self.assertEqual(bundle["model"], "M/V")
        self.assertEqual(
            bundle["description"],
            "80 metros de cable para panel #10, 3 breakers AC de 16 A",
        )
        self.assertEqual((labor["label"], labor["model"]), ("Mano de obra", "M/V"))

    def test_seller_falls_back_to_created_by(self):
        data, _ = self._generate(None)
        self.assertEqual(data["seller_name"], "obarba")

    def test_generates_pdf_bytes(self):
        seller = SimpleNamespace(user="obarba", attributes={"fullname": "Odalis Barba"})
        data, _ = self._generate(seller)
        content = generate_proforma_pdf(data)
        self.assertTrue(content.startswith(b"%PDF"))

    def test_formats(self):
        self.assertEqual(format_money(Decimal("1968.333")), "1.968,33")
        self.assertEqual(format_money(None), "0,00")
        self.assertEqual(format_quantity(Decimal("6.00")), "6")
        self.assertEqual(format_quantity(Decimal("2.50")), "2,5")


if __name__ == "__main__":
    unittest.main()
