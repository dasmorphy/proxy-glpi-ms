from datetime import datetime
from types import SimpleNamespace
import unittest

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.models.db import Base
from swagger_server.models.db.commercial_ticket_management import CommercialTicketManagement
from swagger_server.models.db.financial_ticket_management import FinancialTicketManagement
from swagger_server.models.db.history_area_ticket import HistoryAreaTicket
from swagger_server.models.db.inspection_documents import InspectionDocuments
from swagger_server.models.db.inspection_technical import InspectionTechnical
from swagger_server.models.db.task_technical import TaskTechnical
from swagger_server.models.db.technical_ticket_management import TechnicalTicketManagement
from swagger_server.repository.internal_management_repository import (
    InternalManagementRepository,
)


TABLES = [
    InspectionTechnical.__table__,
    InspectionDocuments.__table__,
    HistoryAreaTicket.__table__,
    TechnicalTicketManagement.__table__,
    CommercialTicketManagement.__table__,
    FinancialTicketManagement.__table__,
    TaskTechnical.__table__,
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

    Base.metadata.create_all(engine, tables=TABLES)
    repository = InternalManagementRepository.__new__(InternalManagementRepository)
    repository.db_telearseg = SimpleNamespace(session_factory=sessionmaker(engine))
    return repository


SUPPORT_DATES = {"start_date": "2026-10-30T13:00:00Z", "end_date": "2026-10-31T15:30:00Z"}


def create(repository, **body):
    if body.get("type") == "Soporte":
        body = {**SUPPORT_DATES, **body}
    body = {"title_ticket": "Ticket", "user": "dmales", **body}
    repository.post_inspection_technical(body, "internal", "external", files=[])
    with repository.db_telearseg.session_factory() as session:
        return session.execute(
            select(InspectionTechnical).order_by(InspectionTechnical.id_inspection.desc())
        ).scalars().first()


class FakeSession:
    """Guarda la consulta de get_inspection_technical sin ejecutarla en Postgres."""

    def __init__(self):
        self.statement = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement):
        self.statement = statement
        return SimpleNamespace(all=lambda: [])


def inspection_sql(filters):
    session = FakeSession()
    repository = InternalManagementRepository.__new__(InternalManagementRepository)
    repository.db_telearseg = SimpleNamespace(session_factory=lambda: session)
    repository.get_inspection_technical(filters, "internal", "external")
    return str(session.statement.compile())


