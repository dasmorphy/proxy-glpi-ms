from decimal import Decimal
from types import SimpleNamespace
import unittest

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.models.db.commercial_ticket_management import (
    CommercialTicketManagement,
)
from swagger_server.models.db.sale_additional_materials import (
    SaleAdditionalMaterials,
)
from swagger_server.models.db.sale_quotation import SaleQuotation
from swagger_server.models.db.sale_quotation_item import SaleQuotationItem
from swagger_server.repository.internal_management_repository import (
    InternalManagementRepository,
)
from swagger_server.uses_cases.internal_management_use_case import (
    InternalManagementUseCase,
)


SALE_QUOTATION = {
    "client_company": 1,
    "items": [
        {
            "item": 1, "material_id": 152, "quantity": 20, "base_price": 1.09,
            "profit_margin": 0.3, "profit_margin_dollar": 0.33, "price": 1.42,
            "total": 28.4, "is_bundle": False, "is_labor": False,
            "components": [],
        },
        {
            "item": 2, "material_id": None, "quantity": 1, "base_price": 158.48,
            "profit_margin": 0.259, "profit_margin_dollar": 41.04,
            "price": 199.52, "total": 199.52, "is_bundle": True,
            "is_labor": False,
            "components": [
                {"material_id": 107, "quantity": 1, "base_price": 93.48,
                 "profit_margin": 0.3, "profit_margin_dollar": 28.04,
                 "total": 121.52},
                {"material_id": 270, "quantity": 1, "base_price": 65,
                 "profit_margin": 0.2, "profit_margin_dollar": 13,
                 "total": 78},
            ],
        },
        {
            "item": 3, "material_id": None, "quantity": 1, "base_price": 500,
            "profit_margin": None, "profit_margin_dollar": 0, "price": 500,
            "total": 500, "is_bundle": False, "is_labor": True,
            "model": "M/V", "description": "Instalación",
            "components": [],
        },
        {
            "item": 4, "material_id": None, "quantity": 2, "base_price": 10,
            "profit_margin": 0.1, "profit_margin_dollar": 1, "price": 11,
            "total": 22, "is_bundle": False, "is_labor": False,
            "is_new": True, "model": "X-1", "description": "Producto nuevo",
            "components": [],
        },
    ],
    "subtotal": 749.92,
    "iva_rate": 0.15,
    "iva": 112.49,
    "total": 862.41,
}


class FakeSession:
    def __init__(self, existing_quotation=None):
        self.inspection = SimpleNamespace(
            id_inspection=7, management_area="Comercial", next_area=None
        )
        # Solo una gestión en estado pendiente (7) se puede editar
        self.management = SimpleNamespace(updated_by=None, status_id=7)
        self.existing_quotation = existing_quotation
        self.added = []
        self.statements = []
        self.committed = False
        self.rolled_back = False
        self._next_item_id = 100

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def get(self, model, key):
        return self.inspection

    def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        is_quotation_select = sql.startswith("SELECT") and "FROM internal_management.sale_quotation" in sql
        first = self.existing_quotation if is_quotation_select else self.management
        return SimpleNamespace(
            scalar_one_or_none=lambda: self.inspection,
            # Sin pendientes del técnico que sincronizar
            scalars=lambda: SimpleNamespace(first=lambda: first, all=lambda: []),
        )

    def add(self, record):
        self.added.append(record)
        if isinstance(record, CommercialTicketManagement):
            record.id_management_commercial = 12
        if isinstance(record, SaleQuotation):
            record.id_quote = 30

    def flush(self):
        for record in self.added:
            if isinstance(record, SaleQuotationItem) and record.id_item is None:
                record.id_item = self._next_item_id
                self._next_item_id += 1

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def build_repository(session):
    repository = InternalManagementRepository.__new__(InternalManagementRepository)
    repository.db_telearseg = SimpleNamespace(session_factory=lambda: session)
    return repository


def added(session, model):
    return [r for r in session.added if isinstance(r, model)]


