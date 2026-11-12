from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from loguru import logger
from sqlalchemy import and_, delete, exists, func, or_, select, update

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.models.db.client_companies import ClientCompany
from swagger_server.models.db.client_projects import Client
from swagger_server.models.db.commercial_followup import CommercialFollowup
from swagger_server.models.db.commercial_origin import CommercialOrigin
from swagger_server.models.db.commercial_ticket_management import CommercialTicketManagement
from swagger_server.models.db.commercial_ticket_status import CommercialTicketStatus
from swagger_server.models.db.commercial_type_solution import CommercialTypeSolution
from swagger_server.models.db.financial_followup import FinancialFollowup
from swagger_server.models.db.financial_ticket_management import FinancialTicketManagement
from swagger_server.models.db.history_area_ticket import HistoryAreaTicket
from swagger_server.models.db.inspection_documents import InspectionDocuments
from swagger_server.models.db.location import ClientLocation
from swagger_server.models.db.material_delivery_detail import MaterialDeliveryDetail
from swagger_server.models.db.material_delivery_history import MaterialDeliveryHistory
from swagger_server.models.db.material_tech_ticket import MaterialTechTicket
from swagger_server.models.db.pending_material import PendingMaterial
from swagger_server.models.db.providers_products import ProvidersProducts
from swagger_server.models.db.sale_additional_materials import SaleAdditionalMaterials
from swagger_server.models.db.sale_quotation import SaleQuotation
from swagger_server.models.db.sale_quotation_item import SaleQuotationItem
from swagger_server.models.db.task_technical import TaskTechnical
from swagger_server.models.db.task_technical_assignments import TaskTechnicalAssignment
from swagger_server.models.db.technical_equipment import TechnicalEquipment
from swagger_server.models.db.technical_record import TechnicalRecord
from swagger_server.models.db.technical_ticket_management import TechnicalTicketManagement
from swagger_server.models.db.users import Users
from swagger_server.models.db.inspection_technical import InspectionTechnical
from swagger_server.resources.databases.postgresql import PostgreSQLClient
from swagger_server.utils.inspection_documents import (
    clean_files,
    document_mimetype,
    remove_documents,
    save_document,
    validate_documents,
)


