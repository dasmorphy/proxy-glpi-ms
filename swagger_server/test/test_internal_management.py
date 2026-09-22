from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
import unittest

from swagger_server.models.db.commercial_ticket_management import (
    CommercialTicketManagement,
)
from swagger_server.models.db.financial_ticket_management import (
    FinancialTicketManagement,
)
from swagger_server.repository.internal_management_repository import (
    InternalManagementRepository,
)
from swagger_server.uses_cases.internal_management_use_case import (
    InternalManagementUseCase,
    PaginationParams,
)


def ticket(**overrides):
    values = {
        "id_ticket": 7,
        "ticket_glpi": 1234,
        "management_area": "Técnica",
        "next_area": "Comercial",
        "title_ticket": "Falla de enlace",
        "status": "Activo",
        "contact": "Daniel",
        "client_id": 3,
        "ubication_id": 4,
        "priority": "Alta",
        "responsible_ticket": "dmales",
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 2),
        "created_by": "dmales",
        "updated_by": "dmales",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeReadRepository:
    def __init__(self):
        self.filters = None
        self.pagination = None

    def get_ticket_technical(self, filters, pagination, internal, external):
        self.filters = filters
        self.pagination = pagination
        management = SimpleNamespace(
            id_management_technical=8,
            code_management="SOL-2026-0008",
            case_type="Incidente",
            management_status="Pendiente",
            next_action="Visita",
            commitment_date=datetime(2026, 1, 3),
            requires_material=True,
            requires_monitoring=False,
            observations="Revisar antena",
            status="En proceso",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 2),
            created_by="dmales",
            updated_by="dmales",
        )
        return [(management, ticket(), "Cliente Demo", "Matriz")], 21

    def get_ticket_commercial(self, filters, internal, external):
        self.filters = filters
        management = SimpleNamespace(
            id_management_commercial=9,
            assigned_user="vendedor",
            code_management="COT-2026-0009",
            origin_id=1,
            type_solution_id=2,
            quoted_amount=Decimal("212.30"),
            probability_closing=50,
            closing_date=datetime(2026, 2, 1),
            next_action="Enviar propuesta",
            responsible_next_action="vendedor",
            requires_technical=True,
            requires_material=True,
            scheduled_start_date=datetime(2026, 2, 2),
            contract_received=False,
            date_finish=None,
            reason_loss=None,
            observations="Cliente interesado",
            status_id=3,
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 2),
            created_by="dmales",
            updated_by="dmales",
        )
        return [(management, ticket(), "Referido", "Servicio", "Cotizado")]

    def get_ticket_financial(self, filters, internal, external):
        self.filters = filters
        management = SimpleNamespace(
            id_management_financial=10,
            code_management="FIN-2026-0010",
            type_management="Factura",
            amount_pending=Decimal("100.00"),
            amount_paid=Decimal("50.00"),
            invoice_price=Decimal("150.00"),
            observations="Pago parcial",
            status="Pendiente",
            date_document=datetime(2026, 2, 1),
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 2),
            created_by="dmales",
            updated_by="dmales",
        )
        return [(management, ticket())]


class FakeWriteSession:
    def __init__(self):
        self.ticket = ticket()
        self.added = []
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def get(self, model, key):
        return self.ticket if key == self.ticket.id_ticket else None

    def execute(self, statement):
        return type(
            "Result",
            (),
            {"scalar_one_or_none": lambda result: self.ticket},
        )()

    def add(self, record):
        self.added.append(record)
        if isinstance(record, CommercialTicketManagement):
            record.id_management_commercial = 12
        if isinstance(record, FinancialTicketManagement):
            record.id_management_financial = 13

    def flush(self):
        pass

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


class FakeUpdateResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def first(self):
        return self.value


class FakeUpdateSession:
    def __init__(self, management):
        self.ticket = ticket()
        self.management = management
        self.committed = False
        self.rolled_back = False
        self.executions = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement):
        self.executions += 1
        value = self.ticket if self.executions == 1 else self.management
        return FakeUpdateResult(value)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


