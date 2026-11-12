"""Asistencias: al aprobarse la gestión comercial (estado 5) pasan directo a
Financiera y descuentan el stock con una entrega automática (sección 3 de
docs/logica-negocio.md)."""
from types import SimpleNamespace
import unittest

from sqlalchemy import select

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.models.db.commercial_ticket_management import CommercialTicketManagement
from swagger_server.models.db.history_area_ticket import HistoryAreaTicket
from swagger_server.models.db.inspection_technical import InspectionTechnical
from swagger_server.models.db.material_delivery_detail import MaterialDeliveryDetail
from swagger_server.models.db.material_delivery_history import MaterialDeliveryHistory
from swagger_server.models.db.pending_material import PendingMaterial
from swagger_server.models.db.technical_equipment import TechnicalEquipment
from swagger_server.test.test_inspection_ready_for_project import (
    FakeSession,
    build_repository,
    inspection,
)
from swagger_server.test.test_return_to_commercial import sqlite_repository
from swagger_server.uses_cases.internal_management_use_case import (
    InternalManagementUseCase,
)

APPROVED = 5
PENDING = 7


def quotation(camera_quantity=4):
    """Cámara del catálogo, producto nuevo, mano de obra y materiales varios
    con un conector y otra cámara (la cámara se valida por la suma: 4 + 1)."""
    return {
        "subtotal": 100, "total": 112,
        "items": [
            {"item": 1, "material_id": 100, "quantity": camera_quantity, "total": 40},
            {"item": 2, "material_id": None, "is_new": True, "description": "Soporte personalizado",
             "model": "SP-1", "quantity": 3, "base_price": 10, "total": 30},
            {"item": 3, "is_labor": True, "description": "Instalación", "quantity": 1, "total": 20},
            {"item": 4, "is_bundle": True, "quantity": 1, "total": 22, "components": [
                {"material_id": 200, "quantity": 20, "total": 20},
                {"material_id": 100, "quantity": 1, "total": 2},
            ]},
        ],
    }


