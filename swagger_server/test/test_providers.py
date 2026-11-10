from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.models.db import Base
from swagger_server.models.db.providers_products import ProvidersProducts
from swagger_server.repository.internal_management_repository import (
    InternalManagementRepository,
)
from swagger_server.uses_cases.internal_management_use_case import (
    InternalManagementUseCase,
)


def sqlite_repository():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def attach_schemas(connection, _):
        connection.execute("ATTACH DATABASE ':memory:' AS internal_management")

    Base.metadata.create_all(engine, tables=[ProvidersProducts.__table__])
    repository = InternalManagementRepository.__new__(InternalManagementRepository)
    repository.db_telearseg = SimpleNamespace(session_factory=sessionmaker(engine))
    return repository


class TestPostProvider(unittest.TestCase):
    def setUp(self):
        self.repository = sqlite_repository()
        self.use_case = InternalManagementUseCase(self.repository)

    def test_saves_provider_with_user_as_created_by(self):
        id_provider = self.use_case.post_provider(
            {
                "provider": "  Distribuidora ABC ",
                "ruc": "0991234567001",
                "email": "ventas@abc.com",
                "user": "dmales",
            },
            None,
            None,
        )

        with self.repository.db_telearseg.session_factory() as session:
            provider = session.get(ProvidersProducts, id_provider)
            self.assertEqual("Distribuidora ABC", provider.provider)
            self.assertEqual("0991234567001", provider.ruc)
            self.assertEqual("ventas@abc.com", provider.email)
            self.assertEqual("dmales", provider.created_by)
            self.assertIsNone(provider.address)
            self.assertIsNone(provider.status)

    def test_only_provider_is_required(self):
        id_provider = self.use_case.post_provider({"provider": "Solo nombre"}, None, None)

        with self.repository.db_telearseg.session_factory() as session:
            provider = session.get(ProvidersProducts, id_provider)
            self.assertEqual("Solo nombre", provider.provider)
            self.assertIsNone(provider.created_by)

    def test_rejects_missing_or_blank_provider(self):
        use_case = InternalManagementUseCase(MagicMock())
        for body in (None, {}, {"provider": "   "}, {"ruc": "0991234567001"}):
            with self.subTest(body=body):
                with self.assertRaises(CustomAPIException) as context:
                    use_case.post_provider(body, None, None)
                self.assertEqual(400, context.exception.status_code)
        use_case.internal_management_repository.post_provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
