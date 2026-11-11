import unittest
from unittest.mock import MagicMock

from sqlalchemy import select

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.models.db.commercial_followup import CommercialFollowup
from swagger_server.models.db.commercial_ticket_management import CommercialTicketManagement
from swagger_server.models.db.financial_ticket_management import FinancialTicketManagement
from swagger_server.models.db.history_area_ticket import HistoryAreaTicket
from swagger_server.models.db.inspection_technical import InspectionTechnical
from swagger_server.models.db.material_delivery_history import MaterialDeliveryHistory
from swagger_server.models.db.material_tech_ticket import MaterialTechTicket
from swagger_server.models.db.pending_material import PendingMaterial
from swagger_server.models.db.sale_quotation import SaleQuotation
from swagger_server.models.db.sale_quotation_item import SaleQuotationItem
from swagger_server.models.db.task_technical import TaskTechnical
from swagger_server.models.db.technical_ticket_management import TechnicalTicketManagement
from swagger_server.test.test_return_to_commercial import sqlite_repository
from swagger_server.uses_cases.internal_management_use_case import (
    InternalManagementUseCase,
)

RETURNED = 9


class TestReturnToTechnical(unittest.TestCase):
    def setUp(self):
        self.repository = sqlite_repository()
        with self.session() as session:
            session.add_all([
                InspectionTechnical(id_inspection=45, code="INS-45",
                                    status="Listo para cotizar",
                                    management_area="Comercial", next_area="Proyectos"),
                TechnicalTicketManagement(id_management_technical=4, inspection_id=45,
                                          status="Aprobado"),
                MaterialTechTicket(id_material=30, tech_ticket=4, other="Sensor",
                                   material_description="Sensor nuevo", quantity=2),
                PendingMaterial(id_pending_material=1, inspection_id=45,
                                material_tech_ticket_id=30, name_material="Sensor",
                                quantity=2, status=PendingMaterial.STATUS_PENDING),
                CommercialTicketManagement(id_management_commercial=9, ticket_id=45, status_id=7),
                SaleQuotation(id_quote=15, inspection_id=45, quote_number="PRF-15"),
                SaleQuotationItem(id_item=50, sale_quote_id=15, item_number=1, is_new=True,
                                  material_tech_ticket_id=30, description="Sensor nuevo",
                                  quantity=2),
            ])
            session.commit()

    def session(self):
        return self.repository.db_telearseg.session_factory()

    def return_it(self, **overrides):
        data = {"inspection_id": 45, "reason": "Faltan materiales", "user": "dmales", **overrides}
        return self.repository.return_to_technical(data, None, None)

    def assert_rejected(self, status_code, text, **overrides):
        with self.assertRaises(CustomAPIException) as error:
            self.return_it(**overrides)
        self.assertEqual(status_code, error.exception.status_code)
        self.assertIn(text, str(error.exception))

    def update(self, model, key, **fields):
        with self.session() as session:
            record = session.get(model, key)
            for field, value in fields.items():
                setattr(record, field, value)
            session.commit()

    def test_returns_record_to_technical(self):
        result = self.return_it()

        self.assertEqual(
            {"inspection_id": 45, "management_area": "Técnica",
             "technical_status": "Devuelto", "commercial_status_id": RETURNED},
            result,
        )
        with self.session() as session:
            inspection = session.get(InspectionTechnical, 45)
            self.assertEqual(("Técnica", "Comercial", "Devuelto a Técnica"),
                             (inspection.management_area, inspection.next_area,
                              inspection.status))
            self.assertEqual("Devuelto", session.get(TechnicalTicketManagement, 4).status)
            history = session.execute(select(HistoryAreaTicket)).scalar_one()
            self.assertEqual(("Comercial", "Técnica", "Faltan materiales"),
                             (history.previous_area, history.current_area, history.reason))
            followup = session.execute(select(CommercialFollowup)).scalar_one()
            self.assertIn("Faltan materiales", followup.observations)
            # La proforma y sus pendientes se conservan
            self.assertIsNotNone(session.get(SaleQuotationItem, 50))
            self.assertIsNotNone(session.get(PendingMaterial, 1))

    def test_rejected_commercial_can_be_returned(self):
        self.update(CommercialTicketManagement, 9, status_id=6)
        self.assertEqual("Técnica", self.return_it()["management_area"])

    def test_rejects_approved_commercial_management(self):
        self.update(CommercialTicketManagement, 9, status_id=5)
        self.assert_rejected(400, "aprobada")

    def test_rejects_already_returned(self):
        self.return_it()
        self.assert_rejected(400, "ya está en Técnica")
        self.update(InspectionTechnical, 45, management_area="Comercial")
        self.assert_rejected(400, "ya fue devuelto")

    def test_rejects_other_areas_and_finished(self):
        self.update(InspectionTechnical, 45, management_area="Proyectos")
        self.assert_rejected(400, "registros de Comercial")
        self.update(InspectionTechnical, 45, status="Finalizado")
        self.assert_rejected(400, "finalizado")

    def test_rejects_unknown_inspection_and_missing_records(self):
        self.assert_rejected(404, "Inspección no encontrada", inspection_id=99)
        with self.session() as session:
            session.add(InspectionTechnical(id_inspection=46, code="INS-46",
                                            management_area="Comercial"))
            session.commit()
        self.assert_rejected(400, "no tiene registro técnico", inspection_id=46)
        with self.session() as session:
            session.add(TechnicalTicketManagement(id_management_technical=5, inspection_id=46))
            session.commit()
        self.assert_rejected(404, "Gestión comercial no encontrada", inspection_id=46)

    def test_rejects_with_project_deliveries_or_financial(self):
        with self.session() as session:
            session.add(TaskTechnical(id_task=3, inspection_id=45, code="PRY-3"))
            session.commit()
        self.assert_rejected(400, "proyecto")
        with self.session() as session:
            session.delete(session.get(TaskTechnical, 3))
            session.add(MaterialDeliveryHistory(task_id=3, quote_id=15, delivered_to="jperez"))
            session.commit()
        self.assert_rejected(400, "materiales entregados")
        with self.session() as session:
            session.execute(MaterialDeliveryHistory.__table__.delete())
            session.add(FinancialTicketManagement(id_management_financial=1, ticket_id=45,
                                                  status="Cobrada"))
            session.commit()
        self.assert_rejected(400, "facturas cobradas")

    def test_commercial_is_frozen_while_returned(self):
        self.return_it()
        body = {"inspection_id": 45, "user": "dmales", "observations": "x"}
        with self.assertRaises(CustomAPIException) as error:
            self.repository.update_ticket_commercial(body, None, None)
        self.assertEqual(400, error.exception.status_code)
        with self.assertRaises(CustomAPIException) as error:
            self.repository.post_ticket_commercial(body, None, None, files=[])
        self.assertEqual(400, error.exception.status_code)

    def test_technical_correction_and_reapproval_resume_commercial(self):
        self.return_it()

        # El técnico corrige: vuelve a la cola de aprobación
        self.repository.update_ticket_technical(
            {"inspection_id": 45, "user": "tecnico", "description": "Corregido",
             "materials": [{"id_material": 30, "other": "Sensor", "quantity": 3,
                            "material_description": "Sensor nuevo"}]},
            None, None,
        )
        with self.session() as session:
            self.assertEqual("Pendiente aprobación",
                             session.get(TechnicalTicketManagement, 4).status)
            self.assertEqual(3, session.get(PendingMaterial, 1).quantity)

        self.repository.approve_technical_inspection(
            {"id_inspection": 45, "user": "jefe"}, None, None
        )
        with self.session() as session:
            inspection = session.get(InspectionTechnical, 45)
            self.assertEqual(("Comercial", "Listo para cotizar"),
                             (inspection.management_area, inspection.status))
            self.assertEqual(7, session.get(CommercialTicketManagement, 9).status_id)
            self.assertEqual(2, len(session.execute(select(CommercialFollowup)).all()))

    def test_removed_technical_product_unlinks_quotation_line(self):
        self.return_it()
        self.repository.update_ticket_technical(
            {"inspection_id": 45, "user": "tecnico", "materials": []}, None, None
        )
        with self.session() as session:
            self.assertIsNone(session.get(SaleQuotationItem, 50).material_tech_ticket_id)
            # Sin proforma aprobada ni catálogo: el pendiente se elimina
            self.assertIsNone(session.get(PendingMaterial, 1))

    def test_dashboard_counts_returned_as_pending_technical(self):
        self.assertEqual(0, self.repository.get_dashboard_counts({}, "i", "e")["pending_technical"])
        self.return_it()
        self.assertEqual(1, self.repository.get_dashboard_counts({}, "i", "e")["pending_technical"])


class TestReturnToTechnicalUseCase(unittest.TestCase):
    def test_validates_and_normalizes_payload(self):
        repository = MagicMock()
        use_case = InternalManagementUseCase(repository)
        with self.assertRaises(CustomAPIException):
            use_case.return_to_technical({"inspection_id": 45, "reason": " "}, None, None)
        use_case.return_to_technical(
            {"inspection_id": "45", "reason": " Motivo ", "user": " dmales "}, "i", "e"
        )
        repository.return_to_technical.assert_called_once_with(
            {"inspection_id": 45, "reason": "Motivo", "user": "dmales"}, "i", "e"
        )


if __name__ == "__main__":
    unittest.main()