class TestPostTicketCommercialSaleQuotation(unittest.TestCase):
    def post(self, **extra):
        session = FakeSession()
        body = {"inspection_id": 7, "status_id": 1, "user": "dmales", **extra}
        build_repository(session).post_ticket_commercial(body, "internal", "external")
        return session

    def test_saves_quotation_items_and_bundle_components(self):
        session = self.post(sale_quotation=SALE_QUOTATION)

        [quotation] = added(session, SaleQuotation)
        self.assertEqual(7, quotation.inspection_id)
        self.assertEqual(1, quotation.client_company)
        self.assertEqual(862.41, quotation.total)
        self.assertEqual("dmales", quotation.created_by)

        items = added(session, SaleQuotationItem)
        self.assertEqual([1, 2, 3, 4], [i.item_number for i in items])
        self.assertTrue(all(i.sale_quote_id == 30 for i in items))
        self.assertTrue(items[1].is_bundle)
        self.assertTrue(items[2].is_labor)
        self.assertEqual("Instalación", items[2].description)
        self.assertTrue(items[3].is_new)
        self.assertEqual("X-1", items[3].model)
        self.assertIsNone(items[0].description)

        extras = added(session, SaleAdditionalMaterials)
        self.assertEqual([107, 270], [e.material_id for e in extras])
        self.assertTrue(all(e.sale_quote_id == 30 for e in extras))
        self.assertTrue(all(e.quotation_item_id == items[1].id_item for e in extras))
        self.assertTrue(session.committed)

    def test_without_quotation_only_saves_commercial_ticket(self):
        session = self.post()

        self.assertEqual([], added(session, SaleQuotation))
        self.assertEqual(1, len(added(session, CommercialTicketManagement)))
        self.assertTrue(session.committed)


class TestPutTicketCommercialSaleQuotation(unittest.TestCase):
    def put(self, existing_quotation):
        session = FakeSession(existing_quotation)
        build_repository(session).update_ticket_commercial(
            {"inspection_id": 7, "user": "editor", "sale_quotation": SALE_QUOTATION},
            "internal",
            "external",
        )
        return session

    def test_replaces_items_of_existing_quotation(self):
        existing = SaleQuotation(id_quote=55, inspection_id=7, created_by="creador")
        session = self.put(existing)

        self.assertEqual([], added(session, SaleQuotation))
        self.assertEqual(862.41, existing.total)
        self.assertEqual("creador", existing.created_by)
        self.assertEqual("editor", existing.updated_by)

        deletes = [s for s in session.statements if s.startswith("DELETE")]
        self.assertIn("sale_additional_materials", deletes[0])
        self.assertIn("sale_quotation_item", deletes[1])

        items = added(session, SaleQuotationItem)
        self.assertEqual(4, len(items))
        self.assertTrue(all(i.sale_quote_id == 55 for i in items))
        self.assertTrue(session.committed)

    def test_creates_quotation_when_inspection_has_none(self):
        session = self.put(None)

        [quotation] = added(session, SaleQuotation)
        self.assertEqual(7, quotation.inspection_id)
        self.assertEqual("editor", quotation.created_by)
        self.assertFalse(any(s.startswith("DELETE") for s in session.statements))

    def test_rejects_editing_a_management_that_is_not_pending(self):
        session = FakeSession(None)
        session.management.status_id = 5

        with self.assertRaises(CustomAPIException):
            build_repository(session).update_ticket_commercial(
                {"inspection_id": 7, "user": "editor", "sale_quotation": SALE_QUOTATION},
                "internal",
                "external",
            )

        self.assertEqual([], added(session, SaleQuotation))
        self.assertFalse(session.committed)


class TestSerializeSaleQuotation(unittest.TestCase):
    def setUp(self):
        self.use_case = InternalManagementUseCase.__new__(InternalManagementUseCase)

    def test_groups_components_under_their_bundle_item(self):
        quotation = SaleQuotation(
            id_quote=30, client_company=1, subtotal=Decimal("100.00"),
            iva_rate=Decimal("0.15"), iva=Decimal("15.00"), total=Decimal("115.00"),
        )
        bundle_a = SaleQuotationItem(id_item=1, item_number=1, is_bundle=True, quantity=Decimal("1"))
        labor = SaleQuotationItem(
            id_item=2, item_number=2, is_labor=True, model="M/V",
            description="Instalación", base_price=Decimal("50.00"),
        )
        bundle_b = SaleQuotationItem(id_item=3, item_number=3, is_bundle=True)
        components = [
            SaleAdditionalMaterials(quotation_item_id=1, material_id=107, total=Decimal("10.50")),
            SaleAdditionalMaterials(quotation_item_id=3, material_id=270),
            SaleAdditionalMaterials(quotation_item_id=1, material_id=271),
        ]

        result = self.use_case._serialize_sale_quotation(
            (quotation, [bundle_a, labor, bundle_b], components)
        )

        self.assertEqual(115.0, result["total"])
        self.assertIsInstance(result["iva_rate"], float)
        items = result["items"]
        self.assertEqual([107, 271], [c["material_id"] for c in items[0]["components"]])
        self.assertEqual(10.5, items[0]["components"][0]["total"])
        self.assertEqual([270], [c["material_id"] for c in items[2]["components"]])
        self.assertEqual("Instalación", items[1]["description"])
        self.assertTrue(items[1]["is_labor"])
        self.assertFalse(items[1]["is_new"])
        self.assertEqual(1.0, items[0]["quantity"])

    def test_without_quotation_returns_none(self):
        self.assertIsNone(self.use_case._serialize_sale_quotation(None))


if __name__ == "__main__":
    unittest.main()
