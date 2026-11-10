from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.models.db import Base
from swagger_server.models.db.commercial_followup import CommercialFollowup
from swagger_server.models.db.commercial_ticket_management import CommercialTicketManagement
from swagger_server.models.db.financial_ticket_management import FinancialTicketManagement
from swagger_server.models.db.history_area_ticket import HistoryAreaTicket
from swagger_server.models.db.inspection_technical import InspectionTechnical
from swagger_server.models.db.material_delivery_history import MaterialDeliveryHistory
from swagger_server.models.db.sale_quotation import SaleQuotation
from swagger_server.models.db.task_technical import TaskTechnical
from swagger_server.repository.internal_management_repository import (
    InternalManagementRepository,
)
from swagger_server.test.test_material_delivery import TABLES
from swagger_server.uses_cases.internal_management_use_case import (
    InternalManagementUseCase,
)

EXTRA_TABLES = [
    CommercialTicketManagement.__table__,
    CommercialFollowup.__table__,
    FinancialTicketManagement.__table__,
    HistoryAreaTicket.__table__,
]


def sqlite_repository():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def attach_schemas(connection, _):
        for schema in ("internal_management", "technical"):
            connection.execute(f"ATTACH DATABASE ':memory:' AS {schema}")

    Base.metadata.create_all(engine, tables=TABLES + EXTRA_TABLES)
    repository = InternalManagementRepository.__new__(InternalManagementRepository)
    repository.db_telearseg = SimpleNamespace(session_factory=sessionmaker(engine))
    return repository


class TestReturnToCommercial(unittest.TestCase):
    def setUp(self):
        self.repository = sqlite_repository()
        with self.session() as session:
            session.add_all([
                InspectionTechnical(id_inspection=45, code="INS-45", status="En proceso",
                                    management_area="Financiera", next_area="Financiera"),
                CommercialTicketManagement(id_management_commercial=9, ticket_id=45, status_id=5),
                SaleQuotation(id_quote=15, inspection_id=45, quote_number="PRF-15"),
                TaskTechnical(id_task=3, inspection_id=45, code="PRY-3"),
            ])
            session.commit()

    def session(self):
        return self.repository.db_telearseg.session_factory()

    def return_it(self, **overrides):
        data = {"inspection_id": 45, "reason": "Cambios del cliente", "user": "dmales", **overrides}
        return self.repository.return_to_commercial(data, None, None)

    def assert_rejected(self, status_code, text, **overrides):
        with self.assertRaises(CustomAPIException) as error:
            self.return_it(**overrides)
        self.assertEqual(status_code, error.exception.status_code)
        self.assertIn(text, str(error.exception))
        with self.session() as session:
            self.assertEqual(5, session.get(CommercialTicketManagement, 9).status_id)

    def update(self, model, key, **fields):
        with self.session() as session:
            record = session.get(model, key)
            for field, value in fields.items():
                setattr(record, field, value)
            session.commit()

    def test_returns_record_to_commercial_as_pending(self):
        result = self.return_it()

        self.assertEqual(
            {"inspection_id": 45, "previous_area": "Financiera",
             "management_area": "Comercial", "commercial_status_id": 7},
            result,
        )
        with self.session() as session:
            inspection = session.get(InspectionTechnical, 45)
            self.assertEqual(("Comercial", "Proyectos"),
                             (inspection.management_area, inspection.next_area))
            self.assertEqual("dmales", session.get(CommercialTicketManagement, 9).updated_by)
            history = session.execute(select(HistoryAreaTicket)).scalar_one()
            self.assertEqual(("Financiera", "Comercial"),
                             (history.previous_area, history.current_area))
            followup = session.execute(select(CommercialFollowup)).scalar_one()
            self.assertEqual(9, followup.management_commercial_id)
            self.assertIn("Cambios del cliente", followup.observations)
            # 1b: el proyecto se conserva
            self.assertIsNotNone(session.get(TaskTechnical, 3))

    def test_returns_from_projects(self):
        self.update(InspectionTechnical, 45, management_area="Proyectos")
        self.assertEqual("Proyectos", self.return_it()["previous_area"])

    def test_rejects_unknown_inspection(self):
        self.assert_rejected(404, "Inspección no encontrada", inspection_id=99)

    def test_rejects_record_already_in_commercial_or_technical(self):
        self.update(InspectionTechnical, 45, management_area="Comercial")
        self.assert_rejected(400, "ya está en Comercial")
        self.update(InspectionTechnical, 45, management_area="Técnica")
        self.assert_rejected(400, "Proyectos o Financiera")

    def test_rejects_finished_record(self):
        self.update(InspectionTechnical, 45, status="Finalizado")
        self.assert_rejected(400, "finalizado")

    def test_rejects_commercial_management_not_approved(self):
        # La última gestión comercial es la que manda
        with self.session() as session:
            session.add(CommercialTicketManagement(id_management_commercial=10,
                                                   ticket_id=45, status_id=7))
            session.commit()
        with self.assertRaises(CustomAPIException) as error:
            self.return_it()
        self.assertEqual(400, error.exception.status_code)
        self.assertIn("no está aprobada", str(error.exception))

    def test_rejects_when_materials_were_delivered(self):
        with self.session() as session:
            session.add(MaterialDeliveryHistory(task_id=3, quote_id=15, delivered_to="jperez"))
            session.commit()
        self.assert_rejected(400, "materiales entregados")

    def test_rejects_when_there_are_financial_managements(self):
        with self.session() as session:
            session.add(FinancialTicketManagement(id_management_financial=1, ticket_id=45,
                                                  status="Facturada"))
            session.commit()
        self.assert_rejected(400, "gestiones financieras")
        self.update(FinancialTicketManagement, 1, status="Cobrada")
        self.assert_rejected(400, "facturas cobradas")


class TestReturnToCommercialUseCase(unittest.TestCase):
    def setUp(self):
        self.repository = MagicMock()
        self.use_case = InternalManagementUseCase(self.repository)

    def test_requires_reason_and_integer_inspection(self):
        for body in ({"inspection_id": 45}, {"inspection_id": 45, "reason": "  "},
                     {"inspection_id": "x", "reason": "Motivo"}, None):
            with self.subTest(body=body):
                with self.assertRaises(CustomAPIException) as error:
                    self.use_case.return_to_commercial(body, None, None)
                self.assertEqual(400, error.exception.status_code)
        self.repository.return_to_commercial.assert_not_called()

    def test_normalizes_payload(self):
        self.use_case.return_to_commercial(
            {"inspection_id": "45", "reason": " Motivo ", "user": " dmales "}, "i", "e"
        )
        self.repository.return_to_commercial.assert_called_once_with(
            {"inspection_id": 45, "reason": "Motivo", "user": "dmales"}, "i", "e"
        )


if __name__ == "__main__":
    unittest.main()
