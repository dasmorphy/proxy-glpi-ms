from datetime import datetime

from loguru import logger
from sqlalchemy import and_, delete, exists, func, select

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.models.db.client_projects import Client
from swagger_server.models.db.commercial_followup import CommercialFollowup
from swagger_server.models.db.commercial_origin import CommercialOrigin
from swagger_server.models.db.commercial_ticket_management import CommercialTicketManagement
from swagger_server.models.db.commercial_ticket_status import CommercialTicketStatus
from swagger_server.models.db.commercial_type_solution import CommercialTypeSolution
from swagger_server.models.db.financial_ticket_management import FinancialTicketManagement
from swagger_server.models.db.history_area_ticket import HistoryAreaTicket
from swagger_server.models.db.location import ClientLocation
from swagger_server.models.db.material_tech_ticket import MaterialTechTicket
from swagger_server.models.db.providers_products import ProvidersProducts
from swagger_server.models.db.task_technical import TaskTechnical
from swagger_server.models.db.technical_equipment import TechnicalEquipment
from swagger_server.models.db.technical_record import TechnicalRecord
from swagger_server.models.db.technical_ticket_management import TechnicalTicketManagement
from swagger_server.models.db.inspection_technical import InspectionTechnical
from swagger_server.resources.databases.postgresql import PostgreSQLClient


