from decimal import Decimal
from types import SimpleNamespace
import unittest

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.models.db import Base
from swagger_server.models.db.material_delivery_detail import MaterialDeliveryDetail
from swagger_server.models.db.material_delivery_history import MaterialDeliveryHistory
from swagger_server.models.db.pending_material import PendingMaterial
from swagger_server.models.db.sale_additional_materials import SaleAdditionalMaterials
from swagger_server.models.db.sale_quotation import SaleQuotation
from swagger_server.models.db.sale_quotation_item import SaleQuotationItem
from swagger_server.models.db.task_technical import TaskTechnical
from swagger_server.models.db.task_technical_assignments import TaskTechnicalAssignment
from swagger_server.models.db.technical_equipment import TechnicalEquipment
from swagger_server.repository.internal_management_repository import (
    InternalManagementRepository,
)
from swagger_server.uses_cases.internal_management_use_case import (
    InternalManagementUseCase,
)


TABLES = [
    TaskTechnical.__table__,
    TaskTechnicalAssignment.__table__,
    TechnicalEquipment.__table__,
    SaleQuotation.__table__,
    SaleQuotationItem.__table__,
    SaleAdditionalMaterials.__table__,
    PendingMaterial.__table__,
    MaterialDeliveryHistory.__table__,
    MaterialDeliveryDetail.__table__,
]


