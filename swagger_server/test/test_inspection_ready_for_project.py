from datetime import datetime
from types import SimpleNamespace
import unittest

from swagger_server.repository.internal_management_repository import (
    InternalManagementRepository,
)
from swagger_server.uses_cases.internal_management_use_case import (
    InternalManagementUseCase,
)


def inspection(**overrides):
    values = {
        "id_inspection": 7,
        "management_area": "Proyectos",
        "next_area": "Financiera",
        "title_ticket": "Inspeccion de sitio",
        "status": "Listo para cotizar",
        "contact": "Daniel",
        "commitment_date": None,
        "code": "INS-2026-0007",
        "case_type": "Interno",
        "client_id": 3,
        "ubication_id": 4,
        "priority": "Alta",
        "client_name": "Cliente",
        "ubication_name": "Guayas",
        "responsible_id": None,
        "responsible_name": None,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 2),
        "created_by": "dmales",
        "updated_by": "dmales",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeInspectionRepository:
    def __init__(self, rows):
        self.rows = rows
        self.filters = None

    def get_inspection_technical(self, filters, internal, external):
        self.filters = filters
        return self.rows


class FakeSession:
    def __init__(self):
        self.statement = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement):
        self.statement = statement
        return SimpleNamespace(all=lambda: [])


def build_repository(session):
    repository = InternalManagementRepository.__new__(InternalManagementRepository)
    repository.db_telearseg = SimpleNamespace(session_factory=lambda: session)
    return repository


class TestInspectionReadyForProjectUseCase(unittest.TestCase):
    def test_serializes_commercial_status_and_ready_flag(self):
        repository = FakeInspectionRepository([
            (inspection(id_inspection=1), None, 5, "Aprobada", 11),
            (inspection(id_inspection=2), 40, 5, "Aprobada", 12),
            (inspection(id_inspection=3), None, 6, "Rechazada", None),
            (inspection(id_inspection=4), None, None, None, None),
        ])
        use_case = InternalManagementUseCase(repository)

        result = use_case.get_inspection_technical(
            {}, {"ready_for_project": "true"}, "internal", "external"
        )

        self.assertEqual("true", repository.filters["ready_for_project"])
        self.assertEqual("Aprobada", result[0]["commercial_status"])
        self.assertEqual(5, result[0]["commercial_status_id"])
        self.assertEqual(
            [True, False, False, False],
            [row["ready_for_project"] for row in result],
        )
        self.assertEqual(40, result[1]["project_id"])
        self.assertEqual(11, result[0]["technical_id"])
        self.assertIsNone(result[3]["technical_id"])


class TestInspectionReadyForProjectRepository(unittest.TestCase):
    def test_selects_commercial_status_columns(self):
        session = FakeSession()

        build_repository(session).get_inspection_technical({}, "internal", "external")

        sql = str(session.statement)
        self.assertIn("commercial_status_id", sql)
        self.assertIn("commmercial_ticket_status.name", sql)
        self.assertNotIn("task_technical.id_task IS NULL", sql)
        self.assertIn("technical_id", sql)

    def test_ready_for_project_filters_approved_without_project(self):
        session = FakeSession()

        build_repository(session).get_inspection_technical(
            {"ready_for_project": "true"}, "internal", "external"
        )

        sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("task_technical.id_task IS NULL", sql)
        self.assertIn("= 5", sql)

    def test_pending_technical_filters_inspections_without_technical_record(self):
        session = FakeSession()

        build_repository(session).get_inspection_technical(
            {"pending_technical": "true"}, "internal", "external"
        )

        sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn(
            "technical_ticket_management.id_management_technical IS NULL", sql
        )


if __name__ == "__main__":
    unittest.main()