class InternalManagementRepository:
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


    def post_inspection_technical(self, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                current_area = "Comercial" if body.get("status") == "Listo para cotizar" else "Técnica"
                next_area = "Proyectos" if current_area == "Comercial" else "Comercial"

                new_inspection = InspectionTechnical(
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
                session.commit()

            except Exception as exception:
                session.rollback()
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
                self._set_updated_by(body, inspection)

                if (
                    body.get("status") == "Listo para cotizar"
                    and inspection.management_area == "Técnica"
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

    def post_ticket_technical(self, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                inspection = session.execute(
                    select(InspectionTechnical).where(
                        InspectionTechnical.id_inspection == body.get('inspection_id')
                    )
                ).scalar_one_or_none()

                if inspection is None:
                    raise CustomAPIException("Inspección no encontrado", 404)

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

                for material in body.get('materials', []):
                    new_material = MaterialTechTicket(
                        tech_ticket=new_register.id_management_technical,
                        material_id=material.get('material_id'),
                        material_description=material.get('material_description'),
                        other=material.get('other'),
                        quantity=material.get('quantity'),
                    )
                    session.add(new_material)

                session.commit()

            except Exception as exception:
                session.rollback()
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

                if filters.get("pending_commercial") == 'true':
                    conditions.append(
                        InspectionTechnical.status == "Listo para cotizar"
                    )

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


    def post_ticket_commercial(self, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                ticket = session.execute(
                    select(InspectionTechnical).where(
                        InspectionTechnical.id_inspection == body.get('inspection_id')
                    )
                ).scalar_one_or_none()

                if ticket is None:
                    raise CustomAPIException("Inspección no encontrada", 404)


                if body.get('status_id') == 5: 
                    ticket.management_area = 'Proyectos'
                    ticket.next_area = 'Financiera'

                    new_history_area = HistoryAreaTicket(
                        ticket_id=ticket.id_inspection,
                        previous_area="Comercial",
                        current_area="Proyectos",
                        created_by=body.get('user')
                    )
                    session.add(new_history_area)

                else:
                    ticket.management_area = 'Comercial'
                    ticket.next_area = 'Proyectos'

                new_register = CommercialTicketManagement(
                    ticket_id=ticket.id_inspection,
                    assigned_user=body.get('assigned_user'),
                    origin_id=body.get('origin_id'),
                    type_solution_id=body.get('type_solution_id'),
                    quoted_amount=body.get('quoted_amount'),
                    probability_closing=body.get('probability_closing'),
                    closing_date=body.get('closing_date'),
                    next_action=body.get('next_action'),
                    responsible_next_action=body.get('responsible_next_action'),
                    requires_technical=body.get('requires_technical'),
                    requires_material=body.get('requires_material'),
                    scheduled_start_date=body.get('scheduled_start_date'),
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
                session.commit()

            except Exception as exception:
                session.rollback()
                logger.error('Error: {}', str(exception), internal=internal, external=external)
                if isinstance(exception, CustomAPIException):
                    raise exception
                
                raise CustomAPIException("Error al insertar en la base de datos", 500)

            finally:
                session.close()

    def get_ticket_commercial(self, filters, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
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


                for filter_name in (
                    "assigned_user",
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

                return session.execute(
                    stmt.order_by(CommercialTicketManagement.created_at.desc())
                ).all()
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
            conditions.append(InspectionTechnical.client_id == filters["client_id"])
        if filters.get("ubication_id") is not None:
            conditions.append(
                InspectionTechnical.ubication_id == filters["ubication_id"]
            )
        if filters.get("priority"):
            conditions.append(InspectionTechnical.priority == filters["priority"])
        return conditions

    def _get_client_and_location_names(self, client_ids, location_ids, internal, external):
        """Obtiene catálogos de Zentinel en dos consultas masivas."""
        unique_client_ids = sorted(set(client_ids))
        unique_location_ids = sorted(set(location_ids))
        if not unique_client_ids and not unique_location_ids:
            return {}, {}

        with self.db_zentinel.session_factory() as session:
            try:
                client_names = {}
                location_names = {}

                if unique_client_ids:
                    client_names = dict(
                        session.execute(
                            select(
                                Client.id_client,
                                Client.name,
                            ).where(
                                Client.id_client.in_(unique_client_ids)
                            )
                        ).all()
                    )

                if unique_location_ids:
                    location_names = dict(
                        session.execute(
                            select(
                                ClientLocation.id_location,
                                ClientLocation.name,
                            ).where(
                                ClientLocation.id_location.in_(unique_location_ids)
                            )
                        ).all()
                    )

                return client_names, location_names
            except Exception as exception:
                self._raise_database_error(
                    exception,
                    "Error al obtener clientes y ubicaciones desde Zentinel",
                    internal,
                    external,
                )

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

    def post_ticket_financial(self, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                ticket = session.execute(
                    select(InspectionTechnical).where(
                        InspectionTechnical.id_inspection == body.get("inspection_id")
                    )
                ).scalar_one_or_none()
                if ticket is None:
                    raise CustomAPIException("Inspección no encontrada", 404)

                ticket.management_area = "Financiera"

                if body.get("status") == "Cobrada":
                    ticket.status = "Finalizado"

                financial_management = FinancialTicketManagement(
                    ticket_id=ticket.id_inspection,
                    type_management=body.get("type_management"),
                    amount_pending=body.get("amount_pending"),
                    amount_paid=body.get("amount_paid"),
                    invoice_price=body.get("invoice_price"),
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

    def get_ticket_financial(self, filters, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                stmt = (
                    select(FinancialTicketManagement, InspectionTechnical)
                    .join(
                        InspectionTechnical,
                        InspectionTechnical.id_inspection
                        == FinancialTicketManagement.ticket_id,
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

    def update_ticket_technical(self, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
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

                self._apply_fields(
                    management,
                    body,
                    {
                        "description": "description",
                        "status": "status",
                    },
                )
                self._set_updated_by(body, management)

                # Los materiales se reemplazan completos con lo que envía el formulario
                if "materials" in body:
                    session.execute(
                        delete(MaterialTechTicket).where(
                            MaterialTechTicket.tech_ticket
                            == management.id_management_technical
                        )
                    )
                    for material in body.get("materials") or []:
                        session.add(
                            MaterialTechTicket(
                                tech_ticket=management.id_management_technical,
                                material_id=material.get("material_id"),
                                material_description=material.get("material_description"),
                                other=material.get("other"),
                                quantity=material.get("quantity"),
                            )
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


                session.commit()
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al actualizar la gestión técnica",
                    internal,
                    external,
                )
            finally:
                session.close()

    def update_ticket_commercial(self, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
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

                self._apply_fields(
                    management,
                    body,
                    {
                        "assigned_user": "assigned_user",
                        "origin_id": "origin_id",
                        "type_solution_id": "type_solution_id",
                        "quoted_amount": "quoted_amount",
                        "probability_closing": "probability_closing",
                        "closing_date": "closing_date",
                        "next_action": "next_action",
                        "responsible_next_action": "responsible_next_action",
                        "requires_technical": "requires_technical",
                        "requires_material": "requires_material",
                        "scheduled_start_date": "scheduled_start_date",
                        "contract_received": "contract_received",
                        "date_finish": "date_finish",
                        "reason_loss": "reason_loss",
                        "observations": "observations",
                        "status_id": "status_id",
                    },
                )
                self._set_updated_by(body, management)

                if body.get('status_id') == 5 and ticket.management_area == 'Comercial':
                    ticket.management_area = 'Proyectos'
                    ticket.next_area = 'Financiera'

                    new_history_area = HistoryAreaTicket(
                        ticket_id=ticket.id_inspection,
                        previous_area="Comercial",
                        current_area="Proyectos",
                        created_by=body.get('user')
                    )

                    session.add(new_history_area)

                session.commit()
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al actualizar la gestión comercial",
                    internal,
                    external,
                )
            finally:
                session.close()

    def update_ticket_financial(self, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                self._validate_update_body(body, "inspection_id")
                ticket = self._get_inspection(session, body.get("inspection_id"))
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
                        "amount_pending": "amount_pending",
                        "amount_paid": "amount_paid",
                        "invoice_price": "invoice_price",
                        "observations": "observations",
                        "status": "status",
                        "date_document": "date_document",
                    },
                )
                self._set_updated_by(body, management)
                session.commit()
            except Exception as exception:
                session.rollback()
                self._raise_database_error(
                    exception,
                    "Error al actualizar la gestión financiera",
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

                inspection.status = "Listo para cotizar"
                inspection.updated_by = body.get("user")

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

                stmt = select(
                    InspectionTechnical,
                    TaskTechnical.id_task.label("project_id"),
                    commercial_status_id.label("commercial_status_id"),
                    commercial_status.label("commercial_status"),
                    TechnicalTicketManagement.id_management_technical.label("technical_id"),
                ).outerjoin(
                    TaskTechnical,
                    TaskTechnical.inspection_id == InspectionTechnical.id_inspection
                ).outerjoin(
                    TechnicalTicketManagement,
                    TechnicalTicketManagement.inspection_id == InspectionTechnical.id_inspection
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
                if filters.get("client_id") is not None:
                    conditions.append(InspectionTechnical.client_id == filters["client_id"])
                if filters.get("ubication_id") is not None:
                    conditions.append(InspectionTechnical.ubication_id == filters["ubication_id"])
                if filters.get("priority"):
                    conditions.append(InspectionTechnical.priority == filters["priority"])
                if filters.get("id_inspection"):
                    conditions.append(InspectionTechnical.id_inspection == filters["id_inspection"])
                if filters.get("responsible_id"):
                    conditions.append(InspectionTechnical.responsible_id == filters["responsible_id"])
                if filters.get("pending_technical") == 'true':
                    # Sin registro técnico asociado (LEFT JOIN sin coincidencia)
                    conditions.append(
                        TechnicalTicketManagement.id_management_technical.is_(None)
                    )

                if filters.get("pending_commercial") == 'true':
                    conditions.append(
                        InspectionTechnical.status == "Listo para cotizar"
                    )

                    conditions.append(
                        ~exists().where(
                            CommercialTicketManagement.ticket_id
                            == InspectionTechnical.id_inspection
                        )
                    )

                if filters.get("ready_for_project") == 'true':
                    # Comercial aprobado (status_id 5) y aún sin proyecto creado
                    conditions.append(commercial_status_id == 5)
                    conditions.append(TaskTechnical.id_task.is_(None))

                if conditions:
                    stmt = stmt.where(and_(*conditions))

                return session.execute(
                    stmt.order_by(InspectionTechnical.created_at.desc())
                ).all()

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
                date_conditions = self._inspection_date_conditions(filters)

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
                    ~exists().where(
                        TechnicalTicketManagement.inspection_id
                        == InspectionTechnical.id_inspection
                    )
                )
                pending_commercial = count_inspections(
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
        siguiente, el ticket sigue en esa área y se mide hasta el momento actual.
        """
        with self.db_telearseg.session_factory() as session:
            try:
                left_at = func.lead(HistoryAreaTicket.created_at).over(
                    partition_by=HistoryAreaTicket.ticket_id,
                    order_by=(HistoryAreaTicket.created_at, HistoryAreaTicket.id_history),
                )
                intervals = (
                    select(
                        HistoryAreaTicket.ticket_id,
                        HistoryAreaTicket.current_area.label("area"),
                        HistoryAreaTicket.created_at.label("entered_at"),
                        left_at.label("left_at"),
                    )
                    .join(
                        InspectionTechnical,
                        InspectionTechnical.id_inspection == HistoryAreaTicket.ticket_id,
                    )
                    .where(*self._inspection_date_conditions(filters))
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

    @staticmethod
    def _inspection_date_conditions(filters):
        conditions = []
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