class TestAssistanceGoesToFinancial(unittest.TestCase):
    def setUp(self):
        self.repository = sqlite_repository()
        with self.session() as session:
            session.add_all([
                InspectionTechnical(id_inspection=50, code="INS-50", type="Asistencia",
                                    status="Listo para cotizar",
                                    management_area="Comercial", next_area="Proyectos"),
                CommercialTicketManagement(id_management_commercial=9, ticket_id=50,
                                           status_id=PENDING),
                TechnicalEquipment(id_equipment=100, product="Cámara IP", stock=5),
                TechnicalEquipment(id_equipment=200, product="Conector RJ45", stock=30),
            ])
            session.commit()

    def session(self):
        return self.repository.db_telearseg.session_factory()

    def update(self, **body):
        body = {"inspection_id": 50, "user": "ventas", "sales_code": "V1", **body}
        self.repository.update_ticket_commercial(body, "i", "e", files=[])

    def approve(self, sale_quotation=None):
        self.update(status_id=APPROVED, sale_quotation=sale_quotation or quotation())

    def stock(self):
        with self.session() as session:
            return {
                record.id_equipment: record.stock
                for record in session.execute(select(TechnicalEquipment)).scalars()
            }

    def deliveries(self):
        with self.session() as session:
            return session.execute(select(MaterialDeliveryHistory)).scalars().all()

    def assert_rejected(self, text, call):
        with self.assertRaises(CustomAPIException) as error:
            call()
        self.assertEqual(400, error.exception.status_code)
        self.assertIn(text, str(error.exception))

    def test_approval_moves_assistance_directly_to_financial(self):
        self.approve()

        with self.session() as session:
            inspection = session.get(InspectionTechnical, 50)
            history = session.execute(select(HistoryAreaTicket)).scalar_one()
        self.assertEqual(("Financiera", "Financiera"),
                         (inspection.management_area, inspection.next_area))
        self.assertEqual(("Comercial", "Financiera"),
                         (history.previous_area, history.current_area))

    def test_approval_discounts_stock_with_the_proforma_quantities(self):
        self.approve()

        # Cámara: 4 del ítem + 1 de materiales varios; conector: 20
        self.assertEqual({100: 0, 200: 10}, self.stock())
        history = self.deliveries()[0]
        self.assertEqual((None, None, "ventas", MaterialDeliveryHistory.ASSISTANCE_OBSERVATION),
                         (history.task_id, history.delivered_to, history.created_by,
                          history.observation))

    def test_labor_and_bundle_line_are_not_delivered(self):
        self.approve()

        with self.session() as session:
            details = session.execute(select(MaterialDeliveryDetail)).scalars().all()
        lines = sorted(
            (detail.additional_material_id is not None, detail.material_id or 0,
             detail.quantity_delivered)
            for detail in details
        )
        # Ítems: cámara (4) y producto nuevo (sin material, 3); componentes: conector y cámara
        self.assertEqual(
            [(False, 0, 3), (False, 100, 4), (True, 100, 1), (True, 200, 20)], lines
        )

    def test_new_product_is_delivered_with_its_pending_without_stock(self):
        self.approve()

        with self.session() as session:
            pending = session.execute(select(PendingMaterial)).scalar_one()
            detail = session.execute(
                select(MaterialDeliveryDetail).where(MaterialDeliveryDetail.material_id.is_(None))
            ).scalar_one()
        self.assertEqual(pending.id_pending_material, detail.pending_material_id)

        # Al crearlo en el catálogo, su stock ya resta lo usado en la asistencia
        equipment_id = self.repository.resolve_pending_material(
            pending.id_pending_material,
            {"product": "Soporte personalizado", "stock": 10, "user": "bodega"},
            "i", "e",
        )
        with self.session() as session:
            self.assertEqual(7, session.get(TechnicalEquipment, equipment_id).stock)

    def test_insufficient_stock_rejects_approval_without_changes(self):
        # Cámara: 5 + 1 > 5 disponibles
        self.assert_rejected(
            'Stock insuficiente de "Cámara IP": disponible 5, requerido 6',
            lambda: self.approve(quotation(camera_quantity=5)),
        )

        self.assertEqual({100: 5, 200: 30}, self.stock())
        self.assertEqual([], self.deliveries())
        with self.session() as session:
            self.assertEqual("Comercial", session.get(InspectionTechnical, 50).management_area)
            self.assertEqual(PENDING, session.get(CommercialTicketManagement, 9).status_id)

    def test_saving_pending_proforma_does_not_discount(self):
        self.update(status_id=PENDING, sale_quotation=quotation())
        self.update(sale_quotation=quotation())

        self.assertEqual({100: 5, 200: 30}, self.stock())
        self.assertEqual([], self.deliveries())

    def test_post_with_approved_status_also_discounts(self):
        with self.session() as session:
            session.delete(session.get(CommercialTicketManagement, 9))
            session.commit()

        self.repository.post_ticket_commercial(
            {"inspection_id": 50, "user": "ventas", "sales_code": "V1",
             "status_id": APPROVED, "sale_quotation": quotation()},
            "i", "e", files=[],
        )

        self.assertEqual({100: 0, 200: 10}, self.stock())
        with self.session() as session:
            self.assertEqual("Financiera", session.get(InspectionTechnical, 50).management_area)

    def test_approved_assistance_cannot_change_proforma_or_status(self):
        self.approve()

        self.assert_rejected("ya fue aprobada", lambda: self.approve())
        self.assert_rejected("ya fue aprobada", lambda: self.update(status_id=6))
        self.assert_rejected("ya fue aprobada", lambda: self.repository.post_ticket_commercial(
            {"inspection_id": 50, "user": "ventas", "status_id": APPROVED}, "i", "e", files=[],
        ))
        # Otros campos sí se pueden editar, sin volver a descontar
        self.update(observations="Factura al cliente final")
        self.assertEqual({100: 0, 200: 10}, self.stock())
        self.assertEqual(1, len(self.deliveries()))

    def test_assistance_cannot_be_returned_to_commercial(self):
        self.approve()

        self.assert_rejected("no se pueden devolver a Comercial", lambda: (
            self.repository.return_to_commercial(
                {"inspection_id": 50, "reason": "x", "user": "conta"}, "i", "e"
            )
        ))

    def test_projects_to_financial_step_is_rejected(self):
        self.approve()

        self.assert_rejected("directo de Comercial a Financiera", lambda: (
            self.repository.approve_ticket_commercial(
                {"id_commercial_ticket": 9, "user": "proyectos"}, "i", "e"
            )
        ))

    def test_proforma_without_materials_creates_no_delivery(self):
        self.approve({"items": [
            {"item": 1, "is_labor": True, "description": "Visita", "quantity": 1, "total": 20},
        ]})

        self.assertEqual([], self.deliveries())
        with self.session() as session:
            self.assertEqual("Financiera", session.get(InspectionTechnical, 50).management_area)

    def test_inspection_still_goes_to_projects_without_discount(self):
        with self.session() as session:
            session.get(InspectionTechnical, 50).type = "Inspección"
            session.commit()

        self.approve()

        self.assertEqual({100: 5, 200: 30}, self.stock())
        with self.session() as session:
            self.assertEqual("Proyectos", session.get(InspectionTechnical, 50).management_area)

    def test_legacy_assistance_in_projects_keeps_previous_flow(self):
        with self.session() as session:
            inspection = session.get(InspectionTechnical, 50)
            inspection.management_area = "Proyectos"
            inspection.next_area = "Financiera"
            session.get(CommercialTicketManagement, 9).status_id = APPROVED
            session.commit()

        self.repository.approve_ticket_commercial(
            {"id_commercial_ticket": 9, "user": "proyectos"}, "i", "e"
        )

        self.assertEqual({100: 5, 200: 30}, self.stock())
        with self.session() as session:
            self.assertEqual("Financiera", session.get(InspectionTechnical, 50).management_area)


def listed(**overrides):
    """Inspección del listado con los campos que agregaron los tipos."""
    return inspection(start_date=None, end_date=None, management_status=None,
                      approve_support=None, **overrides)


class TestAssistanceIsNotReadyForProject(unittest.TestCase):
    def test_ready_flag_is_false_for_assistance_outside_projects(self):
        rows = [
            (listed(id_inspection=1, type="Asistencia", management_area="Financiera"),
             None, 5, "Aprobada", None, None, None, None, None, None, None, None, []),
            (listed(id_inspection=2, type="Asistencia", management_area="Proyectos"),
             None, 5, "Aprobada", None, None, None, None, None, None, None, None, []),
            (listed(id_inspection=3, type="Inspección", management_area="Proyectos"),
             None, 5, "Aprobada", None, None, None, None, None, None, None, None, []),
        ]
        repository = SimpleNamespace(get_inspection_technical=lambda *args: rows)

        result = InternalManagementUseCase(repository).get_inspection_technical(
            {}, {}, "i", "e"
        )

        # Solo la Asistencia antigua (en Proyectos) sigue creando proyecto
        self.assertEqual([False, True, True], [row["ready_for_project"] for row in result])

    def test_ready_filter_keeps_only_legacy_assistances(self):
        session = FakeSession()

        build_repository(session).get_inspection_technical(
            {"ready_for_project": "true"}, "i", "e"
        )

        sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("type IS DISTINCT FROM 'Asistencia'", sql)
        self.assertIn("management_area = 'Proyectos'", sql)


if __name__ == "__main__":
    unittest.main()