class TestInternalManagementUseCase(unittest.TestCase):
    def test_get_ticket_technical_builds_filters_and_serializes_join(self):
        repository = FakeReadRepository()
        use_case = InternalManagementUseCase(repository)

        result = use_case.get_ticket_technical(
            {},
            {
                "ticket_id": "7",
                "ticket_glpi": "1234",
                "management_status": "Pendiente",
                "case_type": "Incidente",
                "page": "2",
                "page_size": "10",
            },
            "internal",
            "external",
        )

        self.assertEqual(7, repository.filters["ticket_id"])
        self.assertEqual(1234, repository.filters["ticket_glpi"])
        self.assertEqual(2, repository.pagination.page)
        self.assertEqual(10, repository.pagination.page_size)
        self.assertEqual("SOL-2026-0008", result["data"][0]["code_management"])
        self.assertEqual("Falla de enlace", result["data"][0]["title_ticket"])
        self.assertEqual("Cliente Demo", result["data"][0]["client_name"])
        self.assertEqual("Matriz", result["data"][0]["location_name"])
        self.assertEqual(21, result["pagination"]["total"])
        self.assertEqual(3, result["pagination"]["total_pages"])
        self.assertTrue(result["pagination"]["has_next"])

    def test_get_ticket_commercial_builds_filters_and_serializes_lookups(self):
        repository = FakeReadRepository()
        use_case = InternalManagementUseCase(repository)

        result = use_case.get_ticket_commercial(
            {},
            {
                "ticket_id": "7",
                "origin_id": "1",
                "type_solution_id": "2",
                "status_id": "3",
            },
            "internal",
            "external",
        )

        self.assertEqual(1, repository.filters["origin_id"])
        self.assertEqual(2, repository.filters["type_solution_id"])
        self.assertEqual(3, repository.filters["status_id"])
        self.assertEqual("COT-2026-0009", result[0]["code_management"])
        self.assertEqual("Referido", result[0]["origin_name"])
        self.assertEqual("Servicio", result[0]["type_solution_name"])
        self.assertEqual("Cotizado", result[0]["status_name"])

    def test_get_ticket_financial_builds_filters_and_serializes_record(self):
        repository = FakeReadRepository()
        use_case = InternalManagementUseCase(repository)

        result = use_case.get_ticket_financial(
            {},
            {
                "ticket_id": "7",
                "type_management": "Factura",
                "code_management": "FIN-2026-0010",
                "user": "dmales",
            },
            "internal",
            "external",
        )

        self.assertEqual(7, repository.filters["ticket_id"])
        self.assertEqual("Factura", repository.filters["type_management"])
        self.assertEqual("FIN-2026-0010", result[0]["code_management"])
        self.assertEqual(Decimal("100.00"), result[0]["amount_pending"])


