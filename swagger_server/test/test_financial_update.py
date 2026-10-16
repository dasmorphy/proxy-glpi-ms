from types import SimpleNamespace
import unittest

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.repository.internal_management_repository import (
    InternalManagementRepository,
)


class FakeSession:
    """Primer execute: la inspección; segundo: la gestión financiera."""

    def __init__(self, management):
        self.inspection = SimpleNamespace(id_inspection=7, status="En proceso")
        self.management = management
        self.statements = []
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement):
        self.statements.append(str(statement))
        value = self.inspection if len(self.statements) == 1 else self.management
        return SimpleNamespace(
            scalar_one_or_none=lambda: value,
            scalars=lambda: SimpleNamespace(first=lambda: value),
        )

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def update(session, body):
    repository = InternalManagementRepository.__new__(InternalManagementRepository)
    repository.db_telearseg = SimpleNamespace(session_factory=lambda: session)
    repository.update_ticket_financial(body, "internal", "external")


def financial(**fields):
    return SimpleNamespace(
        id_management_financial=13, type_management="Factura", status="Emitida",
        number_document="001", amount_paid=None, updated_by="creador", **fields,
    )


class TestUpdateTicketFinancial(unittest.TestCase):
    def test_updates_the_selected_management(self):
        management = financial()
        session = FakeSession(management)

        update(session, {
            "inspection_id": 7, "id_management_financial": 13,
            "number_document": "002", "amount_paid": 50, "user": "editor",
        })

        self.assertIn("id_management_financial", session.statements[1])
        self.assertEqual("002", management.number_document)
        self.assertEqual(50, management.amount_paid)
        self.assertEqual("Emitida", management.status)
        self.assertEqual("editor", management.updated_by)
        self.assertEqual("En proceso", session.inspection.status)
        self.assertTrue(session.committed)

    def test_collected_invoice_finishes_the_ticket(self):
        session = FakeSession(financial())

        update(session, {"inspection_id": 7, "id_management_financial": 13,
                         "status": "Cobrada", "user": "editor"})

        self.assertEqual("Finalizado", session.inspection.status)

    def test_management_of_another_inspection_is_not_found(self):
        session = FakeSession(None)

        with self.assertRaises(CustomAPIException) as context:
            update(session, {"inspection_id": 7, "id_management_financial": 99})

        self.assertEqual(404, context.exception.status_code)
        self.assertFalse(session.committed)


if __name__ == "__main__":
    unittest.main()
