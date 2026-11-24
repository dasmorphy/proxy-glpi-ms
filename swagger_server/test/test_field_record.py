"""Registros técnicos de campo (app) de Soportes / Asistencias en /register-technical."""
import io
import os
import tempfile
import unittest
from unittest import mock

from werkzeug.datastructures import FileStorage

from sqlalchemy import select

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.models.db.inspection_documents import InspectionDocuments
from swagger_server.models.db.inspection_technical import InspectionTechnical
from swagger_server.models.db.tech_staff_record import TechStaffRecord
from swagger_server.models.db.technical_equipment import TechnicalEquipment
from swagger_server.models.db.technical_ticket_management import TechnicalTicketManagement
from swagger_server.utils.inspection_documents import resolve_document_path
from swagger_server.test import test_inspection_type as base
from swagger_server.test.test_inspection_type import (
    TECHNICIAN_A,
    TECHNICIAN_B,
    create,
    inspection_sql,
    sqlite_repository,
)

base.TABLES.extend([TechStaffRecord.__table__, TechnicalEquipment.__table__])


class TestFieldRecord(unittest.TestCase):
    def setUp(self):
        self.repository = sqlite_repository()

    def post_field(self, inspection, **body):
        self.repository.post_ticket_technical(
            {
                "inspection_id": inspection.id_inspection,
                "field_record": True,
                "user": "tecnico",
                "description": "Trabajo",
                **body,
            },
            "i", "e", files=[],
        )

    def managements(self, inspection):
        with self.repository.db_telearseg.session_factory() as session:
            return session.execute(
                select(TechnicalTicketManagement)
                .where(TechnicalTicketManagement.inspection_id == inspection.id_inspection)
                .order_by(TechnicalTicketManagement.id_management_technical)
            ).scalars().all()

    def staff(self, management_id):
        with self.repository.db_telearseg.session_factory() as session:
            return session.execute(
                select(TechStaffRecord).where(
                    TechStaffRecord.management_technical_id == management_id
                )
            ).scalars().all()

    def test_support_accepts_several_field_records(self):
        inspection = create(self.repository, type="Soporte")

        self.post_field(inspection, vehicle="GTW-8534", record_status="Completado")
        self.post_field(inspection, record_status="Incompleto")

        records = self.managements(inspection)
        self.assertEqual(2, len(records))
        self.assertTrue(all(record.is_field_record for record in records))
        self.assertEqual("GTW-8534", records[0].vehicle)
        self.assertEqual("Completado", records[0].record_status)
        self.assertEqual("Pendiente aprobación", records[0].status)

    def test_staff_is_saved_only_when_sent(self):
        inspection = create(self.repository, type="Asistencia")

        self.post_field(inspection, technical_staff=[str(TECHNICIAN_A), str(TECHNICIAN_A)])
        self.post_field(inspection)

        first, second = self.managements(inspection)
        saved = self.staff(first.id_management_technical)
        self.assertEqual([TECHNICIAN_A], [row.user_tech_id for row in saved])
        self.assertEqual(inspection.id_inspection, saved[0].inspection_id)
        self.assertEqual([], self.staff(second.id_management_technical))

    def test_update_replaces_staff_and_keeps_it_when_not_sent(self):
        inspection = create(self.repository, type="Soporte")
        self.post_field(inspection, technical_staff=[str(TECHNICIAN_A)])
        record = self.managements(inspection)[0]

        def update(**body):
            self.repository.update_ticket_technical(
                {
                    "inspection_id": inspection.id_inspection,
                    "id_management_technical": record.id_management_technical,
                    "user": "tecnico",
                    **body,
                },
                "i", "e", files=[],
            )

        update(record_status="Completado", vehicle="GSW-7476")
        self.assertEqual(
            [TECHNICIAN_A],
            [row.user_tech_id for row in self.staff(record.id_management_technical)],
        )

        update(technical_staff=[str(TECHNICIAN_B)])
        self.assertEqual(
            [TECHNICIAN_B],
            [row.user_tech_id for row in self.staff(record.id_management_technical)],
        )
        updated = self.managements(inspection)[0]
        self.assertEqual("Completado", updated.record_status)
        self.assertEqual("GSW-7476", updated.vehicle)

    def test_invalid_staff_is_rejected(self):
        inspection = create(self.repository, type="Soporte")

        with self.assertRaises(CustomAPIException) as context:
            self.post_field(inspection, technical_staff=["no-es-uuid"])

        self.assertEqual(400, context.exception.status_code)

    def test_inspection_rejects_field_records(self):
        inspection = create(self.repository)

        with self.assertRaises(CustomAPIException) as context:
            self.post_field(inspection)

        self.assertEqual(400, context.exception.status_code)

    def test_approved_support_rejects_field_records(self):
        inspection = create(self.repository, type="Soporte")
        self.repository.approve_support(
            {"id_inspection": inspection.id_inspection, "user": "jefe"}, "i", "e"
        )

        with self.assertRaises(CustomAPIException) as context:
            self.post_field(inspection)

        self.assertEqual(400, context.exception.status_code)

    def test_assistance_in_commercial_rejects_field_records(self):
        inspection = create(self.repository, type="Asistencia", status="Listo para cotizar")

        with self.assertRaises(CustomAPIException) as context:
            self.post_field(inspection)

        self.assertEqual(400, context.exception.status_code)

    def test_field_records_do_not_block_web_management(self):
        inspection = create(self.repository, type="Asistencia")
        self.post_field(inspection)

        # La gestión técnica de la web se sigue pudiendo registrar una vez
        self.repository.post_ticket_technical(
            {"inspection_id": inspection.id_inspection, "user": "jefe"},
            "i", "e", files=[],
        )
        with self.assertRaises(CustomAPIException) as context:
            self.repository.post_ticket_technical(
                {"inspection_id": inspection.id_inspection, "user": "jefe"},
                "i", "e", files=[],
            )
        self.assertEqual(409, context.exception.status_code)

    def test_web_update_without_id_edits_the_web_management(self):
        inspection = create(self.repository, type="Asistencia")
        self.repository.post_ticket_technical(
            {"inspection_id": inspection.id_inspection, "user": "jefe"},
            "i", "e", files=[],
        )
        self.post_field(inspection)

        self.repository.update_ticket_technical(
            {"inspection_id": inspection.id_inspection, "user": "jefe", "description": "Web"},
            "i", "e", files=[],
        )

        web, field = self.managements(inspection)
        self.assertEqual("Web", web.description)
        self.assertEqual("Trabajo", field.description)

    def test_assistance_can_be_approved_without_records(self):
        inspection = create(self.repository, type="Asistencia")

        self.repository.approve_technical_inspection(
            {"id_inspection": inspection.id_inspection, "user": "jefe"}, "i", "e"
        )

        with self.repository.db_telearseg.session_factory() as session:
            approved = session.get(InspectionTechnical, inspection.id_inspection)
            self.assertTrue(approved.approve_support)

    def test_approving_assistance_approves_all_its_records(self):
        inspection = create(self.repository, type="Asistencia")
        self.post_field(inspection)
        self.post_field(inspection)

        self.repository.approve_technical_inspection(
            {"id_inspection": inspection.id_inspection, "user": "jefe"}, "i", "e"
        )

        self.assertEqual(
            ["Aprobado", "Aprobado"],
            [record.status for record in self.managements(inspection)],
        )

    def test_approving_support_approves_its_records(self):
        inspection = create(self.repository, type="Soporte")
        self.post_field(inspection)

        self.repository.approve_support(
            {"id_inspection": inspection.id_inspection, "user": "jefe"}, "i", "e"
        )

        self.assertEqual("Aprobado", self.managements(inspection)[0].status)

    def test_field_records_are_listed_in_record_technical(self):
        inspection = create(self.repository, type="Soporte")
        self.post_field(inspection, vehicle="GTW-8534", technical_staff=[str(TECHNICIAN_A)])

        with self.repository.db_telearseg.session_factory() as session:
            loaded = session.get(InspectionTechnical, inspection.id_inspection)
            staff = self.repository._support_staff(session, [loaded])

        records = staff[inspection.id_inspection]["records"]
        self.assertEqual(1, len(records))
        self.assertEqual("register_technical", records[0]["source"])
        self.assertEqual("GTW-8534", records[0]["vehicle"])
        self.assertEqual("Técnico A", records[0]["technical_staff"][0]["name"])

    def test_inspection_query_joins_only_web_management(self):
        sql = inspection_sql({})

        self.assertIn("technical_ticket_management.is_field_record IS 0", sql.replace("false", "0"))

    def test_field_record_images_go_to_public_folder(self):
        inspection = create(self.repository, type="Soporte")
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(
            os.environ,
            {"FIELD_RECORD_IMAGES_PATH": folder, "FIELD_RECORD_IMAGES_URL": "/uploads/technical"},
        ):
            image = FileStorage(
                io.BytesIO(b"webp"), filename="registro_tecnico_0.webp", content_type="image/webp"
            )
            self.repository.post_ticket_technical(
                {"inspection_id": inspection.id_inspection, "field_record": True, "user": "tecnico"},
                "i", "e", files=[image],
            )

            with self.repository.db_telearseg.session_factory() as session:
                document = session.execute(select(InspectionDocuments)).scalar_one()

            filename = document.document_path.rsplit("/", 1)[-1]
            self.assertTrue(document.document_path.startswith("/uploads/technical/"))
            self.assertTrue(os.path.isfile(os.path.join(folder, filename)))
            # La descarga por /inspection-documents/{id} sigue resolviendo el archivo
            self.assertEqual(
                os.path.realpath(os.path.join(folder, filename)),
                resolve_document_path(document.document_path),
            )


if __name__ == "__main__":
    unittest.main()
