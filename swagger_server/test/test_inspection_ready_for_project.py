from datetime import datetime
from decimal import Decimal
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
            (inspection(id_inspection=1), None, 5, "Aprobada", 11, "0991234567001", "Empresa SA", 9, 30, Decimal("862.41"), [
                SimpleNamespace(
                    id_document=3,
                    document_path="inspection-documents/1_a1b2c3d4e5f6_informe_final.pdf",
                    name_document=None,
                    type_document="application/pdf",
                    created_at=datetime(2026, 1, 3),
                ),
            ]),
            (inspection(id_inspection=2), 40, 5, "Aprobada", 12, None, None, None, None, None, []),
            (inspection(id_inspection=3), None, 6, "Rechazada", None, None, None, None, None, None, []),
            (inspection(id_inspection=4), None, None, None, None, None, None, None, None, None, []),
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
        self.assertEqual(9, result[0]["client_company_id"])
        self.assertEqual(11, result[0]["technical_id"])
        self.assertIsNone(result[3]["technical_id"])
        self.assertEqual("0991234567001", result[0]["identity"])
        self.assertIsNone(result[1]["identity"])
        self.assertEqual(30, result[0]["sale_quote_id"])
        self.assertIsNone(result[1]["sale_quote_id"])
        self.assertEqual(Decimal("862.41"), result[0]["sale_quote_total"])
        self.assertEqual(
            [{
                "id_document": 3,
                "document_path": "inspection-documents/1_a1b2c3d4e5f6_informe_final.pdf",
                "document_name": "informe_final.pdf",
                "type": "application/pdf",
                "created_at": datetime(2026, 1, 3),
            }],
            result[0]["documents"],
        )
        self.assertEqual([], result[1]["documents"])


class TestInspectionReadyForProjectRepository(unittest.TestCase):
    def test_selects_commercial_status_columns(self):
        session = FakeSession()

        build_repository(session).get_inspection_technical({}, "internal", "external")

        sql = str(session.statement)
        self.assertIn("commercial_status_id", sql)
        self.assertIn("commmercial_ticket_status.name", sql)
        self.assertNotIn("task_technical.id_task IS NULL", sql)
        self.assertIn("technical_id", sql)
        self.assertIn("client_companies.identity", sql)
        self.assertIn("client_companies.id_company AS client_company_id", sql)
        self.assertIn("AS sale_quote_id", sql)
        self.assertIn("AS sale_quote_total", sql)
        self.assertIn("client_companies.id_company = technical.clients.client_company_id", sql)
        self.assertIn("technical.clients.id_client = internal_management.inspection_technical.client_id", sql)

    def test_ready_for_project_filters_approved_without_project(self):
        session = FakeSession()

        build_repository(session).get_inspection_technical(
            {"ready_for_project": "true"}, "internal", "external"
        )

        sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("task_technical.id_task IS NULL", sql)
        self.assertIn("= 5", sql)

    def test_groups_documents_by_inspection_without_duplicating_rows(self):
        first, second = inspection(id_inspection=1), inspection(id_inspection=2)
        documents = [
            SimpleNamespace(id_document=1, inspection_id=1, document_path="a.pdf"),
            SimpleNamespace(id_document=2, inspection_id=1, document_path="b.png"),
        ]

        class Session(FakeSession):
            def __init__(self):
                super().__init__()
                self.statements = []

            def execute(self, statement):
                self.statements.append(statement)
                if len(self.statements) == 1:
                    return SimpleNamespace(all=lambda: [
                        (first, None, None, None, None, None, None, None, None, None),
                        (second, None, None, None, None, None, None, None, None, None),
                    ])
                return SimpleNamespace(
                    scalars=lambda: SimpleNamespace(all=lambda: documents)
                )

        session = Session()
        rows = build_repository(session).get_inspection_technical({}, "internal", "external")

        self.assertEqual(2, len(rows))
        self.assertEqual(documents, rows[0][10])
        self.assertEqual([], rows[1][10])
        self.assertIn("inspection_documents", str(session.statements[1]))
        self.assertNotIn("inspection_documents", str(session.statements[0]))

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