class TestInternalManagementRepository(unittest.TestCase):
    def test_get_ticket_technical_counts_then_limits_the_joined_query(self):
        class Result:
            def __init__(self, total=None, rows=None):
                self.total = total
                self.rows = rows or []

            def scalar(self):
                return self.total

            def all(self):
                return self.rows

        class Session:
            def __init__(self):
                self.statements = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def execute(self, statement):
                self.statements.append(statement)
                if len(self.statements) == 1:
                    return Result(total=31)
                return Result(
                    rows=[
                        (
                            SimpleNamespace(),
                            ticket(client_id=3, ubication_id=4),
                        )
                    ]
                )

            def close(self):
                pass

        class ZentinelSession:
            def __init__(self):
                self.statements = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def execute(self, statement):
                self.statements.append(statement)
                if len(self.statements) == 1:
                    return Result(rows=[(3, "Cliente Demo")])
                return Result(rows=[(4, "Matriz")])

        session = Session()
        zentinel_session = ZentinelSession()
        repository = InternalManagementRepository.__new__(
            InternalManagementRepository
        )
        repository.db_telearseg = SimpleNamespace(
            session_factory=lambda: session
        )
        repository.db_zentinel = SimpleNamespace(
            session_factory=lambda: zentinel_session
        )

        rows, total = repository.get_ticket_technical(
            {"search": "cliente"},
            PaginationParams(page=2, page_size=10),
            "internal",
            "external",
        )

        self.assertEqual("Cliente Demo", rows[0][2])
        self.assertEqual("Matriz", rows[0][3])
        self.assertEqual(31, total)
        self.assertEqual(2, len(session.statements))
        statement = str(session.statements[1])
        self.assertIn("LIKE", statement)
        self.assertIn("LIMIT", statement)
        self.assertIn("OFFSET", statement)
        self.assertEqual(2, len(zentinel_session.statements))
        self.assertIn(
            "technical.clients",
            str(zentinel_session.statements[0]),
        )
        self.assertIn(
            "technical.clients_location",
            str(zentinel_session.statements[1]),
        )

    def test_post_ticket_commercial_uses_commercial_model_and_one_sequence_id(self):
        session = FakeWriteSession()
        repository = InternalManagementRepository.__new__(
            InternalManagementRepository
        )
        repository.db_telearseg = SimpleNamespace(
            session_factory=lambda: session
        )

        repository.post_ticket_commercial(
            {
                "ticket_id": 1234,
                "assigned_user": "vendedor",
                "origin_id": 1,
                "type_solution_id": 2,
                "quoted_amount": "212.30",
                "probability_closing": 50,
                "status_id": 3,
                "user": "dmales",
            },
            "internal",
            "external",
        )

        record = session.added[0]
        self.assertIsInstance(record, CommercialTicketManagement)
        self.assertEqual(7, record.ticket_id)
        self.assertEqual("COT-2026-0012", record.code_management)
        self.assertTrue(session.committed)
        self.assertFalse(session.rolled_back)

    def test_post_ticket_financial_uses_financial_model_and_one_sequence_id(self):
        session = FakeWriteSession()
        repository = InternalManagementRepository.__new__(
            InternalManagementRepository
        )
        repository.db_telearseg = SimpleNamespace(
            session_factory=lambda: session
        )

        repository.post_ticket_financial(
            {
                "ticket_id": 1234,
                "type_management": "Factura",
                "amount_pending": "100.00",
                "amount_paid": "50.00",
                "invoice_price": "150.00",
                "status": "Pendiente",
                "user": "dmales",
            },
            "internal",
            "external",
        )

        record = session.added[0]
        self.assertIsInstance(record, FinancialTicketManagement)
        self.assertEqual(7, record.ticket_id)
        self.assertEqual("FIN-2026-0013", record.code_management)
        self.assertEqual("Financiera", session.ticket.management_area)
        self.assertTrue(session.committed)
        self.assertFalse(session.rolled_back)

    def test_update_ticket_technical_updates_only_received_fields(self):
        management = SimpleNamespace(
            priority="No aplica",
            requires_material=True,
            observations="Anterior",
            updated_by="creator",
        )
        session = FakeUpdateSession(management)
        repository = InternalManagementRepository.__new__(
            InternalManagementRepository
        )
        repository.db_telearseg = SimpleNamespace(
            session_factory=lambda: session
        )

        repository.update_ticket_technical(
            {
                "ticket_glpi": 1234,
                "priority": "Baja",
                "requires_material": False,
                "observations": None,
                "user": "updater",
            },
            "internal",
            "external",
        )

        self.assertEqual("Baja", session.ticket.priority)
        self.assertFalse(management.requires_material)
        self.assertIsNone(management.observations)
        self.assertEqual("updater", session.ticket.updated_by)
        self.assertEqual("updater", management.updated_by)
        self.assertTrue(session.committed)

    def test_update_ticket_commercial_updates_only_received_fields(self):
        management = SimpleNamespace(
            quoted_amount=Decimal("100.00"),
            requires_technical=True,
            date_finish=datetime(2026, 2, 1),
            updated_by="creator",
        )
        session = FakeUpdateSession(management)
        repository = InternalManagementRepository.__new__(
            InternalManagementRepository
        )
        repository.db_telearseg = SimpleNamespace(
            session_factory=lambda: session
        )

        repository.update_ticket_commercial(
            {
                "ticket_id": 1234,
                "quoted_amount": "250.50",
                "requires_technical": False,
                "date_finish": None,
                "user": "updater",
            },
            "internal",
            "external",
        )

        self.assertEqual("250.50", management.quoted_amount)
        self.assertFalse(management.requires_technical)
        self.assertIsNone(management.date_finish)
        self.assertEqual("updater", management.updated_by)
        self.assertTrue(session.committed)

    def test_update_ticket_financial_updates_only_received_fields(self):
        management = SimpleNamespace(
            amount_pending=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            status="Pendiente",
            updated_by="creator",
        )
        session = FakeUpdateSession(management)
        repository = InternalManagementRepository.__new__(
            InternalManagementRepository
        )
        repository.db_telearseg = SimpleNamespace(
            session_factory=lambda: session
        )

        repository.update_ticket_financial(
            {
                "ticket_id": 1234,
                "amount_paid": "100.00",
                "status": "Cobrada",
                "user": "updater",
            },
            "internal",
            "external",
        )

        self.assertEqual(Decimal("100.00"), management.amount_pending)
        self.assertEqual("100.00", management.amount_paid)
        self.assertEqual("Cobrada", management.status)
        self.assertEqual("updater", management.updated_by)
        self.assertTrue(session.committed)


if __name__ == "__main__":
    unittest.main()
