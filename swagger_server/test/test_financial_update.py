from decimal import Decimal
from types import SimpleNamespace
import unittest

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.repository.internal_management_repository import (
    InternalManagementRepository,
)


class FakeSession:
    """Responde según la tabla consultada: inspección, gestión financiera, comercial o proforma."""

    def __init__(self, management, commercial_status=5, quotation_total=Decimal("862.41")):
        self.inspection = SimpleNamespace(id_inspection=7, status="En proceso")
        self.management = management
        self.commercial = SimpleNamespace(status_id=commercial_status)
        self.quotation = (
            SimpleNamespace(id_quote=30, total=quotation_total)
            if quotation_total is not None else None
        )
        self.statements = []
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        if "FROM internal_management.inspection_technical" in sql:
            value = self.inspection
        elif "FROM internal_management.financial_ticket_management" in sql:
            value = self.management
        elif "FROM internal_management.commercial_ticket_management" in sql:
            value = self.commercial
        else:
            value = self.quotation
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
        self.assertEqual(Decimal("862.41"), management.invoice_price)
        self.assertEqual(Decimal("812.41"), management.amount_pending)
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

    def test_ignores_the_invoice_price_sent_by_the_client(self):
        management = financial()
        session = FakeSession(management)

        update(session, {"inspection_id": 7, "id_management_financial": 13,
                         "invoice_price": 1, "amount_pending": 1})

        self.assertEqual(Decimal("862.41"), management.invoice_price)
        self.assertIsNone(management.amount_pending)

    def test_rejects_when_the_commercial_management_is_not_approved(self):
        session = FakeSession(financial(), commercial_status=7)

        with self.assertRaises(CustomAPIException) as context:
            update(session, {"inspection_id": 7, "id_management_financial": 13})

        self.assertEqual(400, context.exception.status_code)
        self.assertFalse(session.committed)

    def test_rejects_when_there_is_no_quotation(self):
        session = FakeSession(financial(), quotation_total=None)

        with self.assertRaises(CustomAPIException):
            update(session, {"inspection_id": 7, "id_management_financial": 13})

        self.assertFalse(session.committed)

    def test_rejects_paid_amount_greater_than_invoice(self):
        session = FakeSession(financial())

        with self.assertRaises(CustomAPIException) as context:
            update(session, {"inspection_id": 7, "id_management_financial": 13,
                             "amount_paid": 900})

        self.assertEqual(400, context.exception.status_code)
        self.assertFalse(session.committed)


if __name__ == "__main__":
    unittest.main()
