from datetime import datetime
import uuid
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
from swagger_server.models.db.material_tech_ticket import MaterialTechTicket
from swagger_server.models.db.pending_material import PendingMaterial
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
    MaterialTechTicket.__table__,
    PendingMaterial.__table__,
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
    if body.get("type") in ("Soporte", "Asistencia"):
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
            inspection.id_inspection, {"commitment_date": "2026-11-05T05:00:00.000Z"}, "i", "e"
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
        # Solo la "Listo para cotizar" está pendiente de Comercial
        self.assertEqual(1, counts["pending_commercial"])
        self.assertEqual(1, counts["finished_technical"])

    def test_dashboard_pending_commercial_matches_inspection_filter(self):
        # Mismas condiciones que GET /inspection?pending_commercial=true
        ready = create(self.repository, status="Listo para cotizar")
        create(self.repository, status="Listo para cotizar")
        create(self.repository)  # aún en Técnica
        self.repository.post_ticket_commercial(
            {"inspection_id": ready.id_inspection, "user": "dmales"},
            "i", "e", files=[],
        )

        counts = self.repository.get_dashboard_counts({}, "i", "e")

        self.assertEqual(1, counts["pending_commercial"])


class TestInspectionTypeFilters(unittest.TestCase):
    def test_pending_technical_excludes_support(self):
        sql = inspection_sql({"pending_technical": "true"})

        self.assertIn("inspection_technical.type IS DISTINCT FROM", sql)

    def test_pending_commercial_excludes_support(self):
        sql = inspection_sql({"pending_commercial": "true"})

        self.assertIn("inspection_technical.type IS DISTINCT FROM", sql)

    def test_technician_does_not_see_completed_assistances(self):
        # El técnico consulta /inspection?pending_technical=true&responsible_id=...
        sql = inspection_sql({
            "pending_technical": "true",
            "responsible_id": "4cc33865-1bad-4af4-9f18-3ce5dfb744b5",
        })

        self.assertIn("inspection_technical.management_status IS DISTINCT FROM", sql)

    def test_without_responsible_completed_assistances_are_listed(self):
        sql = inspection_sql({"pending_technical": "true"})

        self.assertNotIn("management_status", sql.split("WHERE", 1)[1])

    def test_without_pending_filters_support_is_listed(self):
        sql = inspection_sql({})

        self.assertNotIn("IS DISTINCT FROM", sql)

    def test_type_filter_accepts_several_types(self):
        sql = inspection_sql({"type": ["Soporte", "Asistencia"]})

        self.assertIn("inspection_technical.type IN", sql)
        self.assertNotIn("inspection_technical.type IS NULL", sql)

    def test_inspection_type_filter_includes_legacy_null(self):
        sql = inspection_sql({"type": ["Inspección"]})

        self.assertIn("inspection_technical.type IN", sql)
        self.assertIn("inspection_technical.type IS NULL", sql)


