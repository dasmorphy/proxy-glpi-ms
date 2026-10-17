from types import SimpleNamespace
import unittest

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.repository.internal_management_repository import (
    InternalManagementRepository,
)


class FakeSession:
    def __init__(self, inspection):
        self.inspection = inspection
        self.statements = []
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement):
        self.statements.append(str(statement))
        return SimpleNamespace(scalar_one_or_none=lambda: self.inspection)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def assign(session, body):
    repository = InternalManagementRepository.__new__(InternalManagementRepository)
    repository.db_telearseg = SimpleNamespace(session_factory=lambda: session)
    repository.assign_sales_user(body, "internal", "external")


class TestAssignSalesUser(unittest.TestCase):
    def test_sets_sales_user_of_the_inspection(self):
        inspection = SimpleNamespace(id_inspection=7, sales_user=None)
        session = FakeSession(inspection)

        assign(session, {"id_inspection": 7, "user": " asesor1 "})

        self.assertEqual("asesor1", inspection.sales_user)
        self.assertTrue(session.committed)

    def test_requires_user(self):
        session = FakeSession(SimpleNamespace(id_inspection=7, sales_user=None))

        for body in ({"id_inspection": 7}, {"id_inspection": 7, "user": "  "}):
            with self.assertRaises(CustomAPIException) as context:
                assign(session, body)
            self.assertEqual(400, context.exception.status_code)
        self.assertFalse(session.committed)

    def test_inspection_not_found(self):
        session = FakeSession(None)

        with self.assertRaises(CustomAPIException) as context:
            assign(session, {"id_inspection": 99, "user": "asesor1"})

        self.assertEqual(404, context.exception.status_code)
        self.assertFalse(session.committed)


class TestSalesUserFilter(unittest.TestCase):
    def test_filter_is_built_from_params(self):
        from swagger_server.uses_cases.internal_management_use_case import (
            InternalManagementUseCase,
        )

        use_case = InternalManagementUseCase.__new__(InternalManagementUseCase)
        self.assertEqual(
            "asesor1",
            use_case._build_ticket_filters({"sales_user": " asesor1 "})["sales_user"],
        )
        self.assertIsNone(use_case._build_ticket_filters({})["sales_user"])


if __name__ == "__main__":
    unittest.main()