class TestInspectionType(unittest.TestCase):
    def setUp(self):
        self.repository = sqlite_repository()

    def test_type_defaults_to_inspection(self):
        inspection = create(self.repository, status="Listo para cotizar")

        self.assertEqual("Inspección", inspection.type)
        self.assertEqual("Comercial", inspection.management_area)
        self.assertEqual("Proyectos", inspection.next_area)

    def test_support_stays_in_technical_area(self):
        inspection = create(self.repository, type="Soporte", status="Listo para cotizar")

        self.assertEqual("Soporte", inspection.type)
        self.assertEqual("Listo para cotizar", inspection.status)
        self.assertEqual("Técnica", inspection.management_area)
        self.assertIsNone(inspection.next_area)

    def test_support_dates_are_saved_in_utc_without_zone(self):
        inspection = create(self.repository, type="Soporte")

        self.assertEqual(datetime(2026, 10, 30, 13, 0), inspection.start_date)
        self.assertEqual(datetime(2026, 10, 31, 15, 30), inspection.end_date)

    def test_support_requires_both_dates(self):
        with self.assertRaises(CustomAPIException) as context:
            create(self.repository, type="Soporte", end_date=None)

        self.assertEqual(400, context.exception.status_code)

    def test_support_end_date_cannot_be_before_start_date(self):
        with self.assertRaises(CustomAPIException) as context:
            create(self.repository, type="Soporte",
                   start_date="2026-10-31T00:00:00", end_date="2026-10-30T00:00:00")

        self.assertEqual(400, context.exception.status_code)

    def test_update_validates_resulting_support_dates(self):
        inspection = create(self.repository, type="Soporte")

        with self.assertRaises(CustomAPIException):
            self.repository.update_inspection_technical(
                inspection.id_inspection, {"end_date": "2026-10-01T00:00:00Z"}, "i", "e"
            )

        self.repository.update_inspection_technical(
            inspection.id_inspection, {"end_date": "2026-11-02T00:00:00Z"}, "i", "e"
        )
        with self.repository.db_telearseg.session_factory() as session:
            updated = session.get(InspectionTechnical, inspection.id_inspection)
            self.assertEqual(datetime(2026, 11, 2), updated.end_date)

    def test_update_saves_commitment_date(self):
        inspection = create(self.repository)

        self.repository.update_inspection_technical(
            inspection.id_inspection, {"commitment_date": "2026-11-05T05:00:00Z"}, "i", "e"
        )

        with self.repository.db_telearseg.session_factory() as session:
            updated = session.get(InspectionTechnical, inspection.id_inspection)
            self.assertEqual(datetime(2026, 11, 5, 5, 0), updated.commitment_date)

    def test_inspection_does_not_require_support_dates(self):
        inspection = create(self.repository)

        self.assertIsNone(inspection.start_date)
        self.assertIsNone(inspection.end_date)

    def test_invalid_type_is_rejected(self):
        with self.assertRaises(CustomAPIException) as context:
            create(self.repository, type="Otro")

        self.assertEqual(400, context.exception.status_code)

    def test_update_does_not_move_support_to_commercial(self):
        inspection = create(self.repository, type="Soporte")

        self.repository.update_inspection_technical(
            inspection.id_inspection, {"status": "Listo para cotizar"}, "i", "e"
        )

        with self.repository.db_telearseg.session_factory() as session:
            updated = session.get(InspectionTechnical, inspection.id_inspection)
            self.assertEqual("Técnica", updated.management_area)
            self.assertIsNone(updated.next_area)

    def test_update_to_support_is_rejected_after_technical_register(self):
        inspection = create(self.repository)
        with self.repository.db_telearseg.session_factory() as session:
            session.add(TechnicalTicketManagement(inspection_id=inspection.id_inspection))
            session.commit()

        with self.assertRaises(CustomAPIException) as context:
            self.repository.update_inspection_technical(
                inspection.id_inspection, {"type": "Soporte"}, "i", "e"
            )

        self.assertEqual(400, context.exception.status_code)

    def test_support_back_to_inspection_restores_next_area(self):
        inspection = create(self.repository, type="Soporte")

        self.repository.update_inspection_technical(
            inspection.id_inspection, {"type": "Inspección"}, "i", "e"
        )

        with self.repository.db_telearseg.session_factory() as session:
            updated = session.get(InspectionTechnical, inspection.id_inspection)
            self.assertEqual("Inspección", updated.type)
            self.assertEqual("Comercial", updated.next_area)

    def test_technical_register_is_rejected_for_support(self):
        inspection = create(self.repository, type="Soporte")

        with self.assertRaises(CustomAPIException) as context:
            self.repository.post_ticket_technical(
                {"inspection_id": inspection.id_inspection, "user": "dmales"},
                "i", "e", files=[],
            )

        self.assertEqual(400, context.exception.status_code)

    def test_commercial_register_is_rejected_for_support(self):
        inspection = create(self.repository, type="Soporte")

        with self.assertRaises(CustomAPIException) as context:
            self.repository.post_ticket_commercial(
                {"inspection_id": inspection.id_inspection, "user": "dmales"},
                "i", "e", files=[],
            )

        self.assertEqual(400, context.exception.status_code)

    def test_dashboard_counts_exclude_support(self):
        create(self.repository, status="Listo para cotizar")
        create(self.repository, type="Soporte", status="Listo para cotizar")
        legacy = create(self.repository)
        with self.repository.db_telearseg.session_factory() as session:
            session.get(InspectionTechnical, legacy.id_inspection).type = None
            session.commit()

        counts = self.repository.get_dashboard_counts({}, "i", "e")

        # La de Soporte no cuenta; la antigua (type NULL) sí
        self.assertEqual(2, counts["pending_technical"])
        self.assertEqual(2, counts["pending_commercial"])
        self.assertEqual(1, counts["finished_technical"])


class TestInspectionTypeFilters(unittest.TestCase):
    def test_pending_technical_excludes_support(self):
        sql = inspection_sql({"pending_technical": "true"})

        self.assertIn("inspection_technical.type IS DISTINCT FROM", sql)

    def test_pending_commercial_excludes_support(self):
        sql = inspection_sql({"pending_commercial": "true"})

        self.assertIn("inspection_technical.type IS DISTINCT FROM", sql)

    def test_without_pending_filters_support_is_listed(self):
        sql = inspection_sql({})

        self.assertNotIn("IS DISTINCT FROM", sql)


if __name__ == "__main__":
    unittest.main()