class TestAssistanceType(unittest.TestCase):
    """La Asistencia sigue el flujo normal (registro técnico con materiales);
    solo se diferencia de la Inspección por usar fecha inicio y fin."""

    def setUp(self):
        self.repository = sqlite_repository()

    def test_assistance_follows_flow_like_inspection(self):
        inspection = create(self.repository, type="Asistencia", status="Listo para cotizar")

        self.assertEqual("Asistencia", inspection.type)
        self.assertEqual("Comercial", inspection.management_area)
        self.assertEqual("Proyectos", inspection.next_area)

    def test_new_assistance_starts_in_technical(self):
        inspection = create(self.repository, type="Asistencia")

        self.assertEqual("Técnica", inspection.management_area)
        self.assertEqual("Comercial", inspection.next_area)

    def test_assistance_requires_dates(self):
        with self.assertRaises(CustomAPIException):
            create(self.repository, type="Asistencia", end_date=None)

    def test_assistance_accepts_technical_register_with_materials(self):
        inspection = create(self.repository, type="Asistencia")

        self.repository.post_ticket_technical(
            {
                "inspection_id": inspection.id_inspection,
                "user": "tecnico",
                "materials": [{"material_id": 7, "quantity": 2}],
            },
            "i", "e", files=[],
        )

        with self.repository.db_telearseg.session_factory() as session:
            register = session.execute(
                select(TechnicalTicketManagement).where(
                    TechnicalTicketManagement.inspection_id == inspection.id_inspection
                )
            ).scalar_one()
            materials = session.execute(
                select(MaterialTechTicket).where(
                    MaterialTechTicket.tech_ticket == register.id_management_technical
                )
            ).scalars().all()
            self.assertEqual("Pendiente aprobación", register.status)
            self.assertEqual([7], [material.material_id for material in materials])

    def test_approve_technical_register_moves_assistance_to_commercial(self):
        inspection = create(self.repository, type="Asistencia")
        self.repository.post_ticket_technical(
            {"inspection_id": inspection.id_inspection, "user": "tecnico"},
            "i", "e", files=[],
        )

        self.repository.approve_technical_inspection(
            {"id_inspection": inspection.id_inspection, "user": "jefe"}, "i", "e"
        )

        with self.repository.db_telearseg.session_factory() as session:
            approved = session.get(InspectionTechnical, inspection.id_inspection)
            register = session.execute(
                select(TechnicalTicketManagement).where(
                    TechnicalTicketManagement.inspection_id == inspection.id_inspection
                )
            ).scalar_one()
            self.assertTrue(approved.approve_support)
            self.assertEqual("Listo para cotizar", approved.status)
            self.assertEqual("Comercial", approved.management_area)
            self.assertEqual("Proyectos", approved.next_area)
            self.assertEqual("Aprobado", register.status)

        # Ya puede registrarse la gestión comercial
        self.repository.post_ticket_commercial(
            {"inspection_id": inspection.id_inspection, "user": "dmales"},
            "i", "e", files=[],
        )

    def test_dashboard_counts_assistance_as_pending_technical(self):
        create(self.repository, type="Asistencia")
        create(self.repository, type="Soporte")

        counts = self.repository.get_dashboard_counts({}, "i", "e")

        self.assertEqual(1, counts["pending_technical"])

    def test_legacy_approved_assistance_is_not_pending_technical(self):
        # Aprobada con el flujo anterior: pasó a Comercial sin registro técnico
        legacy = create(self.repository, type="Asistencia")
        with self.repository.db_telearseg.session_factory() as session:
            stored = session.get(InspectionTechnical, legacy.id_inspection)
            stored.approve_support = True
            stored.status = "Listo para cotizar"
            stored.management_area = "Comercial"
            session.commit()

        counts = self.repository.get_dashboard_counts({}, "i", "e")

        self.assertEqual(0, counts["pending_technical"])
        self.assertEqual(1, counts["pending_commercial"])

    def test_support_changed_to_assistance_needs_technical_approval(self):
        inspection = create(self.repository, type="Soporte")
        self.repository.approve_support(
            {"id_inspection": inspection.id_inspection, "user": "jefe"}, "i", "e"
        )

        self.repository.update_inspection_technical(
            inspection.id_inspection, {"type": "Asistencia", "user": "dmales"}, "i", "e"
        )

        with self.repository.db_telearseg.session_factory() as session:
            updated = session.get(InspectionTechnical, inspection.id_inspection)
            self.assertFalse(updated.approve_support)
            self.assertEqual("Comercial", updated.next_area)

    def test_pending_technical_includes_assistance(self):
        sql = inspection_sql({"pending_technical": "true"})

        # Solo excluye el Soporte y las Asistencias antiguas ya aprobadas
        self.assertEqual(1, sql.count("inspection_technical.type IS DISTINCT FROM"))
        self.assertIn("inspection_technical.approve_support IS", sql)