class InternalManagementRepository:
    COMMERCIAL_STATUS_APPROVED = 5
    COMMERCIAL_STATUS_PENDING = 7
    # Congelada mientras el registro está devuelto en Técnica (sección 6 de la doc)
    COMMERCIAL_STATUS_RETURNED_TECHNICAL = 9
    TECHNICAL_STATUS_PENDING_APPROVAL = "Pendiente aprobación"
    TECHNICAL_STATUS_RETURNED = "Devuelto"
    INSPECTION_STATUS_RETURNED_TECHNICAL = "Devuelto a Técnica"
    FOLLOWUP_TYPE_PENDING = "Pendiente"
    FOLLOWUP_TYPE_REGISTERED = "Registrado"
    INSPECTION_TYPE = "Inspección"
    SUPPORT_TYPE = "Soporte"
    ASSISTANCE_TYPE = "Asistencia"
    ASSISTANCE_APPROVED_LOCKED = (
        "La asistencia ya fue aprobada y descontó stock; "
        "no se puede modificar su proforma ni su estado comercial"
    )
    # Tipos que usan fecha inicio/fin en lugar de la fecha compromiso. Solo el
    # Soporte sale del flujo; la Asistencia sigue el flujo normal
    SUPPORT_TYPES = (SUPPORT_TYPE, ASSISTANCE_TYPE)
    VALID_TYPES = (INSPECTION_TYPE, SUPPORT_TYPE, ASSISTANCE_TYPE)
    MANAGEMENT_STATUS_COMPLETED = "Completado"

    def __init__(self):
        self.db_telearseg = PostgreSQLClient("TELEARSEG")
        self.db_zentinel = PostgreSQLClient("ZENTINEL")

    @staticmethod
    def generate_code_technical(management_id):
        return f"SOL-{datetime.now().year}-{management_id:04d}"

    @staticmethod
    def generate_code_commercial(management_id):
        return f"COT-{datetime.now().year}-{management_id:04d}"

    @staticmethod
    def generate_code_financial(management_id):
        return f"MOV-{datetime.now().year}-{management_id:04d}"

    @staticmethod
    def generate_code_inspection(management_id):
        return f"INS-{datetime.now().year}-{management_id:04d}"

    @staticmethod
    def generate_code_quote(sales_code, management_id):
        return f"{sales_code}-{management_id:04d}"


    @staticmethod
    def _quotation_item_key(material_id, material_tech_ticket_id, item_number):
        """Identifica una línea entre ediciones: id_item cambia al recrearla."""
        if material_id:
            return "material", material_id
        if material_tech_ticket_id:
            return "technical", material_tech_ticket_id
        return "item", item_number

    def save_sale_quotation(self, session, inspection_id, quotation, user, sales_code):
        """Guarda la proforma de la inspección. Si ya existe una se actualiza su
        cabecera y sus items se reemplazan completos con los recibidos."""
        InternalManagementRepository._validate_quotation_quantities(quotation)
        technical_ids = self._validate_quotation_technical_materials(
            session, inspection_id, quotation
        )
        sale_quotation = session.execute(
            select(SaleQuotation)
            .where(SaleQuotation.inspection_id == inspection_id)
            .order_by(SaleQuotation.id_quote.desc())
        ).scalars().first()

        previous_checks = {}
        linked_pendings = []
        if sale_quotation is None:
            sale_quotation = SaleQuotation(
                inspection_id=inspection_id,
                created_by=user,
            )
            session.add(sale_quotation)
        else:
            # checked_item es opcional: el item que no lo envíe conserva su valor
            previous_items = session.execute(
                select(SaleQuotationItem).where(
                    SaleQuotationItem.sale_quote_id == sale_quotation.id_quote
                )
            ).scalars().all()
            previous_checks = {
                self._quotation_item_key(
                    previous.material_id,
                    previous.material_tech_ticket_id,
                    previous.item_number,
                ): previous.checked_item
                for previous in previous_items
            }

            # Una proforma aprobada puede volver a Comercial: sus pendientes se
            # desvinculan aquí y se re-vinculan a las líneas recreadas
            linked_pendings = self._unlink_quotation_pendings(
                session, sale_quotation.id_quote, previous_items
            )

            # Los componentes referencian a los items: se eliminan primero
            session.execute(
                delete(SaleAdditionalMaterials).where(
                    SaleAdditionalMaterials.sale_quote_id == sale_quotation.id_quote
                )
            )
            session.execute(
                delete(SaleQuotationItem).where(
                    SaleQuotationItem.sale_quote_id == sale_quotation.id_quote
                )
            )

        sale_quotation.client_company = quotation.get('client_company')
        sale_quotation.iva = quotation.get('iva')
        sale_quotation.iva_rate = quotation.get('iva_rate')
        sale_quotation.subtotal = quotation.get('subtotal')
        sale_quotation.total = quotation.get('total')
        # Condiciones comerciales que se imprimen en el PDF de la proforma
        sale_quotation.delivery_time = self._optional_text(quotation.get('delivery_time'))
        sale_quotation.payment_terms = self._optional_text(quotation.get('payment_terms'))
        sale_quotation.validity_days = self._validity_days(quotation.get('validity_days'))
        sale_quotation.updated_by = user
        session.flush()

        sale_quotation.quote_number = self.generate_code_quote(
            sales_code,
            sale_quotation.id_quote
        )

        for item in quotation.get('items') or []:
            checked_item = item.get('checked_item')
            if checked_item is None:
                checked_item = previous_checks.get(
                    self._quotation_item_key(
                        item.get('material_id'),
                        item.get('material_tech_ticket_id'),
                        item.get('item'),
                    )
                )
            quotation_item = SaleQuotationItem(
                sale_quote_id=sale_quotation.id_quote,
                material_id=item.get('material_id'),
                material_tech_ticket_id=item.get('material_tech_ticket_id'),
                item_number=item.get('item'),
                is_labor=item.get('is_labor'),
                is_bundle=item.get('is_bundle'),
                is_new=item.get('is_new'),
                # Solo los productos nuevos y la mano de obra traen modelo y descripción
                model=item.get('model'),
                description=item.get('description'),
                base_price=item.get('base_price'),
                profit_margin=item.get('profit_margin'),
                profit_margin_dollar=item.get('profit_margin_dollar'),
                quantity=item.get('quantity'),
                total=item.get('total'),
                created_by=user,
                updated_by=user,
            )
            if checked_item is not None:
                quotation_item.checked_item = bool(checked_item)
            session.add(quotation_item)

            if not item.get('is_bundle'):
                continue

            session.flush()
            for component in item.get('components') or []:
                is_new = bool(component.get('is_new')) and not component.get('material_id')
                session.add(SaleAdditionalMaterials(
                    sale_quote_id=sale_quotation.id_quote,
                    quotation_item_id=quotation_item.id_item,
                    material_id=component.get('material_id'),
                    is_new=is_new,
                    # Solo los productos nuevos traen modelo y descripción
                    model=self._optional_text(component.get('model')) if is_new else None,
                    description=self._optional_text(component.get('description')) if is_new else None,
                    material_tech_ticket_id=(
                        component.get('material_tech_ticket_id') if is_new else None
                    ),
                    base_price=component.get('base_price'),
                    profit_margin=component.get('profit_margin'),
                    profit_margin_dollar=component.get('profit_margin_dollar'),
                    quantity=component.get('quantity'),
                    total=component.get('total'),
                    created_by=user,
                    updated_by=user,
                ))

        if linked_pendings:
            self._relink_quotation_pendings(
                session, sale_quotation.id_quote, linked_pendings
            )
        self._sync_quotation_pendings(session, inspection_id, technical_ids)
        return sale_quotation

    @staticmethod
    def _pending_line_key(material_tech_ticket_id, model, description):
        """Identifica la línea de un pendiente entre ediciones de la proforma
        (id_item cambia al recrearla). No usa item_number: al reordenar las
        líneas, un pendiente podría quedar en otro producto."""
        if material_tech_ticket_id is not None:
            return "technical", material_tech_ticket_id

        def normalize(value):
            return (str(value).strip() or None) if value is not None else None

        return "new", normalize(description), normalize(model)

    @classmethod
    def _unlink_quotation_pendings(cls, session, quote_id, previous_items):
        """Antes de recrear las líneas de la proforma: rechaza la edición si ya
        hay entregas y desvincula los pendientes de sus líneas. Devuelve
        (pendiente, clave de su línea) para re-vincularlos después."""
        item_ids = [item.id_item for item in previous_items]
        previous_components = session.execute(
            select(SaleAdditionalMaterials).where(
                SaleAdditionalMaterials.sale_quote_id == quote_id
            )
        ).scalars().all()
        component_ids = [component.id_extra for component in previous_components]

        line_filters = []
        if item_ids:
            line_filters.append(MaterialDeliveryDetail.quotation_item_id.in_(item_ids))
        if component_ids:
            line_filters.append(
                MaterialDeliveryDetail.additional_material_id.in_(component_ids)
            )
        if line_filters and session.execute(
            select(exists().where(or_(*line_filters)))
        ).scalar():
            # El detalle de la entrega referencia las líneas: no se pueden recrear
            raise CustomAPIException(
                "La proforma ya tiene materiales entregados; no se puede editar",
                400,
            )

        pendings = session.execute(
            select(PendingMaterial)
            .where(PendingMaterial.quote_id == quote_id)
            .order_by(PendingMaterial.id_pending_material)
        ).scalars().all()
        if not pendings:
            return []

        lines = {("item", item.id_item): item for item in previous_items}
        lines.update(
            {("component", component.id_extra): component for component in previous_components}
        )
        linked = []
        for pending in pendings:
            line = (
                lines.get(("item", pending.quotation_item_id))
                if pending.quotation_item_id is not None
                else lines.get(("component", pending.additional_material_id))
            )
            source = line or pending
            key = cls._pending_line_key(
                source.material_tech_ticket_id,
                source.model,
                line.description if line is not None else pending.name_material,
            )
            linked.append((pending, key))
            pending.quotation_item_id = None
            pending.additional_material_id = None
        session.flush()
        return linked

    @classmethod
    def _relink_quotation_pendings(cls, session, quote_id, linked_pendings):
        """Vincula cada pendiente a la línea recreada con la misma clave. Los
        que ya no están en la proforma quedan fuera de ella."""
        session.flush()
        new_items = session.execute(
            select(SaleQuotationItem)
            .where(
                SaleQuotationItem.sale_quote_id == quote_id,
                SaleQuotationItem.is_new.is_(True),
                SaleQuotationItem.is_labor.isnot(True),
                SaleQuotationItem.material_id.is_(None),
            )
            .order_by(SaleQuotationItem.id_item)
        ).scalars().all()
        new_components = session.execute(
            select(SaleAdditionalMaterials)
            .where(
                SaleAdditionalMaterials.sale_quote_id == quote_id,
                SaleAdditionalMaterials.is_new.is_(True),
                SaleAdditionalMaterials.material_id.is_(None),
            )
            .order_by(SaleAdditionalMaterials.id_extra)
        ).scalars().all()

        candidates = {}
        for line, item_id, additional_id in (
            [(item, item.id_item, None) for item in new_items]
            + [(component, None, component.id_extra) for component in new_components]
        ):
            key = cls._pending_line_key(
                line.material_tech_ticket_id, line.model, line.description
            )
            candidates.setdefault(key, []).append((line, item_id, additional_id))

        for pending, key in linked_pendings:
            matches = candidates.get(key)
            if not matches:
                # Ya no está en la proforma; el del técnico vuelve a quedar
                # disponible para _sync_quotation_pendings
                pending.quote_id = None
                if pending.status == PendingMaterial.STATUS_PENDING:
                    pending.status = PendingMaterial.STATUS_REMOVED
                continue

            line, item_id, additional_id = matches.pop(0)
            pending.quotation_item_id = item_id
            pending.additional_material_id = additional_id
            pending.model = line.model or pending.model
            pending.quantity = line.quantity
            pending.base_price = line.base_price
            pending.profit_margin = line.profit_margin
            pending.profit_margin_dollar = line.profit_margin_dollar
            if pending.status == PendingMaterial.STATUS_REMOVED:
                pending.status = PendingMaterial.STATUS_PENDING
        session.flush()

    @staticmethod
    def _validate_quotation_technical_materials(session, inspection_id, quotation):
        """Los ítems y los componentes de materiales varios pueden indicar el
        material del registro técnico del que provienen; debe pertenecer a la
        misma inspección y aparecer una sola vez en la proforma."""
        referenced = []
        for item in quotation.get('items') or []:
            lines = (item.get('components') or []) if item.get('is_bundle') else [item]
            referenced.extend(
                line.get('material_tech_ticket_id')
                for line in lines
                if line.get('material_tech_ticket_id') is not None
            )
        technical_ids = set(referenced)
        if len(technical_ids) != len(referenced):
            repeated = min(i for i in technical_ids if referenced.count(i) > 1)
            raise CustomAPIException(
                f"El material técnico {repeated} está repetido en la proforma",
                400,
            )
        if not technical_ids:
            return technical_ids

        valid = set(
            session.execute(
                select(MaterialTechTicket.id_material)
                .join(
                    TechnicalTicketManagement,
                    TechnicalTicketManagement.id_management_technical
                    == MaterialTechTicket.tech_ticket,
                )
                .where(
                    TechnicalTicketManagement.inspection_id == inspection_id,
                    MaterialTechTicket.id_material.in_(technical_ids),
                )
            ).scalars().all()
        )
        invalid = technical_ids - valid
        if invalid:
            raise CustomAPIException(
                f"El material técnico {min(invalid)} no pertenece a la inspección",
                400,
            )
        return technical_ids

    @staticmethod
    def _sync_quotation_pendings(session, inspection_id, technical_ids):
        """Marca como eliminados de la proforma los pendientes del técnico que
        el comercial no incluyó, y restaura los que vuelve a incluir."""
        pendings = session.execute(
            select(PendingMaterial).where(
                PendingMaterial.inspection_id == inspection_id,
                PendingMaterial.material_tech_ticket_id.isnot(None),
                PendingMaterial.quote_id.is_(None),
                PendingMaterial.status.in_([
                    PendingMaterial.STATUS_PENDING,
                    PendingMaterial.STATUS_REMOVED,
                ]),
            )
        ).scalars().all()
        for pending in pendings:
            pending.status = (
                PendingMaterial.STATUS_PENDING
                if pending.material_tech_ticket_id in technical_ids
                else PendingMaterial.STATUS_REMOVED
            )

    @staticmethod
    def _optional_text(value):
        if value is None:
            return None
        return str(value).strip() or None

    @staticmethod
    def _validity_days(value):
        if value is None or value == "":
            return None
        try:
            days = int(value)
        except (TypeError, ValueError):
            raise CustomAPIException("El campo validity_days debe ser un número entero de días", 400)
        if days < 0:
            raise CustomAPIException("El campo validity_days no puede ser negativo", 400)
        return days

    @staticmethod
    def _get_sale_quotations(session, inspection_ids):
        """Retorna {inspection_id: (proforma, items, componentes)} con la última
        proforma de cada inspección, en consultas aparte para no duplicar filas."""
        if not inspection_ids:
            return {}

        latest_by_inspection = {}
        for quotation in session.execute(
            select(SaleQuotation)
            .where(SaleQuotation.inspection_id.in_(inspection_ids))
            .order_by(SaleQuotation.id_quote)
        ).scalars().all():
            latest_by_inspection[quotation.inspection_id] = quotation

        if not latest_by_inspection:
            return {}

        quote_ids = [quotation.id_quote for quotation in latest_by_inspection.values()]
        items_by_quote = {}
        for item in session.execute(
            select(SaleQuotationItem)
            .where(SaleQuotationItem.sale_quote_id.in_(quote_ids))
            .order_by(SaleQuotationItem.item_number, SaleQuotationItem.id_item)
        ).scalars().all():
            items_by_quote.setdefault(item.sale_quote_id, []).append(item)

        components_by_quote = {}
        for component in session.execute(
            select(SaleAdditionalMaterials)
            .where(SaleAdditionalMaterials.sale_quote_id.in_(quote_ids))
            .order_by(SaleAdditionalMaterials.id_extra)
        ).scalars().all():
            components_by_quote.setdefault(component.sale_quote_id, []).append(component)

        return {
            inspection_id: (
                quotation,
                items_by_quote.get(quotation.id_quote, []),
                components_by_quote.get(quotation.id_quote, []),
            )
            for inspection_id, quotation in latest_by_inspection.items()
        }

    @staticmethod
    def _save_inspection_documents(session, inspection_id, files, saved_paths):
        """Escribe los archivos en disco y registra cada ruta en inspection_documents.

        Las rutas escritas se agregan a saved_paths para poder eliminarlas si la
        transacción falla antes del commit.
        """
        for file in files:
            document_path = save_document(file, inspection_id)
            saved_paths.append(document_path)
            session.add(
                InspectionDocuments(
                    inspection_id=inspection_id,
                    document_path=document_path,
                    name_document=file.filename,
                    type_document=document_mimetype(file.filename, file.mimetype),
                )
            )


    def post_inspection_technical(self, body, internal, external, files=None):
        files = clean_files(files)
        saved_paths = []
        with self.db_telearseg.session_factory() as session:
            try:
                validate_documents(files)
                inspection_type = self._inspection_type(body.get("type"))
                if inspection_type == self.SUPPORT_TYPE:
                    # El Soporte no continúa el flujo: se queda en Técnica.
                    # La Asistencia sigue el flujo normal, como una Inspección
                    current_area, next_area = "Técnica", None
                else:
                    current_area = "Comercial" if body.get("status") == "Listo para cotizar" else "Técnica"
                    next_area = "Proyectos" if current_area == "Comercial" else "Comercial"

                new_inspection = InspectionTechnical(
                    type=inspection_type,
                    start_date=self._parse_datetime(body.get("start_date"), "start_date"),
                    end_date=self._parse_datetime(body.get("end_date"), "end_date"),
                    management_area=current_area,
                    next_area=next_area,
                    title_ticket=body.get('title_ticket'),
                    contact=body.get('contact'),
                    priority=body.get('priority'),
                    responsible_id=body.get('responsible_id'),
                    responsible_name=body.get('responsible_name'),
                    commitment_date=body.get('commitment_date'),
                    management_status=body.get('management_status'),
                    status=body.get('status'),
                    case_type=body.get('case_type'),
                    client_id=body.get('client_id'),
                    ubication_id=body.get('ubication_id'),
                    created_by=body.get('user'),
                    updated_by=body.get('user'),
                    client_name=body.get('client_name'),
                    ubication_name=body.get('ubication_name'),
                )
                self._validate_support_dates(new_inspection)


                session.add(new_inspection)
                session.flush()

                new_inspection.code = self.generate_code_inspection(
                    new_inspection.id_inspection
                )

                new_history_area = HistoryAreaTicket(
                    ticket_id=new_inspection.id_inspection,
                    previous_area="Técnica",
                    current_area=current_area,
                    created_by=body.get('user')
                )


                session.add(new_history_area)
                self._save_inspection_documents(
                    session, new_inspection.id_inspection, files, saved_paths
                )
                session.commit()

            except Exception as exception:
                session.rollback()
                remove_documents(saved_paths)
                logger.error('Error: {}', str(exception), internal=internal, external=external)
                if isinstance(exception, CustomAPIException):
                    raise exception

                raise CustomAPIException("Error al insertar en la base de datos", 500)

            finally:
                session.close()

    def update_inspection_technical(self, id_inspection, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                if body is not None and not isinstance(body, dict):
                    raise CustomAPIException("El campo data debe ser un objeto", 400)
                body = body or {}

                inspection = self._get_inspection(session, id_inspection)

                # El formulario siempre envía type: solo se procesa si cambia
                if "type" in body and self._inspection_type(body["type"]) != inspection.type:
                    inspection_type = self._inspection_type(body["type"])
                    if (
                        inspection_type == self.SUPPORT_TYPE
                        and self._follows_flow(inspection)
                        and self._inspection_started_flow(session, inspection)
                    ):
                        raise CustomAPIException(
                            f"La inspección ya avanzó en el flujo; no puede cambiarse a {inspection_type}",
                            400,
                        )
                    inspection.type = inspection_type
                    if inspection_type == self.SUPPORT_TYPE:
                        # El Soporte sale del flujo y requiere su propia aprobación
                        inspection.approve_support = False
                        inspection.next_area = None
                    elif inspection.management_area in (None, "Técnica"):
                        # Vuelve al flujo: la Asistencia se aprueba con su registro
                        # técnico, no con la aprobación del Soporte
                        inspection.approve_support = False
                        if inspection.next_area is None:
                            inspection.next_area = "Comercial"

                self._apply_fields(
                    inspection,
                    body,
                    {
                        "title_ticket": "title_ticket",
                        "status": "status",
                        "contact": "contact",
                        "priority": "priority",
                        "responsible_id": "responsible_id",
                        "responsible_name": "responsible_name",
                        "client_id": "client_id",
                        "ubication_id": "ubication_id",
                        "client_name": "client_name",
                        "ubication_name": "ubication_name",
                    },
                )
                for field in ("commitment_date", "start_date", "end_date"):
                    if field in body:
                        setattr(inspection, field, self._parse_datetime(body[field], field))
                self._validate_support_dates(inspection)
                self._set_updated_by(body, inspection)

                if (
                    body.get("status") == "Listo para cotizar"
                    and inspection.management_area == "Técnica"
                    and self._follows_flow(inspection)
                ):
                    inspection.management_area = "Comercial"
                    inspection.next_area = "Proyectos"

                    new_history_area = HistoryAreaTicket(
                        ticket_id=inspection.id_inspection,
                        previous_area="Técnica",
                        current_area="Comercial",
                        created_by=body.get('user')
                    )
                    session.add(new_history_area)
                    self._resume_returned_commercial(
                        session, inspection.id_inspection, body.get('user')
                    )

                session.commit()
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al actualizar la inspección",
                    internal,
                    external,
                )
            finally:
                session.close()

    def post_ticket_technical(self, body, internal, external, files=None):
        files = clean_files(files)
        saved_paths = []
        with self.db_telearseg.session_factory() as session:
            try:
                validate_documents(files)
                inspection = session.execute(
                    select(InspectionTechnical).where(
                        InspectionTechnical.id_inspection == body.get('inspection_id')
                    )
                ).scalar_one_or_none()

                if inspection is None:
                    raise CustomAPIException("Inspección no encontrado", 404)
                self._ensure_not_support(inspection)

                already_registered = session.execute(
                    select(
                        exists().where(
                            TechnicalTicketManagement.inspection_id
                            == inspection.id_inspection
                        )
                    )
                ).scalar()

                if already_registered:
                    raise CustomAPIException(
                        "La inspección ya tiene un registro técnico asociado", 409
                    )

                new_register = TechnicalTicketManagement(
                    inspection_id=inspection.id_inspection,
                    description=body.get('description'),
                    status="Pendiente aprobación",
                    created_by=body.get('user'),
                    updated_by=body.get('user'),
                )

                session.add(new_register)
                session.flush()
                new_register.code_management = self.generate_code_technical(
                    new_register.id_management_technical
                )

                self._save_technical_materials(
                    session, new_register, body.get('materials') or [], body.get('user')
                )

                self._save_inspection_documents(
                    session, inspection.id_inspection, files, saved_paths
                )
                session.commit()

            except Exception as exception:
                session.rollback()
                remove_documents(saved_paths)
                logger.error('Error: {}', str(exception), internal=internal, external=external)
                if isinstance(exception, CustomAPIException):
                    raise exception

                raise CustomAPIException("Error al insertar en la base de datos", 500)

            finally:
                session.close()


    def get_ticket_technical(self, filters, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                stmt = (
                    select(
                        TechnicalTicketManagement,
                        InspectionTechnical,
                    )
                    .join(
                        InspectionTechnical,
                        InspectionTechnical.id_inspection
                        == TechnicalTicketManagement.inspection_id,
                    )
                )

                conditions = self._ticket_conditions(
                    filters,
                    TechnicalTicketManagement,
                )
                if filters.get("management_status"):
                    conditions.append(
                        InspectionTechnical.management_status
                        == filters["management_status"]
                    )

                if filters.get("user"):
                    conditions.append(
                        TechnicalTicketManagement.created_by == filters["user"]
                    )

                if filters.get("ticket_technical_id") is not None:
                    conditions.append(TechnicalTicketManagement.id_management_technical == filters["ticket_technical_id"])

                if filters.get("type"):
                    conditions.append(self._type_condition(filters["type"]))

                if filters.get("responsible"):
                    # Lo envía el front cuando consulta un técnico: ve los registros
                    # de los que es responsable y, de las Asistencias, solo las que
                    # aún no están en management_status Completado
                    conditions.append(
                        InspectionTechnical.responsible_id == filters["responsible"]
                    )
                    conditions.append(self._not_completed_assistance())

                if filters.get("pending_commercial") == 'true':
                    conditions.append(
                        InspectionTechnical.status == "Listo para cotizar"
                    )
                    conditions.append(self._in_flow())

                    conditions.append(
                        ~exists().where(
                            CommercialTicketManagement.ticket_id
                            == InspectionTechnical.id_inspection
                        )
                    )


                if conditions:
                    stmt = stmt.where(and_(*conditions))


                paginated_stmt = (
                    stmt.order_by(
                        TechnicalTicketManagement.created_at.desc(),
                        TechnicalTicketManagement.id_management_technical.desc(),
                    )
                )
                rows = session.execute(paginated_stmt).all()

                materials_by_ticket = {}
                management_ids = [
                    management.id_management_technical for management, _ in rows
                ]
                if management_ids:
                    materials = session.execute(
                        select(MaterialTechTicket)
                        .where(MaterialTechTicket.tech_ticket.in_(management_ids))
                        .order_by(MaterialTechTicket.id_material)
                    ).scalars().all()
                    for material in materials:
                        materials_by_ticket.setdefault(
                            material.tech_ticket, []
                        ).append(material)

                return [
                    (
                        management,
                        ticket,
                        materials_by_ticket.get(management.id_management_technical, []),
                    )
                    for management, ticket in rows
                ]
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener los tickets técnicos de la base de datos",
                    internal,
                    external,
                )


    def post_ticket_commercial(self, body, internal, external, files=None):
        files = clean_files(files)
        saved_paths = []
        with self.db_telearseg.session_factory() as session:
            try:
                validate_documents(files)
                ticket = session.execute(
                    select(InspectionTechnical).where(
                        InspectionTechnical.id_inspection == body.get('inspection_id')
                    )
                ).scalar_one_or_none()

                if ticket is None:
                    raise CustomAPIException("Inspección no encontrada", 404)
                # El Soporte no pasa por Comercial
                self._ensure_follows_flow(ticket)
                latest = self._get_latest_management(
                    session,
                    CommercialTicketManagement,
                    ticket.id_inspection,
                    CommercialTicketManagement.id_management_commercial,
                )
                if (
                    latest is not None
                    and latest.status_id == self.COMMERCIAL_STATUS_RETURNED_TECHNICAL
                ):
                    raise CustomAPIException(
                        "El registro está devuelto a Técnica; no se puede registrar "
                        "la gestión comercial hasta que Técnica lo vuelva a aprobar",
                        400,
                    )
                if self._assistance_sent_to_financial(session, ticket):
                    # Ya descontó stock con su proforma aprobada
                    raise CustomAPIException(self.ASSISTANCE_APPROVED_LOCKED, 400)

                if body.get('status_id') == 5:
                    # La Asistencia va directo a Financiera; el resto, a Proyectos
                    self._move_on_commercial_approval(session, ticket, body.get('user'))

                else:
                    ticket.management_area = 'Comercial'
                    ticket.next_area = 'Proyectos'

                new_register = CommercialTicketManagement(
                    ticket_id=ticket.id_inspection,
                    origin_id=body.get('origin_id'),
                    type_solution_id=body.get('type_solution_id'),
                    quoted_amount=body.get('quoted_amount'),
                    probability_closing=body.get('probability_closing'),
                    closing_date= datetime.now() if body.get('status_id') == 5 or body.get('status_id') == 6 else None,
                    next_action=body.get('next_action'),
                    responsible_next_action=body.get('responsible_next_action'),
                    requires_technical=body.get('requires_technical'),
                    requires_material=body.get('requires_material'),
                    # scheduled_start_date=body.get('scheduled_start_date'),
                    contract_received=body.get('contract_received'),
                    date_finish=body.get('date_finish'),
                    reason_loss=body.get('reason_loss'),
                    observations=body.get('observations'),
                    status_id=body.get('status_id'),
                    created_by=body.get('user'),
                    updated_by=body.get('user'),
                )

                session.add(new_register)
                session.flush()
                new_register.code_management = self.generate_code_commercial(
                    new_register.id_management_commercial
                )
                sale_quotation = None
                if body.get('sale_quotation'):
                    sale_quotation = self.save_sale_quotation(
                        session,
                        ticket.id_inspection,
                        body['sale_quotation'],
                        body.get('user'),
                        body.get('sales_code')
                    )
                    if new_register.status_id == self.COMMERCIAL_STATUS_APPROVED:
                        self._generate_pending_materials(
                            session, sale_quotation.id_quote, body.get('user')
                        )
                if (
                    new_register.status_id == self.COMMERCIAL_STATUS_APPROVED
                    and self._is_assistance(ticket)
                ):
                    # Asistencia aprobada: descuenta el stock con las cantidades de la proforma
                    sale_quotation = sale_quotation or self._get_latest_quotation(
                        session, ticket.id_inspection
                    )
                    if sale_quotation is not None:
                        self._generate_pending_materials(
                            session, sale_quotation.id_quote, body.get('user')
                        )
                        self._discount_assistance_materials(
                            session, sale_quotation.id_quote, body.get('user')
                        )
                self._save_inspection_documents(
                    session, ticket.id_inspection, files, saved_paths
                )
                session.commit()

            except Exception as exception:
                session.rollback()
                remove_documents(saved_paths)
                logger.error('Error: {}', str(exception), internal=internal, external=external)
                if isinstance(exception, CustomAPIException):
                    raise exception
                
                raise CustomAPIException("Error al insertar en la base de datos", 500)

            finally:
                session.close()

    def get_ticket_commercial(self, filters, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                if filters.get("pending_financial") == "true":
                    # Pendientes de financiero: último seguimiento financiero de tipo Pendiente
                    last_followup = (
                        select(
                            FinancialFollowup.management_commercial_id,
                            func.max(FinancialFollowup.created_at).label("last_followup_at"),
                        )
                        .where(FinancialFollowup.type == self.FOLLOWUP_TYPE_PENDING)
                        .group_by(FinancialFollowup.management_commercial_id)
                        .subquery()
                    )
                else:
                    last_followup = (
                        select(
                            CommercialFollowup.management_commercial_id,
                            func.max(CommercialFollowup.created_at).label("last_followup_at"),
                        )
                        .group_by(CommercialFollowup.management_commercial_id)
                        .subquery()
                    )

                stmt = (
                    select(
                        CommercialTicketManagement,
                        InspectionTechnical,
                        CommercialOrigin.name.label("origin_name"),
                        CommercialTypeSolution.name.label("type_solution_name"),
                        CommercialTicketStatus.name.label("status_name"),
                        last_followup.c.last_followup_at,
                        Users.attributes["fullname"].as_string().label("sales_user_fullname"),
                    )
                    .join(
                        InspectionTechnical,
                        InspectionTechnical.id_inspection
                        == CommercialTicketManagement.ticket_id,
                    )
                    .outerjoin(
                        CommercialOrigin,
                        CommercialOrigin.id_origin
                        == CommercialTicketManagement.origin_id,
                    )
                    .outerjoin(
                        CommercialTypeSolution,
                        CommercialTypeSolution.id_solution
                        == CommercialTicketManagement.type_solution_id,
                    )
                    .outerjoin(
                        CommercialTicketStatus,
                        CommercialTicketStatus.id_status
                        == CommercialTicketManagement.status_id,
                    )
                    .outerjoin(
                        last_followup,
                        last_followup.c.management_commercial_id
                        == CommercialTicketManagement.id_management_commercial,
                    )
                    .outerjoin(
                        Users,
                        Users.user == InspectionTechnical.sales_user,
                    )
                )

                conditions = self._ticket_conditions(
                    filters,
                    CommercialTicketManagement,
                )
                
                

                if filters.get("is_registred") == "true":
                    conditions.append(
                        exists().where(
                            and_(
                                TaskTechnical.inspection_id
                                == CommercialTicketManagement.ticket_id,
                                TaskTechnical.status == "Finalizado"
                            )
                        )
                    )

                if filters.get("pending_financial") == "true":
                    conditions.append(
                        ~exists().where(
                            FinancialTicketManagement.ticket_id
                            == CommercialTicketManagement.ticket_id
                        )
                )

                if filters.get("ticket_commercial_id") is not None:
                    conditions.append(CommercialTicketManagement.id_management_commercial == filters["ticket_commercial_id"])

                if filters.get("sales_user"):
                    conditions.append(InspectionTechnical.sales_user == filters["sales_user"])

                for filter_name in (
                    "origin_id",
                    "type_solution_id",
                    "status_id",
                ):
                    value = filters.get(filter_name)
                    if value is not None and value != "":
                        conditions.append(
                            getattr(CommercialTicketManagement, filter_name) == value
                        )

                if conditions:
                    stmt = stmt.where(and_(*conditions))

                rows = session.execute(
                    stmt.order_by(CommercialTicketManagement.created_at.desc())
                ).all()

                quotations = self._get_sale_quotations(
                    session, {row[1].id_inspection for row in rows}
                )
                return [
                    (*row, quotations.get(row[1].id_inspection))
                    for row in rows
                ]
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener los tickets comerciales de la base de datos",
                    internal,
                    external,
                )


    def get_inspection_materials(self, inspection_id, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                stmt = (
                    select(MaterialTechTicket, TechnicalEquipment)
                    .join(
                        TechnicalTicketManagement,
                        TechnicalTicketManagement.id_management_technical
                        == MaterialTechTicket.tech_ticket,
                    )
                    .outerjoin(
                        TechnicalEquipment,
                        TechnicalEquipment.id_equipment
                        == MaterialTechTicket.material_id,
                    )
                    .where(TechnicalTicketManagement.inspection_id == inspection_id)
                    .order_by(MaterialTechTicket.id_material)
                )

                return session.execute(stmt).all()
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener los materiales de la inspección",
                    internal,
                    external,
                )

    def get_history_area(self, inspection_id, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                stmt = (
                    select(HistoryAreaTicket)
                    .join(
                        InspectionTechnical,
                        InspectionTechnical.id_inspection
                        == HistoryAreaTicket.ticket_id,
                    )
                    .where(InspectionTechnical.id_inspection == inspection_id)
                    .order_by(HistoryAreaTicket.created_at.desc())
                )

                return session.execute(stmt).scalars().all()
            
            except Exception as exception:
                logger.error('Error: {}', str(exception), internal=internal, external=external)
                if isinstance(exception, CustomAPIException):
                    raise exception

                raise CustomAPIException("Error al obtener en la base de datos", 500)

    @staticmethod
    def _ticket_conditions(filters, management_model):
        conditions = []
        if filters.get("start_date"):
            conditions.append(management_model.created_at >= filters["start_date"])
        if filters.get("end_date"):
            conditions.append(management_model.created_at <= filters["end_date"])
        if (filters.get("is_registred") == 'true'):
            conditions.append(management_model.status_id == 5)
            conditions.append(InspectionTechnical.management_area == "Proyectos")
        if filters.get("pending_financial") == "true":
            conditions.append(
                InspectionTechnical.management_area
                == "Financiera"
            )
            conditions.append(
                InspectionTechnical.next_area
                == "Financiera"
            )
        if filters.get("inspection_id") is not None:
            conditions.append(InspectionTechnical.id_inspection == filters["inspection_id"])
        if filters.get("status"):
            conditions.append(management_model.status == filters["status"])
        if filters.get("responsible_id"):
            conditions.append(
                InspectionTechnical.responsible_name == filters["responsible_id"]
            )
        if filters.get("client_id") is not None:
            conditions.append(InspectionTechnical.client_id.in_(filters["client_id"]))
        if filters.get("ubication_id") is not None:
            conditions.append(
                InspectionTechnical.ubication_id == filters["ubication_id"]
            )
        if filters.get("priority"):
            conditions.append(InspectionTechnical.priority == filters["priority"])
        return conditions
    
    @staticmethod
    def _raise_database_error(exception, message, internal, external):
        logger.error(
            'Error: {}',
            str(exception),
            internal=internal,
            external=external,
        )
        if isinstance(exception, CustomAPIException):
            raise exception
        raise CustomAPIException(message, 500)


    def get_type_solution(self, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                result = session.execute(
                    select(CommercialTypeSolution)
                )
                data = [
                    {
                        "id_solution": c.id_solution,
                        "name": c.name,
                        "created_at": c.created_at,
                        "created_by": c.created_by,
                    }
                    for c in result.scalars().all()
                ]
                return data
            except Exception as exception:
                logger.error('Error: {}', str(exception), internal=internal, external=external)
                if isinstance(exception, CustomAPIException):
                    raise exception

                raise CustomAPIException("Error al obtener en la base de datos", 500)


    def get_commercial_ticket_status(self, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                result = session.execute(
                    select(CommercialTicketStatus)
                )
                data = [
                    {
                        "id_status": c.id_status,
                        "name": c.name,
                        "created_at": c.created_at,
                        "created_by": c.created_by,
                    }
                    for c in result.scalars().all()
                ]
                return data
            except Exception as exception:
                logger.error('Error: {}', str(exception), internal=internal, external=external)
                if isinstance(exception, CustomAPIException):
                    raise exception

                raise CustomAPIException("Error al obtener en la base de datos", 500)

    def post_provider(self, data, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                provider = ProvidersProducts(**data)
                session.add(provider)
                session.commit()
                return provider.id_provider
            except Exception as exception:
                session.rollback()
                logger.error('Error: {}', str(exception), internal=internal, external=external)
                if isinstance(exception, CustomAPIException):
                    raise exception

                raise CustomAPIException("Error al guardar en la base de datos", 500)

    def get_providers(self, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                result = session.execute(
                    select(ProvidersProducts)
                )
                data = [
                    {
                        "id_provider": c.id_provider,
                        "name": c.provider,
                        "ruc": c.ruc,
                        "address": c.address,
                        "seller": c.seller,
                        "number_contact": c.number_contact,
                        "email": c.email,
                        "status": c.status,
                        "created_at": c.created_at,
                        "created_by": c.created_by,
                    }
                    for c in result.scalars().all()
                ]
                return data
            except Exception as exception:
                logger.error('Error: {}', str(exception), internal=internal, external=external)
                if isinstance(exception, CustomAPIException):
                    raise exception

                raise CustomAPIException("Error al obtener en la base de datos", 500)

    def get_commercial_origin(self, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                result = session.execute(
                    select(CommercialOrigin)
                )
                data = [
                    {
                        "id_origin": c.id_origin,
                        "name": c.name,
                        "created_at": c.created_at,
                        "created_by": c.created_by,
                    }
                    for c in result.scalars().all()
                ]
                return data
            except Exception as exception:
                logger.error('Error: {}', str(exception), internal=internal, external=external)
                if isinstance(exception, CustomAPIException):
                    raise exception

                raise CustomAPIException("Error al obtener en la base de datos", 500)

    def post_ticket_financial(self, body, internal, external, files=None):
        files = clean_files(files)
        saved_paths = []
        with self.db_telearseg.session_factory() as session:
            try:
                validate_documents(files)
                ticket = session.execute(
                    select(InspectionTechnical).where(
                        InspectionTechnical.id_inspection == body.get("inspection_id")
                    )
                ).scalar_one_or_none()
                if ticket is None:
                    raise CustomAPIException("Inspección no encontrada", 404)

                ticket.management_area = "Financiera"

                invoice_price, amount_pending = self._invoice_from_quotation(
                    session, ticket.id_inspection, body
                )

                if body.get("status") == "Cobrada":
                    ticket.status = "Finalizado"

                financial_management = FinancialTicketManagement(
                    ticket_id=ticket.id_inspection,
                    type_management=body.get("type_management"),
                    amount_pending=amount_pending,
                    amount_paid=body.get("amount_paid"),
                    invoice_price=invoice_price,
                    observations=body.get("observations"),
                    status=body.get("status"),
                    date_document=body.get("date_document"),
                    number_document=body.get("number_document"),
                    created_by=body.get("user"),
                    updated_by=body.get("user"),
                )
                session.add(financial_management)
                session.flush()
                financial_management.code_management = self.generate_code_financial(
                    financial_management.id_management_financial
                )
                self._save_inspection_documents(
                    session, ticket.id_inspection, files, saved_paths
                )
                session.commit()
            except Exception as exception:
                session.rollback()
                remove_documents(saved_paths)
                self._raise_database_error(
                    exception,
                    "Error al insertar la gestión financiera en la base de datos",
                    internal,
                    external,
                )
            finally:
                session.close()

    def get_ticket_financial(self, filters, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                last_followup = (
                    select(
                        FinancialFollowup.management_financial_id,
                        func.max(FinancialFollowup.created_at).label("last_followup_at"),
                    )
                    .where(FinancialFollowup.type == self.FOLLOWUP_TYPE_REGISTERED)
                    .group_by(FinancialFollowup.management_financial_id)
                    .subquery()
                )

                stmt = (
                    select(
                        FinancialTicketManagement,
                        InspectionTechnical,
                        last_followup.c.last_followup_at,
                    )
                    .join(
                        InspectionTechnical,
                        InspectionTechnical.id_inspection
                        == FinancialTicketManagement.ticket_id,
                    )
                    .outerjoin(
                        last_followup,
                        last_followup.c.management_financial_id
                        == FinancialTicketManagement.id_management_financial,
                    )
                )
                conditions = self._ticket_conditions(
                    filters,
                    FinancialTicketManagement,
                )

                if filters.get("type_management"):
                    conditions.append(
                        FinancialTicketManagement.type_management
                        == filters["type_management"]
                    )
                if filters.get("code_management"):
                    conditions.append(
                        FinancialTicketManagement.code_management
                        == filters["code_management"]
                    )
                if filters.get("user"):
                    conditions.append(
                        FinancialTicketManagement.created_by == filters["user"]
                    )

                if filters.get("ticket_financial_id") is not None:
                    conditions.append(FinancialTicketManagement.id_management_financial == filters["ticket_financial_id"])

                if conditions:
                    stmt = stmt.where(and_(*conditions))

                return session.execute(
                    stmt.order_by(
                        FinancialTicketManagement.created_at.desc(),
                        FinancialTicketManagement.id_management_financial.desc(),
                    )
                ).all()
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener los tickets financieros de la base de datos",
                    internal,
                    external,
                )

    def update_ticket_technical(self, body, internal, external, files=None):
        """Los documentos recibidos se agregan a los de la inspección; los
        existentes no se modifican."""
        files = clean_files(files)
        saved_paths = []
        with self.db_telearseg.session_factory() as session:
            try:
                validate_documents(files)
                self._validate_update_body(body, "inspection_id")
                ticket = self._get_inspection(session, body.get("inspection_id"))

                management_stmt = select(TechnicalTicketManagement).where(
                    TechnicalTicketManagement.inspection_id == ticket.id_inspection
                )
                if body.get("id_management_technical") is not None:
                    management_stmt = management_stmt.where(
                        TechnicalTicketManagement.id_management_technical
                        == body.get("id_management_technical")
                    )
                management = session.execute(
                    management_stmt.order_by(
                        TechnicalTicketManagement.id_management_technical.desc()
                    )
                ).scalars().first()

                if management is None:
                    raise CustomAPIException("Gestión técnica no encontrada", 404)

                was_returned = management.status == self.TECHNICAL_STATUS_RETURNED
                self._apply_fields(
                    management,
                    body,
                    {
                        "description": "description",
                        "status": "status",
                    },
                )
                if was_returned and not body.get("status"):
                    # Corregido por el técnico: vuelve a la cola de aprobación
                    management.status = self.TECHNICAL_STATUS_PENDING_APPROVAL
                self._set_updated_by(body, management)

                if "materials" in body:
                    self._save_technical_materials(
                        session, management, body.get("materials") or [], body.get("user")
                    )

                if body.get("status") == 'Listo para cotizar':
                    ticket.management_area = "Comercial"
                    ticket.next_area = "Financiero"

                    new_history_area = HistoryAreaTicket(
                        ticket_id=ticket.id_inspection,
                        previous_area="Técnica",
                        current_area="Comercial",
                        created_by=body.get('user')
                    )

                    session.add(new_history_area)
                    self._resume_returned_commercial(
                        session, ticket.id_inspection, body.get('user')
                    )


                self._save_inspection_documents(
                    session, ticket.id_inspection, files, saved_paths
                )
                session.commit()
            except Exception as exception:
                session.rollback()
                remove_documents(saved_paths)
                self._raise_database_error(
                    exception,
                    "Error al actualizar la gestión técnica",
                    internal,
                    external,
                )
            finally:
                session.close()

    def update_ticket_commercial(self, body, internal, external, files=None):
        """Los documentos recibidos se agregan a los de la inspección; los
        existentes no se modifican."""
        files = clean_files(files)
        saved_paths = []
        with self.db_telearseg.session_factory() as session:
            try:
                validate_documents(files)
                self._validate_update_body(body, "inspection_id")
                ticket = self._get_inspection(session, body.get("inspection_id"))
                management = self._get_latest_management(
                    session,
                    CommercialTicketManagement,
                    ticket.id_inspection,
                    CommercialTicketManagement.id_management_commercial,
                )
                if management is None:
                    raise CustomAPIException("Gestión comercial no encontrada", 404)
                if (
                    management.status_id == self.COMMERCIAL_STATUS_RETURNED_TECHNICAL
                    or ticket.management_area == "Técnica"
                ):
                    raise CustomAPIException(
                        "El registro está devuelto a Técnica; no se puede editar "
                        "hasta que Técnica lo vuelva a aprobar",
                        400,
                    )
                if self._assistance_sent_to_financial(session, ticket) and (
                    body.get('sale_quotation')
                    or (
                        body.get('status_id') is not None
                        and body.get('status_id') != self.COMMERCIAL_STATUS_APPROVED
                    )
                ):
                    # La proforma aprobada ya descontó stock: no cambian ni ella ni el estado
                    raise CustomAPIException(self.ASSISTANCE_APPROVED_LOCKED, 400)
                approving = (
                    body.get('status_id') == self.COMMERCIAL_STATUS_APPROVED
                    and ticket.management_area == 'Comercial'
                )

                # Aprobada, perdida, etc. ya no se edita: la proforma aprobada alimenta a bodega
                # if management.status_id != self.COMMERCIAL_STATUS_PENDING:
                #     raise CustomAPIException(
                #         "Solo se puede editar una gestión comercial en estado pendiente",
                #         400,
                #     )

                self._apply_fields(
                    management,
                    body,
                    {
                        "origin_id": "origin_id",
                        "type_solution_id": "type_solution_id",
                        "quoted_amount": "quoted_amount",
                        "probability_closing": "probability_closing",
                        "closing_date": "closing_date",
                        "next_action": "next_action",
                        "responsible_next_action": "responsible_next_action",
                        "requires_technical": "requires_technical",
                        "requires_material": "requires_material",
                        # "scheduled_start_date": "scheduled_start_date",
                        "contract_received": "contract_received",
                        "date_finish": "date_finish",
                        "reason_loss": "reason_loss",
                        "observations": "observations",
                        "status_id": "status_id",
                    },
                )
                self._set_updated_by(body, management)

                sale_quotation = None
                if body.get('sale_quotation'):
                    sale_quotation = self.save_sale_quotation(
                        session,
                        ticket.id_inspection,
                        body['sale_quotation'],
                        body.get('user'),
                        body.get('sales_code')
                    )

                if management.status_id == self.COMMERCIAL_STATUS_APPROVED:
                    sale_quotation = sale_quotation or self._get_latest_quotation(
                        session, ticket.id_inspection
                    )
                    if sale_quotation is not None:
                        self._generate_pending_materials(
                            session, sale_quotation.id_quote, body.get('user')
                        )

                if approving:
                    # La Asistencia va directo a Financiera; el resto, a Proyectos
                    self._move_on_commercial_approval(session, ticket, body.get('user'))
                    if self._is_assistance(ticket) and sale_quotation is not None:
                        # Descuenta el stock con las cantidades de la proforma aprobada
                        self._discount_assistance_materials(
                            session, sale_quotation.id_quote, body.get('user')
                        )

                self._save_inspection_documents(
                    session, ticket.id_inspection, files, saved_paths
                )
                session.commit()
            except Exception as exception:
                session.rollback()
                remove_documents(saved_paths)
                self._raise_database_error(
                    exception,
                    "Error al actualizar la gestión comercial",
                    internal,
                    external,
                )
            finally:
                session.close()

    def update_ticket_financial(self, body, internal, external, files=None):
        """Los documentos recibidos se agregan a los de la inspección; los
        existentes no se modifican."""
        files = clean_files(files)
        saved_paths = []
        with self.db_telearseg.session_factory() as session:
            try:
                validate_documents(files)
                self._validate_update_body(body, "inspection_id")
                ticket = self._get_inspection(session, body.get("inspection_id"))
                if body.get("id_management_financial") is not None:
                    # Se edita la gestión elegida en la tabla, no solo la última
                    management = session.execute(
                        select(FinancialTicketManagement).where(
                            FinancialTicketManagement.id_management_financial
                            == body["id_management_financial"],
                            FinancialTicketManagement.ticket_id
                            == ticket.id_inspection,
                        )
                    ).scalars().first()
                else:
                    management = self._get_latest_management(
                        session,
                        FinancialTicketManagement,
                        ticket.id_inspection,
                        FinancialTicketManagement.id_management_financial,
                    )
                if management is None:
                    raise CustomAPIException("Gestión financiera no encontrada", 404)

                self._apply_fields(
                    management,
                    body,
                    {
                        "type_management": "type_management",
                        "amount_paid": "amount_paid",
                        "observations": "observations",
                        "status": "status",
                        "date_document": "date_document",
                        "number_document": "number_document",
                    },
                )
                management.invoice_price, management.amount_pending = (
                    self._invoice_from_quotation(
                        session,
                        ticket.id_inspection,
                        {"amount_paid": management.amount_paid},
                    )
                )
                self._set_updated_by(body, management)

                # Igual que al registrar: una factura cobrada finaliza el ticket
                if management.status == "Cobrada":
                    ticket.status = "Finalizado"

                self._save_inspection_documents(
                    session, ticket.id_inspection, files, saved_paths
                )
                session.commit()
            except Exception as exception:
                session.rollback()
                remove_documents(saved_paths)
                self._raise_database_error(
                    exception,
                    "Error al actualizar la gestión financiera",
                    internal,
                    external,
                )
            finally:
                session.close()

    def assign_sales_user(self, body, internal, external):
        """Asigna el asesor comercial (sales_user) de la inspección.
        sales_user solo se llena desde este flujo."""
        with self.db_telearseg.session_factory() as session:
            try:
                self._validate_update_body(body, "id_inspection")
                self._validate_update_body(body, "user")
                user = str(body.get("user")).strip()
                if not user:
                    raise CustomAPIException("El campo user es obligatorio para actualizar el registro", 400)

                inspection = self._get_inspection(session, body.get("id_inspection"))
                inspection.sales_user = user

                session.commit()
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al asignar el asesor comercial",
                    internal,
                    external,
                )
            finally:
                session.close()

    def approve_technical_inspection(self, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:

                register_technical = session.execute(
                    select(TechnicalTicketManagement).where(
                        TechnicalTicketManagement.inspection_id == body.get("id_inspection")
                    )
                ).scalar_one_or_none()
        
                if register_technical is None:
                    raise CustomAPIException("Registro técnico no encontrado", 404)

                register_technical.status = "Aprobado"
                register_technical.updated_by = body.get("user")

                self._validate_update_body(body, "id_inspection")
                self._validate_update_body(body, "user")
                inspection = self._get_inspection(session, body.get("id_inspection"))
                self._ensure_not_support(inspection)

                inspection.status = "Listo para cotizar"
                inspection.updated_by = body.get("user")
                if inspection.type == self.ASSISTANCE_TYPE:
                    # La Asistencia se aprueba con su registro técnico
                    inspection.approve_support = True

                if inspection.management_area == "Técnica":
                    inspection.management_area = "Comercial"
                    inspection.next_area = "Proyectos"

                    new_history_area = HistoryAreaTicket(
                        ticket_id=inspection.id_inspection,
                        previous_area="Técnica",
                        current_area="Comercial",
                        created_by=body.get("user")
                    )
                    session.add(new_history_area)

                self._resume_returned_commercial(
                    session, inspection.id_inspection, body.get("user")
                )
                session.commit()
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al aprobar la inspección técnica",
                    internal,
                    external,
                )
            finally:
                session.close()

    def approve_support(self, body, internal, external):
        """Marca un Soporte como aprobado (approve_support = true); se queda en Técnica.
        La Asistencia sigue el flujo normal y se aprueba con su registro técnico
        (approve_technical_inspection)."""
        with self.db_telearseg.session_factory() as session:
            try:
                self._validate_update_body(body, "id_inspection")
                self._validate_update_body(body, "user")
                inspection = self._get_inspection(session, body.get("id_inspection"))

                if inspection.type == self.ASSISTANCE_TYPE:
                    raise CustomAPIException(
                        "La asistencia se aprueba con su registro técnico", 400
                    )
                if inspection.type != self.SUPPORT_TYPE:
                    raise CustomAPIException(
                        "Solo se pueden aprobar registros de tipo Soporte", 400
                    )
                if inspection.approve_support:
                    raise CustomAPIException(
                        "El soporte ya se encuentra aprobado", 400
                    )

                inspection.approve_support = True
                inspection.updated_by = body.get("user")
                session.commit()
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al aprobar el soporte",
                    internal,
                    external,
                )
            finally:
                session.close()

    def approve_ticket_commercial(self, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                ticket_commercial = session.execute(
                    select(CommercialTicketManagement).where(
                        CommercialTicketManagement.id_management_commercial == body.get("id_commercial_ticket")
                    )
                ).scalar_one_or_none()

                if ticket_commercial is None:
                    raise CustomAPIException("Ticket comercial no encontrado", 404)

                if ticket_commercial.status_id != 5:
                    raise CustomAPIException("Ticket comercial no esta aprobado", 404)


                ticket_management = session.execute(
                    select(InspectionTechnical).where(
                        InspectionTechnical.id_inspection == ticket_commercial.ticket_id
                    )
                ).scalar_one_or_none()

                if ticket_management is None:
                    raise CustomAPIException("Ticket no encontrado", 404)
                # La Asistencia pasa de Comercial a Financiera al aprobarse; solo
                # las antiguas, que siguen en Proyectos, usan este paso
                if (
                    self._is_assistance(ticket_management)
                    and ticket_management.management_area != "Proyectos"
                ):
                    raise CustomAPIException(
                        "Las asistencias pasan directo de Comercial a Financiera", 400
                    )

                ticket_management.management_area = "Financiera"
                ticket_management.next_area = "Financiera"
                ticket_management.updated_by = body.get("user")
                ticket_management.updated_at = datetime.now()

                new_history_area = HistoryAreaTicket(
                    ticket_id=ticket_management.id_inspection,
                    previous_area="Proyectos",
                    current_area="Financiera",
                    created_by=body.get('user')
                )

                session.add(new_history_area)
                session.commit()
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al insertar la gestión financiera en la base de datos",
                    internal,
                    external,
                )
            finally:
                session.close()


    def get_followup_commercial(self, filters, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                stmt = (
                    select(
                        CommercialFollowup
                    )
                    .order_by(CommercialFollowup.created_at.desc())
                )
                
                if filters.get("id_commercial"):
                    stmt = stmt.where(CommercialFollowup.management_commercial_id == filters["id_commercial"])

                if filters.get("user"):
                    stmt = stmt.where(CommercialFollowup.created_by == filters["user"])

                rows = session.execute(stmt).scalars().all()                
                return rows
            
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener los seguimientos de la base de datos",
                    internal,
                    external,
                )


    def get_followup_financial(self, filters, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                stmt = (
                    select(
                        FinancialFollowup
                    )
                    .order_by(FinancialFollowup.created_at.desc())
                )
                
                if filters.get("type"):
                    stmt = stmt.where(FinancialFollowup.type == filters["type"])

                if filters.get("id_financial"):
                    stmt = stmt.where(FinancialFollowup.management_financial_id == filters["id_financial"])

                if filters.get("id_commercial"):
                    stmt = stmt.where(FinancialFollowup.management_commercial_id == filters["id_commercial"])

                if filters.get("user"):
                    stmt = stmt.where(FinancialFollowup.created_by == filters["user"])

                rows = session.execute(stmt).scalars().all()                
                return rows
            
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener los seguimientos de la base de datos",
                    internal,
                    external,
                )


    def new_followup_financial(self, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                followup_type = body.get("type")

                if followup_type == self.FOLLOWUP_TYPE_PENDING:
                    # Pendiente: la gestión financiera aún no existe, se vincula a la comercial
                    ticket_commercial = session.execute(
                        select(CommercialTicketManagement).where(
                            CommercialTicketManagement.id_management_commercial == body.get("management_commercial_id")
                        )
                    ).scalar_one_or_none()

                    if ticket_commercial is None:
                        raise CustomAPIException("Ticket comercial no encontrado", 404)

                    new_followup = FinancialFollowup(
                        management_commercial_id=body.get("management_commercial_id"),
                        observations=body.get("observations"),
                        type=followup_type,
                        created_by=body.get("user")
                    )
                elif followup_type == self.FOLLOWUP_TYPE_REGISTERED:
                    ticket_financial = session.execute(
                        select(FinancialTicketManagement).where(
                            FinancialTicketManagement.id_management_financial == body.get("management_financial_id")
                        )
                    ).scalar_one_or_none()

                    if ticket_financial is None:
                        raise CustomAPIException("Ticket financiero no encontrado", 404)

                    new_followup = FinancialFollowup(
                        management_financial_id=body.get("management_financial_id"),
                        observations=body.get("observations"),
                        type=followup_type,
                        created_by=body.get("user")
                    )
                else:
                    raise CustomAPIException("Tipo de seguimiento no válido", 400)

                session.add(new_followup)
                session.commit()
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al insertar la gestión financiera en la base de datos",
                    internal,
                    external,
                )
            finally:
                session.close()


    RETURNABLE_AREAS = ("Proyectos", "Financiera")

    def return_to_commercial(self, data, internal, external):
        """Devuelve a Comercial un registro aprobado que está en Proyectos o
        Financiera: la gestión comercial vuelve a Pendiente para editarla. La
        proforma, sus pendientes y el proyecto se conservan; al editar la
        proforma los pendientes se re-vinculan (save_sale_quotation)."""
        with self.db_telearseg.session_factory() as session:
            try:
                inspection = self._get_inspection(session, data["inspection_id"])
                previous_area = inspection.management_area
                if previous_area == "Comercial":
                    raise CustomAPIException("El registro ya está en Comercial", 400)
                if previous_area not in self.RETURNABLE_AREAS:
                    raise CustomAPIException(
                        "Solo se pueden devolver registros de Proyectos o Financiera", 400
                    )
                if inspection.status == "Finalizado":
                    raise CustomAPIException(
                        "El registro está finalizado; no se puede devolver", 400
                    )
                if self._is_assistance(inspection) and previous_area == "Financiera":
                    raise CustomAPIException(
                        "Las asistencias no se pueden devolver a Comercial", 400
                    )

                management = self._get_latest_management(
                    session,
                    CommercialTicketManagement,
                    inspection.id_inspection,
                    CommercialTicketManagement.id_management_commercial,
                )
                if management is None:
                    raise CustomAPIException("Gestión comercial no encontrada", 404)
                if management.status_id != self.COMMERCIAL_STATUS_APPROVED:
                    raise CustomAPIException("La gestión comercial no está aprobada", 400)

                self._ensure_returnable(session, inspection.id_inspection, "Comercial")

                user = data.get("user")
                management.status_id = self.COMMERCIAL_STATUS_PENDING
                management.updated_by = user
                inspection.management_area = "Comercial"
                inspection.next_area = "Proyectos"
                inspection.updated_by = user
                inspection.updated_at = datetime.now()
                session.add(HistoryAreaTicket(
                    ticket_id=inspection.id_inspection,
                    previous_area=previous_area,
                    current_area="Comercial",
                    reason=data["reason"],
                    created_by=user,
                ))
                session.add(CommercialFollowup(
                    management_commercial_id=management.id_management_commercial,
                    observations=f"Devuelto a Comercial desde {previous_area}: {data['reason']}",
                    created_by=user,
                ))
                session.commit()
                return {
                    "inspection_id": inspection.id_inspection,
                    "previous_area": previous_area,
                    "management_area": inspection.management_area,
                    "commercial_status_id": management.status_id,
                }
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al devolver el registro a Comercial",
                    internal,
                    external,
                )

    def return_to_technical(self, data, internal, external):
        """Devuelve a Técnica un registro que está en Comercial y cuya gestión
        comercial no está aprobada. El registro técnico queda Devuelto para
        corregirlo y la gestión comercial queda congelada; la proforma y sus
        pendientes se conservan (sección 6 de docs/logica-negocio.md)."""
        with self.db_telearseg.session_factory() as session:
            try:
                inspection = self._get_inspection(session, data["inspection_id"])
                if inspection.status == "Finalizado":
                    raise CustomAPIException(
                        "El registro está finalizado; no se puede devolver", 400
                    )
                if inspection.management_area == "Técnica":
                    raise CustomAPIException("El registro ya está en Técnica", 400)
                if inspection.management_area != "Comercial":
                    raise CustomAPIException(
                        "Solo se pueden devolver a Técnica registros de Comercial", 400
                    )

                technical = session.execute(
                    select(TechnicalTicketManagement)
                    .where(TechnicalTicketManagement.inspection_id == inspection.id_inspection)
                    .order_by(TechnicalTicketManagement.id_management_technical.desc())
                ).scalars().first()
                if technical is None:
                    # Ej: Asistencias aprobadas con el flujo anterior (sin registro técnico)
                    raise CustomAPIException(
                        "El registro no tiene registro técnico; no se puede devolver a Técnica",
                        400,
                    )

                management = self._get_latest_management(
                    session,
                    CommercialTicketManagement,
                    inspection.id_inspection,
                    CommercialTicketManagement.id_management_commercial,
                )
                if management is None:
                    raise CustomAPIException("Gestión comercial no encontrada", 404)
                if management.status_id == self.COMMERCIAL_STATUS_APPROVED:
                    raise CustomAPIException(
                        "La gestión comercial está aprobada; no se puede devolver a Técnica",
                        400,
                    )
                if management.status_id == self.COMMERCIAL_STATUS_RETURNED_TECHNICAL:
                    raise CustomAPIException("El registro ya fue devuelto a Técnica", 400)

                # El proyecto se armó con una proforma aprobada antes
                has_project = session.execute(
                    select(exists().where(
                        TaskTechnical.inspection_id == inspection.id_inspection
                    ))
                ).scalar()
                if has_project:
                    raise CustomAPIException(
                        "El registro ya tiene un proyecto; no se puede devolver a Técnica",
                        400,
                    )
                self._ensure_returnable(session, inspection.id_inspection, "Técnica")

                user = data.get("user")
                technical.status = self.TECHNICAL_STATUS_RETURNED
                technical.updated_by = user
                management.status_id = self.COMMERCIAL_STATUS_RETURNED_TECHNICAL
                management.updated_by = user
                inspection.status = self.INSPECTION_STATUS_RETURNED_TECHNICAL
                inspection.management_area = "Técnica"
                inspection.next_area = "Comercial"
                inspection.updated_by = user
                inspection.updated_at = datetime.now()
                session.add(HistoryAreaTicket(
                    ticket_id=inspection.id_inspection,
                    previous_area="Comercial",
                    current_area="Técnica",
                    reason=data["reason"],
                    created_by=user,
                ))
                session.add(CommercialFollowup(
                    management_commercial_id=management.id_management_commercial,
                    observations=f"Devuelto a Técnica: {data['reason']}",
                    created_by=user,
                ))
                session.commit()
                return {
                    "inspection_id": inspection.id_inspection,
                    "management_area": inspection.management_area,
                    "technical_status": technical.status,
                    "commercial_status_id": management.status_id,
                }
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al devolver el registro a Técnica",
                    internal,
                    external,
                )

    @staticmethod
    def _ensure_returnable(session, inspection_id, target_area):
        """Validaciones comunes de las devoluciones: sin entregas ni gestiones
        financieras."""
        # Las entregas referencian las líneas de la proforma: no se podría editar
        delivered = session.execute(
            select(exists().where(
                MaterialDeliveryHistory.quote_id == SaleQuotation.id_quote,
                SaleQuotation.inspection_id == inspection_id,
            ))
        ).scalar()
        if delivered:
            raise CustomAPIException(
                "La proforma ya tiene materiales entregados; "
                f"no se puede devolver a {target_area}",
                400,
            )

        financial_statuses = session.execute(
            select(FinancialTicketManagement.status).where(
                FinancialTicketManagement.ticket_id == inspection_id
            )
        ).scalars().all()
        if "Cobrada" in financial_statuses:
            raise CustomAPIException(
                "El registro tiene facturas cobradas; no se puede devolver", 400
            )
        if financial_statuses:
            raise CustomAPIException(
                "El registro tiene gestiones financieras registradas; "
                f"elimínelas antes de devolverlo a {target_area}",
                400,
            )

    def _resume_returned_commercial(self, session, inspection_id, user):
        """Al volver a aprobar Técnica, la gestión comercial congelada pasa a
        Pendiente para que Comercial revise la proforma."""
        management = self._get_latest_management(
            session,
            CommercialTicketManagement,
            inspection_id,
            CommercialTicketManagement.id_management_commercial,
        )
        if (
            management is None
            or management.status_id != self.COMMERCIAL_STATUS_RETURNED_TECHNICAL
        ):
            return
        management.status_id = self.COMMERCIAL_STATUS_PENDING
        management.updated_by = user
        session.add(CommercialFollowup(
            management_commercial_id=management.id_management_commercial,
            observations="Aprobado nuevamente por Técnica; revisar la proforma",
            created_by=user,
        ))

    def new_followup_commercial(self, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                ticket_commercial = session.execute(
                    select(CommercialTicketManagement).where(
                        CommercialTicketManagement.id_management_commercial == body.get("management_commercial_id")
                    )
                ).scalar_one_or_none()

                if ticket_commercial is None:
                    raise CustomAPIException("Ticket comercial no encontrado", 404)

                new_followup = CommercialFollowup(
                    management_commercial_id=body.get("management_commercial_id"),
                    observations=body.get("observations"),
                    created_by=body.get("user")
                )

                session.add(new_followup)
                session.commit()
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al insertar la gestión financiera en la base de datos",
                    internal,
                    external,
                )
            finally:
                session.close()


    def get_inspection_technical(self, filters, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                # task_id_subquery = (
                #     select(TaskTechnical.id_task)
                #     .where(
                #         TaskTechnical.inspection_id
                #         == InspectionTechnical.id_inspection
                #     )
                #     .limit(1)
                #     .scalar_subquery()
                # )

                # Estado del último registro comercial de la inspección
                commercial_status_id = (
                    select(CommercialTicketManagement.status_id)
                    .where(CommercialTicketManagement.ticket_id == InspectionTechnical.id_inspection)
                    .order_by(CommercialTicketManagement.id_management_commercial.desc())
                    .limit(1)
                    .correlate(InspectionTechnical)
                    .scalar_subquery()
                )
                commercial_status = (
                    select(CommercialTicketStatus.name)
                    .where(CommercialTicketStatus.id_status == commercial_status_id)
                    .scalar_subquery()
                )

                # Proforma de la inspección (una por inspección; por si acaso, la última)
                sale_quote_id = (
                    select(SaleQuotation.id_quote)
                    .where(SaleQuotation.inspection_id == InspectionTechnical.id_inspection)
                    .order_by(SaleQuotation.id_quote.desc())
                    .limit(1)
                    .correlate(InspectionTechnical)
                    .scalar_subquery()
                )

                sale_quote_total = (
                    select(SaleQuotation.total)
                    .where(SaleQuotation.id_quote == sale_quote_id)
                    .scalar_subquery()
                )

                stmt = select(
                    InspectionTechnical,
                    TaskTechnical.id_task.label("project_id"),
                    commercial_status_id.label("commercial_status_id"),
                    commercial_status.label("commercial_status"),
                    TechnicalTicketManagement.id_management_technical.label("technical_id"),
                    TechnicalTicketManagement.description.label("technical_description"),
                    ClientCompany.identity.label("identity"),
                    ClientCompany.company_name.label("company_name"),
                    ClientCompany.id_company.label("client_company_id"),
                    sale_quote_id.label("sale_quote_id"),
                    sale_quote_total.label("sale_quote_total"),
                    Users.attributes["fullname"].as_string().label("sales_user_fullname"),
                ).outerjoin(
                    TaskTechnical,
                    TaskTechnical.inspection_id == InspectionTechnical.id_inspection
                ).outerjoin(
                    TechnicalTicketManagement,
                    TechnicalTicketManagement.inspection_id == InspectionTechnical.id_inspection
                ).outerjoin(
                    # inspección -> cliente -> empresa del cliente (RUC)
                    Client,
                    Client.id_client == InspectionTechnical.client_id
                ).outerjoin(
                    ClientCompany,
                    ClientCompany.id_company == Client.client_company_id
                ).outerjoin(
                    Users,
                    Users.user == InspectionTechnical.sales_user,
                )

                conditions = []

                if filters.get("start_date"):
                    conditions.append(InspectionTechnical.created_at >= filters["start_date"])
                if filters.get("end_date"):
                    conditions.append(InspectionTechnical.created_at <= filters["end_date"])
                if filters.get("inspection_id") is not None:
                    conditions.append(InspectionTechnical.id_inspection == filters["inspection_id"])
                if filters.get("status"):
                    conditions.append(InspectionTechnical.status == filters["status"])
                if filters.get("responsible"):
                    conditions.append(InspectionTechnical.responsible_id == filters["responsible"])
                if filters.get("responsible") or filters.get("responsible_id"):
                    # Consulta de un técnico (igual que GET /register-technical): las
                    # Asistencias en management_status Completado no se le muestran
                    conditions.append(self._not_completed_assistance())
                if filters.get("client_id") is not None:
                    conditions.append(InspectionTechnical.client_id.in_(filters["client_id"]))
                if filters.get("ubication_id") is not None:
                    conditions.append(InspectionTechnical.ubication_id == filters["ubication_id"])
                if filters.get("priority"):
                    conditions.append(InspectionTechnical.priority == filters["priority"])
                if filters.get("id_inspection"):
                    conditions.append(InspectionTechnical.id_inspection == filters["id_inspection"])
                if filters.get("responsible_id"):
                    conditions.append(InspectionTechnical.responsible_id == filters["responsible_id"])
                if filters.get("sales_user"):
                    conditions.append(InspectionTechnical.sales_user == filters["sales_user"])
                if filters.get("type"):
                    conditions.append(self._type_condition(filters["type"]))
                if filters.get("pending_technical") == 'true':
                    # Sin registro técnico asociado (LEFT JOIN sin coincidencia) o
                    # devuelto desde Comercial; las de Soporte no continúan el flujo
                    conditions.append(or_(
                        and_(
                            TechnicalTicketManagement.id_management_technical.is_(None),
                            # Asistencias antiguas: ya pasaron a Comercial sin registro
                            ~self._legacy_approved_assistance(),
                        ),
                        TechnicalTicketManagement.status == self.TECHNICAL_STATUS_RETURNED,
                    ))
                    conditions.append(self._in_flow())

                if filters.get("pending_commercial") == 'true':
                    conditions.append(
                        InspectionTechnical.status == "Listo para cotizar"
                    )
                    # Incluye las Asistencias; excluye el Soporte
                    conditions.append(self._in_flow())

                    conditions.append(
                        ~exists().where(
                            CommercialTicketManagement.ticket_id
                            == InspectionTechnical.id_inspection
                        )
                    )

                if filters.get("pending_approve_support") == 'true':
                    # Soportes / Asistencias sin aprobar (approve_support false o NULL)
                    conditions.append(
                        InspectionTechnical.approve_support.is_not(True)
                    )

                if filters.get("ready_for_project") == 'true':
                    # Comercial aprobado (status_id 5) y aún sin proyecto creado
                    conditions.append(commercial_status_id == 5)
                    conditions.append(TaskTechnical.id_task.is_(None))
                    # La Asistencia va directo a Financiera; solo las antiguas en Proyectos
                    conditions.append(or_(
                        InspectionTechnical.type.is_distinct_from(self.ASSISTANCE_TYPE),
                        InspectionTechnical.management_area == "Proyectos",
                    ))

                if conditions:
                    stmt = stmt.where(and_(*conditions))

                rows = session.execute(
                    stmt.order_by(InspectionTechnical.created_at.desc())
                ).all()

                # Documentos en una sola consulta aparte para no duplicar filas por cada archivo
                documents_by_inspection = {}
                inspection_ids = [row[0].id_inspection for row in rows]
                if inspection_ids:
                    documents = session.execute(
                        select(InspectionDocuments)
                        .where(InspectionDocuments.inspection_id.in_(inspection_ids))
                        .order_by(InspectionDocuments.id_document)
                    ).scalars().all()
                    for document in documents:
                        documents_by_inspection.setdefault(
                            document.inspection_id, []
                        ).append(document)

                return [
                    (*row, documents_by_inspection.get(row[0].id_inspection, []))
                    for row in rows
                ]

            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener las inspecciones de la base de datos",
                    internal,
                    external,
                )

    def get_dashboard_counts(self, filters, internal, external):
        """Obtiene en una sola consulta todos los conteos del dashboard."""
        with self.db_telearseg.session_factory() as session:
            try:
                date_conditions = self._dashboard_inspection_conditions(filters)

                def count_inspections(*conditions):
                    return (
                        select(func.count(InspectionTechnical.id_inspection))
                        .where(*date_conditions, *conditions)
                        .scalar_subquery()
                    )

                def count_commercial(*conditions):
                    return (
                        select(func.count(CommercialTicketManagement.id_management_commercial))
                        .join(
                            InspectionTechnical,
                            InspectionTechnical.id_inspection
                            == CommercialTicketManagement.ticket_id,
                        )
                        .where(*date_conditions, *conditions)
                        .scalar_subquery()
                    )

                def count_financial(status):
                    return (
                        select(func.count(FinancialTicketManagement.id_management_financial))
                        .join(
                            InspectionTechnical,
                            InspectionTechnical.id_inspection
                            == FinancialTicketManagement.ticket_id,
                        )
                        .where(*date_conditions, FinancialTicketManagement.status == status)
                        .scalar_subquery()
                    )

                # Mismas condiciones que /inspection?pending_technical=true,
                # /inspection?pending_commercial=true,
                # /register-commercial?is_registred=true y ?pending_financial=true
                pending_technical = count_inspections(
                    # date_conditions ya excluye el Soporte (_in_flow)
                    or_(
                        and_(
                            ~exists().where(
                                TechnicalTicketManagement.inspection_id
                                == InspectionTechnical.id_inspection
                            ),
                            # Asistencias antiguas: pasaron a Comercial sin registro
                            ~self._legacy_approved_assistance(),
                        ),
                        # Devueltas desde Comercial
                        exists().where(
                            TechnicalTicketManagement.inspection_id
                            == InspectionTechnical.id_inspection,
                            TechnicalTicketManagement.status
                            == self.TECHNICAL_STATUS_RETURNED,
                        ),
                    ),
                )
                pending_commercial = count_inspections(
                    InspectionTechnical.status == "Listo para cotizar",
                    ~exists().where(
                        CommercialTicketManagement.ticket_id
                        == InspectionTechnical.id_inspection
                    )
                )
                pending_projects = count_commercial(
                    CommercialTicketManagement.status_id == 5,
                    InspectionTechnical.management_area == "Proyectos",
                    exists().where(
                        and_(
                            TaskTechnical.inspection_id
                            == CommercialTicketManagement.ticket_id,
                            TaskTechnical.status == "Finalizado",
                        )
                    ),
                )
                pending_financial = count_commercial(
                    InspectionTechnical.management_area == "Financiera",
                    InspectionTechnical.next_area == "Financiera",
                    ~exists().where(
                        FinancialTicketManagement.ticket_id
                        == CommercialTicketManagement.ticket_id
                    ),
                )

                # Proyectos finalizados: aprobados en /approve-commercial-ticket,
                # que registra el paso Proyectos -> Financiera en el historial.
                finished_projects = (
                    select(func.count(func.distinct(HistoryAreaTicket.ticket_id)))
                    .join(
                        InspectionTechnical,
                        InspectionTechnical.id_inspection == HistoryAreaTicket.ticket_id,
                    )
                    .where(
                        *date_conditions,
                        HistoryAreaTicket.previous_area == "Proyectos",
                        HistoryAreaTicket.current_area == "Financiera",
                    )
                    .scalar_subquery()
                )

                stmt = select(
                    pending_technical.label("pending_technical"),
                    pending_commercial.label("pending_commercial"),
                    pending_projects.label("pending_projects"),
                    pending_financial.label("pending_financial"),
                    count_inspections(
                        InspectionTechnical.status == "Listo para cotizar"
                    ).label("finished_technical"),
                    count_commercial(
                        CommercialTicketManagement.status_id == 5
                    ).label("quotations_approved"),
                    count_commercial(
                        CommercialTicketManagement.status_id == 6
                    ).label("quotations_rejected"),
                    count_commercial(
                        CommercialTicketManagement.status_id == 7
                    ).label("quotations_pending"),
                    finished_projects.label("finished_projects"),
                    count_financial("Cobrada").label("invoices_collected"),
                    count_financial("Emitida").label("invoices_issued"),
                )

                return dict(session.execute(stmt).one()._mapping)
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener los datos del dashboard",
                    internal,
                    external,
                )

    def get_dashboard_area_times(self, filters, internal, external):
        """Devuelve el SLA promedio por área y el tiempo por área de cada inspección.

        El tiempo en un área es la diferencia entre el registro del historial que
        la inicia y el siguiente registro del mismo ticket (LEAD). Si no hay
        siguiente, el ticket sigue en esa área y se mide hasta el momento actual,
        salvo que la inspección esté finalizada (tiene un documento financiero
        Cobrado): en ese caso el área se cierra en la fecha del cobro.
        """
        with self.db_telearseg.session_factory() as session:
            try:
                finished = (
                    select(
                        FinancialTicketManagement.ticket_id,
                        func.max(FinancialTicketManagement.updated_at).label("finished_at"),
                    )
                    .where(FinancialTicketManagement.status == "Cobrada")
                    .group_by(FinancialTicketManagement.ticket_id)
                    .subquery()
                )
                next_entered_at = func.lead(HistoryAreaTicket.created_at).over(
                    partition_by=HistoryAreaTicket.ticket_id,
                    order_by=(HistoryAreaTicket.created_at, HistoryAreaTicket.id_history),
                )
                # greatest evita tiempos negativos si el cobro es anterior al último cambio de área
                left_at = func.coalesce(
                    next_entered_at,
                    func.greatest(finished.c.finished_at, HistoryAreaTicket.created_at),
                )
                intervals = (
                    select(
                        HistoryAreaTicket.ticket_id,
                        HistoryAreaTicket.current_area.label("area"),
                        HistoryAreaTicket.created_at.label("entered_at"),
                        left_at.label("left_at"),
                        finished.c.finished_at,
                    )
                    .join(
                        InspectionTechnical,
                        InspectionTechnical.id_inspection == HistoryAreaTicket.ticket_id,
                    )
                    .outerjoin(finished, finished.c.ticket_id == HistoryAreaTicket.ticket_id)
                    .where(*self._dashboard_inspection_conditions(filters))
                    .subquery()
                )
                seconds = func.extract(
                    "epoch",
                    func.coalesce(intervals.c.left_at, func.localtimestamp())
                    - intervals.c.entered_at,
                )

                sla_rows = session.execute(
                    select(
                        intervals.c.area,
                        func.avg(seconds).label("average_seconds"),
                        func.count().label("transitions"),
                    )
                    .where(intervals.c.left_at.is_not(None))
                    .group_by(intervals.c.area)
                ).all()

                inspection_rows = session.execute(
                    select(
                        InspectionTechnical.id_inspection,
                        InspectionTechnical.title_ticket,
                        InspectionTechnical.management_area,
                        intervals.c.area,
                        func.sum(seconds).label("seconds"),
                        func.bool_or(intervals.c.left_at.is_(None)).label("in_progress"),
                        func.max(intervals.c.finished_at).label("finished_at"),
                    )
                    .join(
                        InspectionTechnical,
                        InspectionTechnical.id_inspection == intervals.c.ticket_id,
                    )
                    .group_by(
                        InspectionTechnical.id_inspection,
                        InspectionTechnical.title_ticket,
                        InspectionTechnical.management_area,
                        intervals.c.area,
                    )
                    .order_by(
                        InspectionTechnical.id_inspection.desc(),
                        func.min(intervals.c.entered_at),
                    )
                ).all()

                return sla_rows, inspection_rows
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener los tiempos por área",
                    internal,
                    external,
                )

    def get_project_activities(self, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                total = func.count(TechnicalRecord.id_record)
                return session.execute(
                    select(
                        TaskTechnical.id_task,
                        TaskTechnical.code,
                        total.label("total_records"),
                    )
                    .outerjoin(TechnicalRecord, TechnicalRecord.task_id == TaskTechnical.id_task)
                    .group_by(TaskTechnical.id_task, TaskTechnical.code)
                    .order_by(total.desc(), TaskTechnical.id_task)
                ).all()
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener las actividades por proyecto",
                    internal,
                    external,
                )

    @classmethod
    def _dashboard_inspection_conditions(cls, filters):
        """Rango de fechas del dashboard; solo cuentan los registros del flujo
        (no Soporte)."""
        conditions = [cls._in_flow()]
        if filters.get("start_date"):
            conditions.append(InspectionTechnical.created_at >= filters["start_date"])
        if filters.get("end_date"):
            conditions.append(InspectionTechnical.created_at <= filters["end_date"])
        return conditions

    @staticmethod
    def _validate_update_body(body, identifier):
        if not isinstance(body, dict):
            raise CustomAPIException("El campo data es obligatorio", 400)
        if body.get(identifier) is None:
            raise CustomAPIException(
                f"El campo {identifier} es obligatorio para actualizar el registro",
                400,
            )

    @staticmethod
    def _get_latest_management(session, model, ticket_id, primary_key):
        return session.execute(
            select(model)
            .where(model.ticket_id == ticket_id)
            .order_by(primary_key.desc())
        ).scalars().first()

    @staticmethod
    def _apply_fields(record, body, field_map):
        for request_field, model_field in field_map.items():
            if request_field in body:
                setattr(record, model_field, body[request_field])

    @staticmethod
    def _set_updated_by(body, *records):
        if "user" in body:
            for record in records:
                record.updated_by = body["user"]

    def get_inspection_document(self, id_document, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                document = session.execute(
                    select(InspectionDocuments).where(
                        InspectionDocuments.id_document == id_document
                    )
                ).scalar_one_or_none()

                if document is None:
                    raise CustomAPIException("Documento no encontrado", 404)
                return document
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener el documento de la base de datos",
                    internal,
                    external,
                )

    def get_sale_quotation_document(self, id_quote, internal, external):
        """Retorna todo lo necesario para generar el PDF de una proforma."""
        with self.db_telearseg.session_factory() as session:
            try:
                quotation = session.execute(
                    select(SaleQuotation).where(SaleQuotation.id_quote == id_quote)
                ).scalar_one_or_none()
                if quotation is None:
                    raise CustomAPIException("Proforma no encontrada", 404)

                inspection = None
                if quotation.inspection_id is not None:
                    inspection = self._get_inspection(session, quotation.inspection_id)

                company = None
                if quotation.client_company is not None:
                    company = session.execute(
                        select(ClientCompany).where(
                            ClientCompany.id_company == quotation.client_company
                        )
                    ).scalar_one_or_none()

                # created_by guarda el usuario de sesión (public.users.user)
                seller = None
                if quotation.created_by:
                    seller = session.execute(
                        select(Users.user, Users.attributes).where(
                            Users.user == quotation.created_by
                        )
                    ).first()

                items = session.execute(
                    select(SaleQuotationItem)
                    .where(SaleQuotationItem.sale_quote_id == id_quote)
                    .order_by(SaleQuotationItem.item_number, SaleQuotationItem.id_item)
                ).scalars().all()
                components = session.execute(
                    select(SaleAdditionalMaterials)
                    .where(SaleAdditionalMaterials.sale_quote_id == id_quote)
                    .order_by(SaleAdditionalMaterials.id_extra)
                ).scalars().all()

                material_ids = {
                    record.material_id
                    for record in (*items, *components)
                    if record.material_id is not None
                }
                equipment = {}
                if material_ids:
                    equipment = {
                        record.id_equipment: record
                        for record in session.execute(
                            select(TechnicalEquipment).where(
                                TechnicalEquipment.id_equipment.in_(material_ids)
                            )
                        ).scalars().all()
                    }

                return quotation, inspection, company, seller, items, components, equipment
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener la proforma de la base de datos",
                    internal,
                    external,
                )

    @classmethod
    def _inspection_type(cls, value):
        """Valida el tipo de inspección; sin valor se asume Inspección."""
        if value in (None, ""):
            return cls.INSPECTION_TYPE
        if value not in cls.VALID_TYPES:
            raise CustomAPIException(
                f"El campo type debe ser {', '.join(cls.VALID_TYPES)}", 400
            )
        return value

    @staticmethod
    def _parse_datetime(value, field_name):
        """ISO 8601 a datetime sin zona (como guarda Postgres un timestamp sin tz)."""
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            text = str(value).strip()
            # Python 3.10 (imagen de prod) no acepta el sufijo Z de JavaScript
            if text.endswith(("Z", "z")):
                text = text[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                raise CustomAPIException(
                    f"El campo {field_name} debe ser una fecha ISO 8601", 400
                )
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    @classmethod
    def _validate_support_dates(cls, inspection):
        """Un Soporte usa fecha inicio y fin en lugar de la fecha compromiso."""
        if not cls._is_support(inspection):
            return
        if inspection.start_date is None or inspection.end_date is None:
            raise CustomAPIException(
                "Las inspecciones de soporte requieren start_date y end_date", 400
            )
        if inspection.end_date < inspection.start_date:
            raise CustomAPIException(
                "La fecha fin no puede ser anterior a la fecha inicio", 400
            )

    @classmethod
    def _type_condition(cls, types):
        """Filtra por uno o varios tipos (ej: ["Soporte", "Asistencia"]).
        Inspección incluye también las antiguas con type NULL."""
        if isinstance(types, str):
            types = [types]
        conditions = [InspectionTechnical.type.in_(types)]
        if cls.INSPECTION_TYPE in types:
            conditions.append(InspectionTechnical.type.is_(None))
        return or_(*conditions)

    @classmethod
    def _in_flow(cls):
        """Registros que siguen el flujo Técnica -> Comercial -> Proyectos -> Financiera:
        todos menos el Soporte (la Asistencia sigue el flujo normal)."""
        # IS DISTINCT FROM para no descartar las inspecciones antiguas con type NULL
        return InspectionTechnical.type.is_distinct_from(cls.SUPPORT_TYPE)

    @classmethod
    def _legacy_approved_assistance(cls):
        """Asistencias aprobadas con /approve-support antes de que la Asistencia
        tuviera registro técnico: pasaron directo a Comercial sin él."""
        # Sin NULL (IS NOT DISTINCT FROM / IS TRUE) para poder negarla con ~
        return and_(
            InspectionTechnical.type.is_not_distinct_from(cls.ASSISTANCE_TYPE),
            InspectionTechnical.approve_support.is_(True),
        )

    @classmethod
    def _not_completed_assistance(cls):
        """Excluye las Asistencias en management_status Completado (vista del técnico).
        IS DISTINCT FROM para conservar los type / management_status NULL."""
        return or_(
            InspectionTechnical.type.is_distinct_from(cls.ASSISTANCE_TYPE),
            InspectionTechnical.management_status.is_distinct_from(
                cls.MANAGEMENT_STATUS_COMPLETED
            ),
        )

    @classmethod
    def _is_support(cls, inspection):
        """Soporte o Asistencia (usan fecha inicio y fin)."""
        return inspection.type in cls.SUPPORT_TYPES

    @classmethod
    def _follows_flow(cls, inspection):
        """Versión en Python de _in_flow para una inspección ya cargada."""
        return inspection.type != cls.SUPPORT_TYPE

    @classmethod
    def _ensure_not_support(cls, inspection):
        """El Soporte no tiene registro técnico ni continúa el flujo."""
        if not cls._follows_flow(inspection):
            raise CustomAPIException(
                "Las inspecciones de soporte no continúan el flujo", 400
            )

    @classmethod
    def _ensure_follows_flow(cls, inspection):
        cls._ensure_not_support(inspection)

    @classmethod
    def _is_assistance(cls, inspection):
        return inspection.type == cls.ASSISTANCE_TYPE

    @classmethod
    def _move_on_commercial_approval(cls, session, ticket, user):
        """Al aprobarse la gestión comercial (estado 5) el registro sale de
        Comercial: la Asistencia va directo a Financiera y el resto a Proyectos."""
        target = "Financiera" if cls._is_assistance(ticket) else "Proyectos"
        ticket.management_area = target
        ticket.next_area = "Financiera"
        session.add(HistoryAreaTicket(
            ticket_id=ticket.id_inspection,
            previous_area="Comercial",
            current_area=target,
            created_by=user,
        ))

    @classmethod
    def _assistance_sent_to_financial(cls, session, ticket):
        """Asistencia aprobada con el flujo directo Comercial -> Financiera (ya
        descontó stock). Las antiguas pasaron por Proyectos y siguen ese flujo."""
        if not cls._is_assistance(ticket):
            return False
        return session.execute(
            select(exists().where(
                HistoryAreaTicket.ticket_id == ticket.id_inspection,
                HistoryAreaTicket.previous_area == "Comercial",
                HistoryAreaTicket.current_area == "Financiera",
            ))
        ).scalar()

    def _discount_assistance_materials(self, session, quote_id, user):
        """Registra la entrega automática de la Asistencia aprobada y descuenta
        el stock con las cantidades de la proforma. Entran los ítems de material
        y los componentes de materiales varios (no la mano de obra ni la línea
        agrupadora). Los productos nuevos se registran con su pendiente y no
        descuentan: al crearlos, resolve_pending_material resta lo entregado.
        Debe llamarse después de _generate_pending_materials."""
        items = session.execute(
            select(SaleQuotationItem).where(
                SaleQuotationItem.sale_quote_id == quote_id,
                SaleQuotationItem.is_labor.isnot(True),
                SaleQuotationItem.is_bundle.isnot(True),
            ).order_by(SaleQuotationItem.id_item)
        ).scalars().all()
        components = session.execute(
            select(SaleAdditionalMaterials)
            .where(SaleAdditionalMaterials.sale_quote_id == quote_id)
            .order_by(SaleAdditionalMaterials.id_extra)
        ).scalars().all()
        pendings = {
            self.line_key(pending.quotation_item_id, pending.additional_material_id): pending
            for pending in session.execute(
                select(PendingMaterial).where(PendingMaterial.quote_id == quote_id)
            ).scalars().all()
        }

        lines = []
        sources = (
            [(item, item.id_item, None) for item in items]
            + [(component, None, component.id_extra) for component in components]
        )
        for line, item_id, additional_id in sources:
            quantity = int(Decimal(str(line.quantity or 0)))
            if quantity <= 0:
                continue
            pending = None
            material_id = line.material_id
            if material_id is None:
                pending = pendings.get(self.line_key(item_id, additional_id))
                if pending is None:
                    # Ni producto del catálogo ni producto nuevo: no hay qué descontar
                    continue
                # Puede estar ya creado en el catálogo (desde el registro técnico)
                material_id = pending.material_id
            lines.append({
                "quotation_item_id": item_id,
                "additional_material_id": additional_id,
                "material_id": material_id,
                "pending": pending,
                "quantity": quantity,
            })
        if not lines:
            return None

        equipment_ids = {line["material_id"] for line in lines if line["material_id"]}
        equipment = {}
        if equipment_ids:
            equipment = {
                record.id_equipment: record
                for record in session.execute(
                    select(TechnicalEquipment)
                    .where(TechnicalEquipment.id_equipment.in_(equipment_ids))
                    .order_by(TechnicalEquipment.id_equipment)
                    .with_for_update()
                ).scalars().all()
            }

        # Un mismo producto puede repetirse en varias líneas: se valida la suma
        required = {}
        for line in lines:
            if line["material_id"]:
                required[line["material_id"]] = (
                    required.get(line["material_id"], 0) + line["quantity"]
                )
        for material_id, quantity in required.items():
            record = equipment.get(material_id)
            if record is None:
                raise CustomAPIException(
                    f"El material {material_id} no existe en el catálogo", 404
                )
            stock = int(record.stock or 0)
            if quantity > stock:
                raise CustomAPIException(
                    f'Stock insuficiente de "{record.product}": disponible {stock}, '
                    f"requerido {quantity}",
                    400,
                )

        history = MaterialDeliveryHistory(
            task_id=None,
            quote_id=quote_id,
            delivered_to=None,
            observation=MaterialDeliveryHistory.ASSISTANCE_OBSERVATION,
            status=MaterialDeliveryHistory.STATUS_REGISTERED,
            created_by=user,
        )
        session.add(history)
        session.flush()

        for material_id, quantity in required.items():
            record = equipment[material_id]
            record.stock = int(record.stock or 0) - quantity
            record.updated_by = user

        for line in lines:
            session.add(MaterialDeliveryDetail(
                history_id=history.id_history,
                quotation_item_id=line["quotation_item_id"],
                additional_material_id=line["additional_material_id"],
                material_id=line["material_id"],
                pending_material_id=(
                    line["pending"].id_pending_material if line["pending"] else None
                ),
                quantity_delivered=line["quantity"],
                quantity_remaining=0,
            ))
        session.flush()
        return history

    @staticmethod
    def _inspection_started_flow(session, inspection):
        if inspection.management_area not in (None, "Técnica"):
            return True
        return session.execute(
            select(
                exists().where(
                    TechnicalTicketManagement.inspection_id == inspection.id_inspection
                )
                | exists().where(
                    CommercialTicketManagement.ticket_id == inspection.id_inspection
                )
            )
        ).scalar()

    @staticmethod
    def _get_inspection(session, inspection_id):
        inspection = session.execute(
            select(InspectionTechnical).where(
                InspectionTechnical.id_inspection == inspection_id
            )
        ).scalar_one_or_none()

        if inspection is None:
            raise CustomAPIException("Inspección no encontrada", 404)
        return inspection

    # ------------------------------------------------------------------
    # Entrega de materiales (bodega)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_integer_quantity(value):
        if value is None or isinstance(value, bool):
            return False
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return False
        return amount.is_finite() and amount == amount.to_integral_value()

    @classmethod
    def _validate_quotation_quantities(cls, quotation):
        """Las cantidades de materiales deben ser enteras porque el stock del
        catálogo es entero. La mano de obra no se entrega en bodega y no se valida."""
        for item in quotation.get('items') or []:
            if item.get('is_bundle'):
                for component in item.get('components') or []:
                    if not component.get('material_id') and not (
                        component.get('is_new') and cls._optional_text(component.get('description'))
                    ):
                        raise CustomAPIException(
                            f"Los materiales varios del ítem {item.get('item')} deben ser del catálogo o un producto nuevo con descripción",
                            400,
                        )
                    if not cls._is_integer_quantity(component.get('quantity')):
                        raise CustomAPIException(
                            f"Las cantidades de los materiales varios del ítem {item.get('item')} deben ser números enteros",
                            400,
                        )
            elif not item.get('is_labor') and not cls._is_integer_quantity(item.get('quantity')):
                raise CustomAPIException(
                    f"La cantidad del ítem {item.get('item')} debe ser un número entero",
                    400,
                )

    @staticmethod
    def _format_quantity(value):
        amount = Decimal(str(value or 0))
        if amount == amount.to_integral_value():
            return str(int(amount))
        return str(amount.normalize())

    @staticmethod
    def line_key(quotation_item_id, additional_material_id):
        """Identifica una línea de la proforma: un ítem o un componente de materiales varios."""
        if quotation_item_id is not None:
            return ("item", quotation_item_id)
        return ("additional", additional_material_id)

    def _invoice_from_quotation(self, session, inspection_id, body):
        """
        El valor facturado es siempre el total de la proforma aprobada de la
        inspección (una por inspección); no se acepta el que envía el cliente.
        Retorna (invoice_price, amount_pending).
        """
        commercial = self._get_latest_management(
            session,
            CommercialTicketManagement,
            inspection_id,
            CommercialTicketManagement.id_management_commercial,
        )
        if commercial is None or commercial.status_id != self.COMMERCIAL_STATUS_APPROVED:
            raise CustomAPIException(
                "La gestión comercial de la inspección no está aprobada", 400
            )

        quotation = self._get_latest_quotation(session, inspection_id)
        if quotation is None or quotation.total is None:
            raise CustomAPIException(
                "La inspección no tiene una proforma registrada", 400
            )

        invoice_price = Decimal(str(quotation.total))
        amount_paid = body.get("amount_paid")
        if amount_paid in (None, ""):
            return invoice_price, None

        amount_paid = Decimal(str(amount_paid))
        if amount_paid < 0 or amount_paid > invoice_price:
            raise CustomAPIException(
                "El valor abonado debe estar entre 0 y el valor facturado", 400
            )
        return invoice_price, invoice_price - amount_paid

    @staticmethod
    def _get_latest_quotation(session, inspection_id, lock=False):
        stmt = (
            select(SaleQuotation)
            .where(SaleQuotation.inspection_id == inspection_id)
            .order_by(SaleQuotation.id_quote.desc())
        )
        if lock:
            stmt = stmt.with_for_update()
        return session.execute(stmt).scalars().first()

    def _save_technical_materials(self, session, management, materials, user):
        """Guarda los materiales del registro técnico. Los que llegan con
        id_material se actualizan en lugar de recrearse, para no perder el
        vínculo con su pendiente."""
        current = {
            material.id_material: material
            for material in session.execute(
                select(MaterialTechTicket).where(
                    MaterialTechTicket.tech_ticket == management.id_management_technical
                )
            ).scalars().all()
        }

        saved = []
        for data in materials:
            record = current.pop(data.get("id_material"), None)
            if record is None:
                record = MaterialTechTicket(tech_ticket=management.id_management_technical)
                session.add(record)
            record.material_id = data.get("material_id")
            record.material_description = data.get("material_description")
            record.other = data.get("other")
            record.quantity = data.get("quantity")
            saved.append(record)

        # Los que no llegaron en la lista fueron quitados por el técnico
        removed = list(current.values())
        if removed:
            self._release_technical_pendings(
                session, [material.id_material for material in removed]
            )
            for material in removed:
                session.delete(material)

        session.flush()
        self._sync_technical_pendings(session, management.inspection_id, saved, user)

    @staticmethod
    def _release_technical_pendings(session, material_ids):
        """Desvincula los pendientes de los materiales que el técnico quitó. Si
        aún no llegaron a la proforma ni al catálogo se eliminan."""
        session.execute(
            update(SaleQuotationItem)
            .where(SaleQuotationItem.material_tech_ticket_id.in_(material_ids))
            .values(material_tech_ticket_id=None)
        )
        session.execute(
            update(SaleAdditionalMaterials)
            .where(SaleAdditionalMaterials.material_tech_ticket_id.in_(material_ids))
            .values(material_tech_ticket_id=None)
        )
        pendings = session.execute(
            select(PendingMaterial).where(
                PendingMaterial.material_tech_ticket_id.in_(material_ids)
            )
        ).scalars().all()
        for pending in pendings:
            if (
                pending.quote_id is None
                and pending.status != PendingMaterial.STATUS_CREATED
            ):
                session.delete(pending)
            else:
                pending.material_tech_ticket_id = None
        session.flush()

    @staticmethod
    def _sync_technical_pendings(session, inspection_id, materials, user):
        """Un pendiente por cada producto nuevo (sin material_id) del registro
        técnico. Mientras no llegue a la proforma aprobada ni al catálogo, sigue
        los cambios del técnico."""
        if not materials:
            return

        pendings = {
            pending.material_tech_ticket_id: pending
            for pending in session.execute(
                select(PendingMaterial).where(
                    PendingMaterial.material_tech_ticket_id.in_(
                        [material.id_material for material in materials]
                    )
                )
            ).scalars().all()
        }
        for material in materials:
            pending = pendings.get(material.id_material)
            editable = (
                pending is not None
                and pending.quote_id is None
                and pending.status != PendingMaterial.STATUS_CREATED
            )
            if material.material_id is not None:
                # El técnico cambió el producto nuevo por uno del catálogo
                if editable:
                    session.delete(pending)
                continue

            if pending is None:
                session.add(PendingMaterial(
                    inspection_id=inspection_id,
                    material_tech_ticket_id=material.id_material,
                    name_material=material.other or material.material_description,
                    description=material.material_description,
                    quantity=material.quantity,
                    status=PendingMaterial.STATUS_PENDING,
                    created_by=user,
                ))
            elif editable:
                pending.name_material = material.other or material.material_description
                pending.description = material.material_description
                pending.quantity = material.quantity
        session.flush()

    @staticmethod
    def _generate_pending_materials(session, quote_id, user):
        """Registra como pendientes los productos nuevos de la proforma aprobada:
        ítems y componentes de materiales varios. Si la línea proviene de un
        material del técnico, vincula su pendiente en lugar de crear otro. Es
        idempotente: las líneas que ya tienen pendiente no se duplican."""
        line_key = InternalManagementRepository.line_key
        inspection_id = session.execute(
            select(SaleQuotation.inspection_id).where(SaleQuotation.id_quote == quote_id)
        ).scalar_one()
        existing = {
            line_key(item_id, additional_id)
            for item_id, additional_id in session.execute(
                select(
                    PendingMaterial.quotation_item_id,
                    PendingMaterial.additional_material_id,
                ).where(PendingMaterial.quote_id == quote_id)
            ).all()
        }

        new_items = session.execute(
            select(SaleQuotationItem).where(
                SaleQuotationItem.sale_quote_id == quote_id,
                SaleQuotationItem.is_new.is_(True),
                SaleQuotationItem.is_labor.isnot(True),
                SaleQuotationItem.material_id.is_(None),
            )
        ).scalars().all()
        new_components = session.execute(
            select(SaleAdditionalMaterials).where(
                SaleAdditionalMaterials.sale_quote_id == quote_id,
                SaleAdditionalMaterials.is_new.is_(True),
                SaleAdditionalMaterials.material_id.is_(None),
            )
        ).scalars().all()

        # (línea, ítem, componente): el pendiente referencia uno de los dos
        lines = [
            (line, item_id, additional_id)
            for line, item_id, additional_id in (
                [(item, item.id_item, None) for item in new_items]
                + [(component, None, component.id_extra) for component in new_components]
            )
            if line_key(item_id, additional_id) not in existing
        ]

        technical_ids = {
            line.material_tech_ticket_id
            for line, _, _ in lines
            if line.material_tech_ticket_id is not None
        }
        technical = {}
        if technical_ids:
            technical = {
                pending.material_tech_ticket_id: pending
                for pending in session.execute(
                    select(PendingMaterial).where(
                        PendingMaterial.material_tech_ticket_id.in_(technical_ids),
                        PendingMaterial.quote_id.is_(None),
                    )
                ).scalars().all()
            }

        created = []
        for line, item_id, additional_id in lines:
            pending = technical.pop(line.material_tech_ticket_id, None)
            if pending is None:
                pending = PendingMaterial(
                    inspection_id=inspection_id,
                    name_material=line.description,
                    model=line.model,
                    status=PendingMaterial.STATUS_PENDING,
                    created_by=user,
                )
                session.add(pending)
            elif pending.status == PendingMaterial.STATUS_REMOVED:
                pending.status = PendingMaterial.STATUS_PENDING

            # El pendiente queda en la línea aprobada, con su cantidad y precios
            pending.quote_id = quote_id
            pending.quotation_item_id = item_id
            pending.additional_material_id = additional_id
            pending.model = line.model or pending.model
            pending.quantity = line.quantity
            pending.base_price = line.base_price
            pending.profit_margin = line.profit_margin
            pending.profit_margin_dollar = line.profit_margin_dollar
            created.append(pending)

        if created:
            session.flush()
        return created

    def _get_project_quotation(self, session, task_id, lock=False):
        task = session.get(TaskTechnical, task_id)
        if task is None:
            raise CustomAPIException("Proyecto no encontrado", 404)

        quotation = self._get_latest_quotation(session, task.inspection_id, lock=lock)
        if quotation is None:
            raise CustomAPIException("El proyecto no tiene una proforma registrada", 404)
        return task, quotation

    @classmethod
    def _delivered_by_line(cls, session, quote_id):
        """Cantidad entregada por línea de la proforma, sin contar entregas anuladas."""
        rows = session.execute(
            select(
                MaterialDeliveryDetail.quotation_item_id,
                MaterialDeliveryDetail.additional_material_id,
                func.sum(MaterialDeliveryDetail.quantity_delivered),
            )
            .join(
                MaterialDeliveryHistory,
                MaterialDeliveryHistory.id_history == MaterialDeliveryDetail.history_id,
            )
            .where(
                MaterialDeliveryHistory.quote_id == quote_id,
                MaterialDeliveryHistory.status == MaterialDeliveryHistory.STATUS_REGISTERED,
            )
            .group_by(
                MaterialDeliveryDetail.quotation_item_id,
                MaterialDeliveryDetail.additional_material_id,
            )
        ).all()
        return {
            cls.line_key(item_id, additional_id): int(total or 0)
            for item_id, additional_id, total in rows
        }

    def get_project_materials(self, task_id, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                task, quotation = self._get_project_quotation(session, task_id)

                # Respaldo para proformas aprobadas antes de existir los pendientes
                if self._generate_pending_materials(session, quotation.id_quote, None):
                    session.commit()

                items = session.execute(
                    select(SaleQuotationItem)
                    .where(SaleQuotationItem.sale_quote_id == quotation.id_quote)
                    .order_by(SaleQuotationItem.item_number, SaleQuotationItem.id_item)
                ).scalars().all()
                components = session.execute(
                    select(SaleAdditionalMaterials)
                    .where(SaleAdditionalMaterials.sale_quote_id == quotation.id_quote)
                    .order_by(SaleAdditionalMaterials.id_extra)
                ).scalars().all()
                pendings = {
                    self.line_key(pending.quotation_item_id, pending.additional_material_id): pending
                    for pending in session.execute(
                        select(PendingMaterial).where(
                            PendingMaterial.quote_id == quotation.id_quote
                        )
                    ).scalars().all()
                }

                material_ids = (
                    {item.material_id for item in items if item.material_id}
                    | {component.material_id for component in components if component.material_id}
                    | {pending.material_id for pending in pendings.values() if pending.material_id}
                )
                equipment = {}
                if material_ids:
                    equipment = {
                        record.id_equipment: record
                        for record in session.execute(
                            select(TechnicalEquipment).where(
                                TechnicalEquipment.id_equipment.in_(material_ids)
                            )
                        ).scalars().all()
                    }

                histories = session.execute(
                    select(MaterialDeliveryHistory)
                    .where(MaterialDeliveryHistory.quote_id == quotation.id_quote)
                    .order_by(
                        MaterialDeliveryHistory.created_at.desc(),
                        MaterialDeliveryHistory.id_history.desc(),
                    )
                ).scalars().all()
                details = []
                if histories:
                    details = session.execute(
                        select(MaterialDeliveryDetail)
                        .where(
                            MaterialDeliveryDetail.history_id.in_(
                                [history.id_history for history in histories]
                            )
                        )
                        .order_by(MaterialDeliveryDetail.id_delivery_material)
                    ).scalars().all()

                technicians = list(dict.fromkeys(
                    user
                    for user in session.execute(
                        select(TaskTechnicalAssignment.user)
                        .where(TaskTechnicalAssignment.task_id == task.id_task)
                        .order_by(TaskTechnicalAssignment.id_assignment)
                    ).scalars().all()
                    if user
                ))

                usernames = (
                    set(technicians)
                    | {history.delivered_to for history in histories}
                    | {history.created_by for history in histories if history.created_by}
                )
                fullnames = {}
                if usernames:
                    fullnames = {
                        user: (attributes or {}).get("fullname")
                        for user, attributes in session.execute(
                            select(Users.user, Users.attributes).where(
                                Users.user.in_(usernames)
                            )
                        ).all()
                    }

                return {
                    "task": task,
                    "quotation": quotation,
                    "items": items,
                    "components": components,
                    "pendings": pendings,
                    "equipment": equipment,
                    "delivered": self._delivered_by_line(session, quotation.id_quote),
                    "histories": histories,
                    "details": details,
                    "technicians": technicians,
                    "fullnames": fullnames,
                }
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener los materiales del proyecto",
                    internal,
                    external,
                )

    def post_material_delivery(self, data, internal, external):
        """Registra la entrega y descuenta el stock del catálogo en una sola
        transacción. Los productos nuevos aún pendientes de crear se registran
        con su pendiente y no descuentan stock."""
        with self.db_telearseg.session_factory() as session:
            try:
                user = data.get("user")
                # Bloquear la proforma serializa las entregas del proyecto
                task, quotation = self._get_project_quotation(
                    session, data["task_id"], lock=True
                )
                self._generate_pending_materials(session, quotation.id_quote, user)

                items = {
                    item.id_item: item
                    for item in session.execute(
                        select(SaleQuotationItem).where(
                            SaleQuotationItem.sale_quote_id == quotation.id_quote
                        )
                    ).scalars().all()
                }
                components = {
                    component.id_extra: component
                    for component in session.execute(
                        select(SaleAdditionalMaterials).where(
                            SaleAdditionalMaterials.sale_quote_id == quotation.id_quote
                        )
                    ).scalars().all()
                }
                pendings = {
                    self.line_key(pending.quotation_item_id, pending.additional_material_id): pending
                    for pending in session.execute(
                        select(PendingMaterial).where(
                            PendingMaterial.quote_id == quotation.id_quote
                        )
                    ).scalars().all()
                }
                delivered = self._delivered_by_line(session, quotation.id_quote)

                lines = []
                for entry in data["items"]:
                    pending = None
                    if entry.get("quotation_item_id") is not None:
                        item = items.get(entry["quotation_item_id"])
                        if item is None or item.is_labor or item.is_bundle:
                            raise CustomAPIException(
                                f"El ítem {entry['quotation_item_id']} no es un material de la proforma del proyecto",
                                400,
                            )
                        approved = item.quantity
                        material_id = item.material_id
                        name = item.description
                        if material_id is None:
                            pending = pendings.get(self.line_key(item.id_item, None))
                            if pending is None:
                                raise CustomAPIException(
                                    f'El producto nuevo "{item.description}" no tiene un pendiente registrado',
                                    400,
                                )
                            # Sigue en None mientras el producto no se cree en el catálogo
                            material_id = pending.material_id
                    else:
                        component = components.get(entry["additional_material_id"])
                        if component is None:
                            raise CustomAPIException(
                                f"El material {entry['additional_material_id']} no pertenece a la proforma del proyecto",
                                400,
                            )
                        approved = component.quantity
                        material_id = component.material_id
                        name = component.description
                        if material_id is None:
                            pending = pendings.get(self.line_key(None, component.id_extra))
                            if pending is None:
                                raise CustomAPIException(
                                    f'El producto nuevo "{component.description}" no tiene un pendiente registrado',
                                    400,
                                )
                            # Sigue en None mientras el producto no se cree en el catálogo
                            material_id = pending.material_id

                    lines.append({
                        "key": self.line_key(
                            entry.get("quotation_item_id"),
                            entry.get("additional_material_id"),
                        ),
                        "quotation_item_id": entry.get("quotation_item_id"),
                        "additional_material_id": entry.get("additional_material_id"),
                        "approved": Decimal(str(approved or 0)),
                        "material_id": material_id,
                        "pending": pending,
                        "name": name,
                        "quantity": entry["quantity"],
                    })

                equipment_ids = {line["material_id"] for line in lines if line["material_id"]}
                equipment = {}
                if equipment_ids:
                    equipment = {
                        record.id_equipment: record
                        for record in session.execute(
                            select(TechnicalEquipment)
                            .where(TechnicalEquipment.id_equipment.in_(equipment_ids))
                            .with_for_update()
                        ).scalars().all()
                    }

                history = MaterialDeliveryHistory(
                    task_id=task.id_task,
                    quote_id=quotation.id_quote,
                    delivered_to=data["delivered_to"],
                    observation=data.get("observation"),
                    status=MaterialDeliveryHistory.STATUS_REGISTERED,
                    created_by=user,
                )
                session.add(history)
                session.flush()

                for line in lines:
                    record = equipment.get(line["material_id"]) if line["material_id"] else None
                    if line["material_id"] and record is None:
                        raise CustomAPIException(
                            f"El material {line['material_id']} no existe en el catálogo",
                            404,
                        )
                    name = (
                        (record.product if record else None)
                        or line["name"]
                        or (line["pending"].name_material if line["pending"] else None)
                        or "Material"
                    )

                    remaining = line["approved"] - delivered.get(line["key"], 0)
                    if line["quantity"] > remaining:
                        raise CustomAPIException(
                            f'"{name}" supera lo pendiente de entregar ({self._format_quantity(max(remaining, 0))})',
                            400,
                        )

                    if record is not None:
                        stock = record.stock or 0
                        if line["quantity"] > stock:
                            raise CustomAPIException(
                                f'Stock insuficiente de "{name}": disponible {stock}, solicitado {line["quantity"]}',
                                400,
                            )
                        record.stock = stock - line["quantity"]
                        record.updated_by = user

                    session.add(MaterialDeliveryDetail(
                        history_id=history.id_history,
                        quotation_item_id=line["quotation_item_id"],
                        additional_material_id=line["additional_material_id"],
                        material_id=line["material_id"],
                        pending_material_id=(
                            line["pending"].id_pending_material if line["pending"] else None
                        ),
                        quantity_delivered=line["quantity"],
                        quantity_remaining=remaining - line["quantity"],
                    ))
                    delivered[line["key"]] = delivered.get(line["key"], 0) + line["quantity"]

                session.commit()
                return history.id_history
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al registrar la entrega de materiales",
                    internal,
                    external,
                )
            finally:
                session.close()

    def get_pending_materials(self, filters, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                stmt = (
                    select(PendingMaterial, SaleQuotation.quote_number, InspectionTechnical)
                    .join(
                        InspectionTechnical,
                        InspectionTechnical.id_inspection == PendingMaterial.inspection_id,
                    )
                    # Los pendientes del técnico pueden no tener proforma todavía
                    .outerjoin(SaleQuotation, SaleQuotation.id_quote == PendingMaterial.quote_id)
                    .order_by(
                        PendingMaterial.created_at.desc(),
                        PendingMaterial.id_pending_material.desc(),
                    )
                )
                if filters.get("quote_id") is not None:
                    stmt = stmt.where(PendingMaterial.quote_id == filters["quote_id"])
                if filters.get("inspection_id") is not None:
                    stmt = stmt.where(PendingMaterial.inspection_id == filters["inspection_id"])
                if filters.get("status"):
                    stmt = stmt.where(PendingMaterial.status == filters["status"])
                return session.execute(stmt).all()
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener los materiales pendientes",
                    internal,
                    external,
                )

    def resolve_pending_material(self, id_pending_material, data, internal, external):
        """Resuelve un pendiente con un producto del catálogo: lo crea o, con
        data["material_id"], usa uno existente y le suma el stock recibido (así
        varios pendientes del mismo producto no lo duplican). Al stock se le
        descuenta lo ya entregado con el pendiente, y esas entregas quedan
        enlazadas al producto. Si viene del técnico, su material y los ítems de
        la proforma aún sin aprobar pasan a usar el producto."""
        with self.db_telearseg.session_factory() as session:
            try:
                user = data.get("user")
                pending = session.execute(
                    select(PendingMaterial)
                    .where(PendingMaterial.id_pending_material == id_pending_material)
                    .with_for_update()
                ).scalar_one_or_none()
                if pending is None:
                    raise CustomAPIException("Material pendiente no encontrado", 404)
                if pending.status == PendingMaterial.STATUS_REMOVED:
                    raise CustomAPIException(
                        "El material pendiente fue eliminado de la proforma", 400
                    )
                if pending.status != PendingMaterial.STATUS_PENDING:
                    raise CustomAPIException(
                        "El material pendiente ya fue creado en el catálogo", 400
                    )

                stock = data["stock"]
                existing = None
                if data.get("material_id") is not None:
                    existing = session.execute(
                        select(TechnicalEquipment)
                        .where(TechnicalEquipment.id_equipment == data["material_id"])
                        .with_for_update()
                    ).scalar_one_or_none()
                    if existing is None:
                        raise CustomAPIException("Producto del catálogo no encontrado", 404)

                # Sin proforma aprobada no hay cantidad comprometida que cubrir.
                # Con un producto existente también cuenta su stock actual
                available = stock + (int(existing.stock or 0) if existing is not None else 0)
                if pending.quote_id is not None \
                        and available < Decimal(str(pending.quantity or 0)):
                    quantity = self._format_quantity(pending.quantity)
                    raise CustomAPIException(
                        f"El stock actual más lo recibido debe cubrir la cantidad de la proforma ({quantity})"
                        if existing is not None
                        else f"El stock debe ser al menos la cantidad de la proforma ({quantity})",
                        400,
                    )

                delivered = session.execute(
                    select(func.coalesce(func.sum(MaterialDeliveryDetail.quantity_delivered), 0))
                    .join(
                        MaterialDeliveryHistory,
                        MaterialDeliveryHistory.id_history == MaterialDeliveryDetail.history_id,
                    )
                    .where(
                        MaterialDeliveryDetail.pending_material_id == pending.id_pending_material,
                        MaterialDeliveryHistory.status == MaterialDeliveryHistory.STATUS_REGISTERED,
                    )
                ).scalar_one()

                if existing is not None:
                    # Solo cambia el stock; los datos del producto no se tocan
                    equipment = existing
                    equipment.stock = available - int(delivered or 0)
                    equipment.updated_by = user
                else:
                    equipment = TechnicalEquipment(
                        code=data.get("code"),
                        product=data["product"],
                        unit=data.get("unit"),
                        model=data.get("model"),
                        provider_id=data.get("provider_id"),
                        base_price=data.get("base_price"),
                        profit_margin=data.get("profit_margin"),
                        profit_margin_dollar=data.get("profit_margin_dollar"),
                        price=data.get("price"),
                        description=data.get("description"),
                        stock=stock - int(delivered or 0),
                        created_by=user,
                        updated_by=user,
                    )
                    session.add(equipment)
                session.flush()

                session.execute(
                    update(MaterialDeliveryDetail)
                    .where(
                        MaterialDeliveryDetail.pending_material_id == pending.id_pending_material,
                        MaterialDeliveryDetail.material_id.is_(None),
                    )
                    .values(material_id=equipment.id_equipment)
                )

                if pending.material_tech_ticket_id is not None:
                    session.execute(
                        update(MaterialTechTicket)
                        .where(MaterialTechTicket.id_material == pending.material_tech_ticket_id)
                        .values(material_id=equipment.id_equipment)
                    )
                    if pending.quote_id is None:
                        # La proforma en borrador deja de tratarlo como producto nuevo,
                        # sea un ítem o un componente de materiales varios
                        for model in (SaleQuotationItem, SaleAdditionalMaterials):
                            session.execute(
                                update(model)
                                .where(
                                    model.material_tech_ticket_id
                                    == pending.material_tech_ticket_id,
                                    model.material_id.is_(None),
                                )
                                .values(material_id=equipment.id_equipment, is_new=False)
                            )

                pending.status = PendingMaterial.STATUS_CREATED
                pending.material_id = equipment.id_equipment
                pending.resolved_at = datetime.now()
                pending.resolved_by = user

                session.commit()
                return equipment.id_equipment
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al crear el material pendiente en el catálogo",
                    internal,
                    external,
                )
            finally:
                session.close()
