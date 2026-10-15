import io
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from werkzeug.datastructures import FileStorage

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.repository.internal_management_repository import (
    InternalManagementRepository,
)


def file_storage(name, content=b"contenido"):
    return FileStorage(stream=io.BytesIO(content), filename=name)


class FakeSession:
    def __init__(self, inspection=None, fail_on_commit=False):
        self.inspection = inspection
        self.fail_on_commit = fail_on_commit
        self.added = []
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement):
        return SimpleNamespace(
            scalar_one_or_none=lambda: self.inspection,
            scalar=lambda: False,
        )

    def add(self, record):
        self.added.append(record)

    def flush(self):
        for record in self.added:
            for pk in ("id_inspection", "id_management_financial"):
                if hasattr(record, pk) and getattr(record, pk) is None:
                    setattr(record, pk, 15)

    def commit(self):
        if self.fail_on_commit:
            raise RuntimeError("fallo de base de datos")
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def build_repository(session):
    repository = InternalManagementRepository.__new__(InternalManagementRepository)
    repository.db_telearseg = SimpleNamespace(session_factory=lambda: session)
    return repository


class TestInspectionDocumentsRepository(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = os.path.join(self.tmp.name, "inspection-documents")
        patcher = mock.patch(
            "swagger_server.utils.inspection_documents.get_documents_folder",
            return_value=self.folder,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def documents(self, session):
        return [
            record for record in session.added
            if type(record).__name__ == "InspectionDocuments"
        ]

    def test_post_inspection_saves_files_and_registers_paths(self):
        session = FakeSession()

        build_repository(session).post_inspection_technical(
            {"status": "En proceso", "user": "dmales"},
            "internal",
            "external",
            files=[file_storage("informe.pdf"), file_storage("foto sitio.jpg")],
        )

        documents = self.documents(session)
        self.assertTrue(session.committed)
        self.assertEqual(2, len(documents))
        self.assertTrue(all(doc.inspection_id == 15 for doc in documents))
        for doc in documents:
            self.assertTrue(os.path.isfile(doc.document_path))
            self.assertTrue(os.path.basename(doc.document_path).startswith("15_"))
        self.assertTrue(documents[1].document_path.endswith("_foto_sitio.jpg"))
        self.assertEqual("foto sitio.jpg", documents[1].name_document)
        self.assertEqual("application/pdf", documents[0].type_document)
        self.assertEqual("image/jpeg", documents[1].type_document)

    def test_post_without_files_does_not_register_documents(self):
        session = FakeSession()

        build_repository(session).post_inspection_technical(
            {"status": "En proceso"}, "internal", "external"
        )

        self.assertTrue(session.committed)
        self.assertEqual([], self.documents(session))

    def test_empty_file_fields_are_ignored(self):
        session = FakeSession()

        build_repository(session).post_inspection_technical(
            {"status": "En proceso"},
            "internal",
            "external",
            files=[file_storage("")],
        )

        self.assertEqual([], self.documents(session))

    def test_rejects_extension_not_allowed(self):
        session = FakeSession()

        with self.assertRaises(CustomAPIException) as context:
            build_repository(session).post_inspection_technical(
                {"status": "En proceso"},
                "internal",
                "external",
                files=[file_storage("script.exe")],
            )

        self.assertEqual(400, context.exception.status_code)
        self.assertFalse(session.committed)
        self.assertFalse(os.path.exists(self.folder))

    def test_removes_written_files_when_commit_fails(self):
        inspection = SimpleNamespace(
            id_inspection=7, management_area="Comercial", status="Emitida"
        )
        session = FakeSession(inspection=inspection, fail_on_commit=True)

        with self.assertRaises(CustomAPIException):
            build_repository(session).post_ticket_financial(
                {"inspection_id": 7, "status": "Emitida"},
                "internal",
                "external",
                files=[file_storage("factura.pdf")],
            )

        self.assertTrue(session.rolled_back)
        self.assertEqual([], os.listdir(self.folder))


class TestInspectionDocumentsController(unittest.TestCase):
    ENDPOINTS = {
        "/rest/proxy-glpi-api/v1.0/inspection": "post_inspection_technical",
        "/rest/proxy-glpi-api/v1.0/register-technical": "post_ticket_technical",
        "/rest/proxy-glpi-api/v1.0/register-commercial": "post_ticket_commercial",
        "/rest/proxy-glpi-api/v1.0/register-financial": "post_ticket_financial",
    }

    @classmethod
    def setUpClass(cls):
        from swagger_server.__main__ import create_app_test

        cls.client = create_app_test().test_client()

    def test_endpoints_accept_multipart_with_multiple_files(self):
        for url, method_name in self.ENDPOINTS.items():
            with self.subTest(url=url), mock.patch(
                f"swagger_server.uses_cases.internal_management_use_case."
                f"InternalManagementUseCase.{method_name}"
            ) as post_method:
                response = self.client.post(
                    url,
                    data={
                        "data": json.dumps({"inspection_id": 1, "user": "dmales"}),
                        "channel": "TLSG_WEB",
                        "externalTransactionId": "ext-1",
                        "files": [
                            (io.BytesIO(b"pdf"), "informe.pdf"),
                            (io.BytesIO(b"img"), "foto.png"),
                        ],
                    },
                    content_type="multipart/form-data",
                )

                self.assertEqual(200, response.status_code, response.get_json())
                args, kwargs = post_method.call_args
                self.assertEqual({"inspection_id": 1, "user": "dmales"}, args[0])
                self.assertEqual(
                    ["informe.pdf", "foto.png"],
                    [file.filename for file in kwargs["files"]],
                )

    def test_files_are_optional(self):
        with mock.patch(
            "swagger_server.uses_cases.internal_management_use_case."
            "InternalManagementUseCase.post_inspection_technical"
        ) as post_method:
            response = self.client.post(
                "/rest/proxy-glpi-api/v1.0/inspection",
                data={"data": json.dumps({"user": "dmales"})},
                content_type="multipart/form-data",
            )

        self.assertEqual(200, response.status_code, response.get_json())
        self.assertEqual([], post_method.call_args.kwargs["files"])

    def _stored_document(self, folder, **overrides):
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "7_abc123_informe.pdf")
        with open(path, "wb") as file:
            file.write(b"%PDF-contenido")
        values = {
            "id_document": 1,
            "document_path": path,
            "name_document": "informe.pdf",
            "type_document": "application/pdf",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def _download(self, document, folder, query=""):
        with mock.patch(
            "swagger_server.utils.inspection_documents.get_documents_folder",
            return_value=folder,
        ), mock.patch(
            "swagger_server.repository.internal_management_repository."
            "InternalManagementRepository.get_inspection_document",
            return_value=document,
        ):
            return self.client.get(
                f"/rest/proxy-glpi-api/v1.0/inspection-documents/1{query}",
                headers={"externalTransactionId": "ext-1", "channel": "TLSG_WEB"},
            )

    def test_download_returns_file_as_attachment(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, "inspection-documents")
            response = self._download(self._stored_document(folder), folder)

            self.assertEqual(200, response.status_code)
            self.assertEqual(b"%PDF-contenido", response.data)
            self.assertEqual("application/pdf", response.mimetype)
            self.assertIn("attachment", response.headers["Content-Disposition"])
            self.assertIn("informe.pdf", response.headers["Content-Disposition"])
            response.close()

    def test_download_inline_for_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, "inspection-documents")
            response = self._download(self._stored_document(folder), folder, "?inline=true")

            self.assertEqual(200, response.status_code)
            self.assertIn("inline", response.headers["Content-Disposition"])
            response.close()

    def test_download_rejects_path_outside_documents_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, "inspection-documents")
            outside = os.path.join(tmp, "secreto.txt")
            with open(outside, "w") as file:
                file.write("no debe salir")
            document = self._stored_document(folder, document_path=outside)

            response = self._download(document, folder)

            self.assertEqual(404, response.status_code)

    def test_download_missing_file_returns_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, "inspection-documents")
            document = self._stored_document(
                folder, document_path=os.path.join(folder, "no-existe.pdf")
            )

            response = self._download(document, folder)

            self.assertEqual(404, response.status_code)

    def test_invalid_json_in_data_returns_400(self):
        response = self.client.post(
            "/rest/proxy-glpi-api/v1.0/inspection",
            data={"data": "{no es json"},
            content_type="multipart/form-data",
        )

        self.assertEqual(400, response.status_code)


if __name__ == "__main__":
    unittest.main()