class TestApproveSupport(unittest.TestCase):
    def setUp(self):
        self.repository = sqlite_repository()

    def approve(self, inspection):
        self.repository.approve_support(
            {"id_inspection": inspection.id_inspection, "user": "jefe"}, "i", "e"
        )
        with self.repository.db_telearseg.session_factory() as session:
            return session.get(InspectionTechnical, inspection.id_inspection)

    def test_approve_support_sets_flag(self):
        inspection = create(self.repository, type="Soporte")

        approved = self.approve(inspection)

        self.assertTrue(approved.approve_support)
        self.assertEqual("jefe", approved.updated_by)

    def test_inspection_cannot_be_approved_as_support(self):
        inspection = create(self.repository)

        with self.assertRaises(CustomAPIException) as context:
            self.approve(inspection)

        self.assertEqual(400, context.exception.status_code)

    def test_assistance_cannot_be_approved_as_support(self):
        inspection = create(self.repository, type="Asistencia")

        with self.assertRaises(CustomAPIException) as context:
            self.approve(inspection)

        self.assertEqual(400, context.exception.status_code)

    def test_already_approved_support_is_rejected(self):
        inspection = create(self.repository, type="Soporte")
        self.approve(inspection)

        with self.assertRaises(CustomAPIException):
            self.approve(inspection)

    def test_approved_support_stays_in_technical(self):
        inspection = create(self.repository, type="Soporte")

        approved = self.approve(inspection)

        self.assertEqual("Técnica", approved.management_area)
        self.assertIsNone(approved.next_area)

    def test_approved_support_still_rejects_commercial_register(self):
        inspection = create(self.repository, type="Soporte")
        self.approve(inspection)

        with self.assertRaises(CustomAPIException) as context:
            self.repository.post_ticket_commercial(
                {"inspection_id": inspection.id_inspection, "user": "dmales"},
                "i", "e", files=[],
            )
        self.assertEqual(400, context.exception.status_code)

    def test_support_cannot_be_approved_as_technical_register(self):
        inspection = create(self.repository, type="Soporte")

        with self.assertRaises(CustomAPIException):
            self.repository.approve_technical_inspection(
                {"id_inspection": inspection.id_inspection, "user": "jefe"}, "i", "e"
            )

    def test_pending_approve_support_filter(self):
        sql = inspection_sql({"pending_approve_support": "true"})

        self.assertIn("inspection_technical.approve_support IS NOT", sql)


class TestTechnicalRegisterResponsibleFilter(unittest.TestCase):
    """GET /register-technical con responsible (rol técnico): las Asistencias solo
    salen si management_status no es Completado."""

    RESPONSIBLE = "fcea920f-7412-b5da-7be0-cf42b8c93759"
    OTHER = "05a0caad-4eb7-4a5a-bcd9-89d497564345"

    def setUp(self):
        self.repository = sqlite_repository()
        self.ids = {}
        for key, inspection_type, status, responsible in (
            ("inspection_completed", "Inspección", "Completado", self.RESPONSIBLE),
            ("assistance_completed", "Asistencia", "Completado", self.RESPONSIBLE),
            ("assistance_in_progress", "Asistencia", "En proceso", self.RESPONSIBLE),
            ("assistance_without_status", "Asistencia", None, self.RESPONSIBLE),
            ("other_responsible", "Asistencia", "En proceso", self.OTHER),
        ):
            inspection = create(
                self.repository,
                type=inspection_type,
                management_status=status,
                responsible_id=uuid.UUID(responsible),
            )
            self.repository.post_ticket_technical(
                {"inspection_id": inspection.id_inspection, "user": "tecnico"},
                "i", "e", files=[],
            )
            self.ids[inspection.id_inspection] = key

    def keys(self, filters):
        rows = self.repository.get_ticket_technical(filters, "i", "e")
        return {self.ids[ticket.id_inspection] for _, ticket, _ in rows}

    def test_responsible_hides_completed_assistances(self):
        self.assertEqual(
            {"inspection_completed", "assistance_in_progress", "assistance_without_status"},
            self.keys({"responsible": uuid.UUID(self.RESPONSIBLE)}),
        )

    def test_without_responsible_lists_everything(self):
        self.assertEqual(set(self.ids.values()), self.keys({}))

    def test_type_filter(self):
        self.assertEqual({"inspection_completed"}, self.keys({"type": ["Inspección"]}))
        self.assertEqual(
            {"assistance_in_progress", "assistance_without_status"},
            self.keys({"responsible": uuid.UUID(self.RESPONSIBLE), "type": ["Asistencia"]}),
        )


if __name__ == "__main__":
    unittest.main()