def sqlite_repository():
    """Repositorio sobre SQLite en memoria con los esquemas adjuntos, para
    ejercitar las transacciones reales de entrega."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def attach_schemas(connection, _):
        for schema in ("internal_management", "technical"):
            connection.execute(f"ATTACH DATABASE ':memory:' AS {schema}")

    Base.metadata.create_all(engine, tables=TABLES)
    repository = InternalManagementRepository.__new__(InternalManagementRepository)
    repository.db_telearseg = SimpleNamespace(session_factory=sessionmaker(engine))
    return repository


def seed(repository):
    """Proforma con: un producto del catálogo, uno nuevo, mano de obra y
    materiales varios con un componente."""
    with repository.db_telearseg.session_factory() as session:
        session.add_all([
            TaskTechnical(id_task=1, inspection_id=50, code="PRY-1"),
            TaskTechnicalAssignment(task_id=1, user="jperez"),
            TechnicalEquipment(id_equipment=100, product="Cámara IP", stock=5),
            TechnicalEquipment(id_equipment=200, product="Conector RJ45", stock=30),
            SaleQuotation(id_quote=10, inspection_id=50, quote_number="PRF-10"),
            SaleQuotationItem(id_item=1, sale_quote_id=10, item_number=1, material_id=100,
                              is_new=False, is_labor=False, is_bundle=False, quantity=Decimal("4")),
            SaleQuotationItem(id_item=2, sale_quote_id=10, item_number=2, material_id=None,
                              is_new=True, is_labor=False, is_bundle=False, quantity=Decimal("3"),
                              description="Soporte personalizado", model="SP-1",
                              base_price=Decimal("10"), profit_margin=Decimal("0.3"),
                              profit_margin_dollar=Decimal("3")),
            SaleQuotationItem(id_item=3, sale_quote_id=10, item_number=3, material_id=None,
                              is_new=False, is_labor=True, is_bundle=False, quantity=Decimal("1"),
                              description="Instalación"),
            SaleQuotationItem(id_item=4, sale_quote_id=10, item_number=4, material_id=None,
                              is_new=False, is_labor=False, is_bundle=True, quantity=Decimal("1")),
            SaleAdditionalMaterials(id_extra=7, sale_quote_id=10, quotation_item_id=4,
                                    material_id=200, quantity=Decimal("20")),
        ])
        session.commit()


def delivery(items, delivered_to="jperez"):
    return {"task_id": 1, "delivered_to": delivered_to, "items": items, "user": "bodega"}


class TestQuotationQuantities(unittest.TestCase):
    def test_material_quantities_must_be_integers(self):
        with self.assertRaises(CustomAPIException):
            InternalManagementRepository._validate_quotation_quantities(
                {"items": [{"item": 1, "quantity": 2.5}]}
            )

    def test_bundle_component_quantities_must_be_integers(self):
        with self.assertRaises(CustomAPIException):
            InternalManagementRepository._validate_quotation_quantities({
                "items": [{"item": 1, "is_bundle": True, "quantity": 1,
                           "components": [{"quantity": 12.5}]}]
            })

    def test_labor_and_integer_quantities_are_accepted(self):
        InternalManagementRepository._validate_quotation_quantities({
            "items": [
                {"item": 1, "is_labor": True, "quantity": 1.5},
                {"item": 2, "quantity": 3},
                {"item": 3, "quantity": "4.00"},
                {"item": 4, "is_bundle": True, "quantity": 1, "components": [{"quantity": 2}]},
            ]
        })


class TestMaterialDeliveryRepository(unittest.TestCase):
    def setUp(self):
        self.repository = sqlite_repository()
        seed(self.repository)

    def session(self):
        return self.repository.db_telearseg.session_factory()

    def test_generates_pending_only_for_new_items_and_is_idempotent(self):
        with self.session() as session:
            created = InternalManagementRepository._generate_pending_materials(session, 10, "ventas")
            again = InternalManagementRepository._generate_pending_materials(session, 10, "ventas")
            session.commit()
            pendings = session.execute(select(PendingMaterial)).scalars().all()

        self.assertEqual(1, len(created))
        self.assertEqual([], again)
        self.assertEqual(1, len(pendings))
        self.assertEqual(2, pendings[0].quotation_item_id)
        self.assertEqual("Soporte personalizado", pendings[0].name_material)
        self.assertEqual(PendingMaterial.STATUS_PENDING, pendings[0].status)

    def test_delivery_discounts_catalog_stock_and_records_detail(self):
        self.repository.post_material_delivery(delivery([
            {"quotation_item_id": 1, "additional_material_id": None, "quantity": 3},
            {"quotation_item_id": None, "additional_material_id": 7, "quantity": 20},
        ]), "internal", "external")

        with self.session() as session:
            self.assertEqual(2, session.get(TechnicalEquipment, 100).stock)
            self.assertEqual(10, session.get(TechnicalEquipment, 200).stock)
            details = session.execute(
                select(MaterialDeliveryDetail).order_by(MaterialDeliveryDetail.id_delivery_material)
            ).scalars().all()

        self.assertEqual([100, 200], [detail.material_id for detail in details])
        self.assertEqual([Decimal("1"), Decimal("0")], [detail.quantity_remaining for detail in details])

    def test_delivery_is_rejected_when_stock_is_insufficient(self):
        with self.session() as session:
            session.get(TechnicalEquipment, 100).stock = 1
            session.commit()

        with self.assertRaises(CustomAPIException) as error:
            self.repository.post_material_delivery(delivery([
                {"quotation_item_id": 1, "additional_material_id": None, "quantity": 2},
            ]), "internal", "external")

        self.assertIn("Stock insuficiente", str(error.exception))
        with self.session() as session:
            self.assertEqual(1, session.get(TechnicalEquipment, 100).stock)
            self.assertEqual([], session.execute(select(MaterialDeliveryHistory)).scalars().all())

    def test_delivery_cannot_exceed_the_remaining_quantity(self):
        self.repository.post_material_delivery(delivery([
            {"quotation_item_id": 1, "additional_material_id": None, "quantity": 3},
        ]), "internal", "external")

        with self.assertRaises(CustomAPIException) as error:
            self.repository.post_material_delivery(delivery([
                {"quotation_item_id": 1, "additional_material_id": None, "quantity": 2},
            ]), "internal", "external")

        self.assertIn("supera lo pendiente de entregar (1)", str(error.exception))

    def test_labor_items_cannot_be_delivered(self):
        with self.assertRaises(CustomAPIException):
            self.repository.post_material_delivery(delivery([
                {"quotation_item_id": 3, "additional_material_id": None, "quantity": 1},
            ]), "internal", "external")

    def test_new_product_is_delivered_with_its_pending_and_without_stock(self):
        self.repository.post_material_delivery(delivery([
            {"quotation_item_id": 2, "additional_material_id": None, "quantity": 2},
        ]), "internal", "external")

        with self.session() as session:
            detail = session.execute(select(MaterialDeliveryDetail)).scalar_one()
            pending = session.execute(select(PendingMaterial)).scalar_one()

        self.assertIsNone(detail.material_id)
        self.assertEqual(pending.id_pending_material, detail.pending_material_id)

    def test_resolving_pending_discounts_what_was_already_delivered(self):
        self.repository.post_material_delivery(delivery([
            {"quotation_item_id": 2, "additional_material_id": None, "quantity": 2},
        ]), "internal", "external")
        with self.session() as session:
            pending_id = session.execute(select(PendingMaterial)).scalar_one().id_pending_material

        equipment_id = self.repository.resolve_pending_material(
            pending_id,
            {"product": "Soporte personalizado", "stock": 5, "user": "bodega"},
            "internal",
            "external",
        )

        with self.session() as session:
            equipment = session.get(TechnicalEquipment, equipment_id)
            detail = session.execute(select(MaterialDeliveryDetail)).scalar_one()
            pending = session.get(PendingMaterial, pending_id)

        self.assertEqual(3, equipment.stock)
        self.assertEqual(equipment_id, detail.material_id)
        self.assertEqual(pending_id, detail.pending_material_id)
        self.assertEqual(PendingMaterial.STATUS_CREATED, pending.status)
        self.assertEqual(equipment_id, pending.material_id)

        # Ya creado, la siguiente entrega descuenta del catálogo
        self.repository.post_material_delivery(delivery([
            {"quotation_item_id": 2, "additional_material_id": None, "quantity": 1},
        ]), "internal", "external")
        with self.session() as session:
            self.assertEqual(2, session.get(TechnicalEquipment, equipment_id).stock)

    def test_resolving_pending_requires_at_least_the_proforma_quantity(self):
        with self.session() as session:
            InternalManagementRepository._generate_pending_materials(session, 10, None)
            session.commit()
            pending_id = session.execute(select(PendingMaterial)).scalar_one().id_pending_material

        with self.assertRaises(CustomAPIException) as error:
            self.repository.resolve_pending_material(
                pending_id, {"product": "Soporte", "stock": 2}, "internal", "external"
            )
        self.assertIn("al menos la cantidad de la proforma (3)", str(error.exception))

    def test_resolving_twice_is_rejected(self):
        with self.session() as session:
            InternalManagementRepository._generate_pending_materials(session, 10, None)
            session.commit()
            pending_id = session.execute(select(PendingMaterial)).scalar_one().id_pending_material

        self.repository.resolve_pending_material(
            pending_id, {"product": "Soporte", "stock": 3}, "internal", "external"
        )
        with self.assertRaises(CustomAPIException):
            self.repository.resolve_pending_material(
                pending_id, {"product": "Soporte", "stock": 3}, "internal", "external"
            )


class FakeDeliveryRepository:
    def __init__(self):
        self.delivery = None

    def post_material_delivery(self, data, internal, external):
        self.delivery = data
        return 1

    def get_project_materials(self, task_id, internal, external):
        pending = SimpleNamespace(
            id_pending_material=9, status="Pendiente", name_material="Soporte", model="SP-1",
            quantity=Decimal("3.00"), base_price=Decimal("10.00"), profit_margin=Decimal("0.30"),
            profit_margin_dollar=Decimal("3.00"), material_id=None,
        )
        return {
            "task": SimpleNamespace(id_task=task_id),
            "quotation": SimpleNamespace(id_quote=10, quote_number="PRF-10"),
            "items": [
                SimpleNamespace(id_item=1, item_number=1, material_id=100, is_labor=False,
                                is_bundle=False, quantity=Decimal("4.00"), description=None, model=None),
                SimpleNamespace(id_item=2, item_number=2, material_id=None, is_labor=False,
                                is_bundle=False, quantity=Decimal("3.00"), description="Soporte", model="SP-1"),
                SimpleNamespace(id_item=3, item_number=3, material_id=None, is_labor=True,
                                is_bundle=False, quantity=Decimal("1.00"), description="Instalación", model=None),
                SimpleNamespace(id_item=4, item_number=4, material_id=None, is_labor=False,
                                is_bundle=True, quantity=Decimal("1.00"), description=None, model=None),
            ],
            "components": [
                SimpleNamespace(id_extra=7, quotation_item_id=4, material_id=200, quantity=Decimal("20.00")),
            ],
            "pendings": {2: pending},
            "equipment": {
                100: SimpleNamespace(product="Cámara IP", model="CAM", code="C-1", unit="Unid.", stock=5),
                200: SimpleNamespace(product="Conector RJ45", model=None, code="R-1", unit="Unid.", stock=30),
            },
            "delivered": {("item", 1): 3, ("additional", 7): 20},
            "histories": [
                SimpleNamespace(id_history=5, delivered_to="jperez", created_by="bodega",
                                created_at=None, observation=None, status="Registrada"),
            ],
            "details": [
                SimpleNamespace(history_id=5, quotation_item_id=1, additional_material_id=None,
                                material_id=100, pending_material_id=None, quantity_delivered=3),
            ],
            "technicians": ["jperez"],
            "fullnames": {"jperez": "Juan Pérez"},
        }


class TestMaterialDeliveryUseCase(unittest.TestCase):
    def setUp(self):
        self.repository = FakeDeliveryRepository()
        self.use_case = InternalManagementUseCase(self.repository)

    def test_project_materials_skip_labor_and_expand_bundles(self):
        result = self.use_case.get_project_materials(1, "internal", "external")
        materials = {material["key"]: material for material in result["materials"]}

        self.assertEqual(["item-1", "item-2", "additional-7"], list(materials))
        self.assertEqual(1, materials["item-1"]["pending"])
        self.assertEqual(5, materials["item-1"]["stock"])
        self.assertIsNone(materials["item-2"]["stock"])
        self.assertTrue(materials["item-2"]["is_new"])
        self.assertEqual(9, materials["item-2"]["pending_material"]["id_pending_material"])
        self.assertEqual(0, materials["additional-7"]["pending"])
        self.assertEqual("Materiales varios (ítem 4)", materials["additional-7"]["group"])
        self.assertEqual([{"user": "jperez", "fullname_user": "Juan Pérez"}], result["technicians"])
        self.assertEqual("Juan Pérez", result["deliveries"][0]["technician_name"])
        self.assertEqual("item-1", result["deliveries"][0]["items"][0]["key"])

    def test_delivery_quantities_must_be_integers(self):
        with self.assertRaises(CustomAPIException):
            self.use_case.post_material_delivery(
                {"task_id": 1, "delivered_to": "jperez",
                 "items": [{"quotation_item_id": 1, "quantity": 1.5}]},
                "internal", "external",
            )

    def test_delivery_requires_technician_and_distinct_materials(self):
        with self.assertRaises(CustomAPIException):
            self.use_case.post_material_delivery(
                {"task_id": 1, "items": [{"quotation_item_id": 1, "quantity": 1}]},
                "internal", "external",
            )
        with self.assertRaises(CustomAPIException):
            self.use_case.post_material_delivery(
                {"task_id": 1, "delivered_to": "jperez", "items": [
                    {"quotation_item_id": 1, "quantity": 1},
                    {"quotation_item_id": 1, "quantity": 2},
                ]},
                "internal", "external",
            )

    def test_delivery_normalizes_the_payload(self):
        self.use_case.post_material_delivery(
            {"task_id": "1", "delivered_to": " jperez ", "observation": "  ",
             "items": [{"additional_material_id": 7, "quantity": 2.0}], "user": "bodega"},
            "internal", "external",
        )

        self.assertEqual({
            "task_id": 1,
            "delivered_to": "jperez",
            "observation": None,
            "items": [{"quotation_item_id": None, "additional_material_id": 7, "quantity": 2}],
            "user": "bodega",
        }, self.repository.delivery)

    def test_resolve_requires_integer_stock(self):
        with self.assertRaises(CustomAPIException):
            self.use_case.resolve_pending_material(
                9, {"product": "Soporte", "stock": 2.5}, "internal", "external"
            )


if __name__ == "__main__":
    unittest.main()
