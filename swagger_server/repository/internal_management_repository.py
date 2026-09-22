from datetime import datetime

from loguru import logger
from sqlalchemy import and_, exists, func, select

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
from swagger_server.models.db.technical_ticket_management import TechnicalTicketManagement
from swagger_server.models.db.tickets_management import TicketsManagement
from swagger_server.resources.databases.postgresql import PostgreSQLClient
from swagger_server.utils.utils import SEARCH_COLUMNS_TECHNICAL_TICKETS, apply_search


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

    def get_management_areas_by_ticket_ids(self, ticket_ids, internal, external):
        """Obtiene area y prioridad de una pagina de tickets en una consulta."""
        unique_ticket_ids = sorted(set(ticket_ids))
        if not unique_ticket_ids:
            return {}

        with self.db_telearseg.session_factory() as session:
            try:
                rows = session.execute(
                    select(
                        TicketsManagement.ticket_glpi,
                        TicketsManagement.management_area,
                        TicketsManagement.priority,
                    )
                    .where(TicketsManagement.ticket_glpi.in_(unique_ticket_ids))
                    .order_by(TicketsManagement.id_ticket.desc())
                ).all()

                management_data = {}
                for ticket_glpi, management_area, priority in rows:
                    # Si existen registros historicos duplicados, se conserva
                    # el mas reciente gracias al orden descendente por id.
                    management_data.setdefault(
                        ticket_glpi,
                        {
                            "management_area": management_area,
                            "priority": priority,
                        },
                    )
                return management_data
            except Exception as exception:
                logger.error(
                    'Error: {}',
                    str(exception),
                    internal=internal,
                    external=external,
                )
                if isinstance(exception, CustomAPIException):
                    raise exception
                raise CustomAPIException(
                    "Error al consultar las areas de gestion de los tickets",
                    500,
                )

    def post_ticket_technical(self, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                current_area = "Comercial" if body.get("status") == "Listo para cotizar" else "Técnica"
                next_area = "Proyectos" if current_area == "Comercial" else "Comercial"

                new_ticket = TicketsManagement(
                    ticket_glpi=body.get('ticket_glpi'),
                    management_area=current_area,
                    next_area=next_area,
                    title_ticket=body.get('title_ticket'),
                    contact=body.get('contact'),
                    priority=body.get('priority'),
                    responsible_ticket=body.get('responsible'),
                    client_id=body.get('client_id'),
                    ubication_id=body.get('ubication_id'),
                    created_by=body.get('user'),
                    updated_by=body.get('user'),
                    client_name=body.get('client_name'),
                    ubication_name=body.get('ubication_name'),
                )

                session.add(new_ticket)
                session.flush()

                new_history_area = HistoryAreaTicket(
                    ticket_id=new_ticket.id_ticket,
                    previous_area="Técnica",
                    current_area=current_area,
                    created_by=body.get('user')
                )

                session.add(new_history_area)

                new_register = TechnicalTicketManagement(
                    ticket_id=new_ticket.id_ticket,
                    case_type=body.get('case_type'),
                    management_status=body.get('management_status'),
                    next_action=body.get('next_action'),
                    commitment_date=body.get('commitment_date'),
                    requires_material=body.get('requires_material'),
                    requires_monitoring=body.get('requires_monitoring'),
                    observations=body.get('observations'),
                    status=body.get('status'),
                    created_by=body.get('user'),
                    updated_by=body.get('user'),
                )

                session.add(new_register)
                session.flush()
                new_register.code_management = self.generate_code_technical(
                    new_register.id_management_technical
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


    def get_ticket_technical(self, filters, pagination, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                stmt = (
                    select(
                        TechnicalTicketManagement,
                        TicketsManagement,
                    )
                    .join(
                        TicketsManagement,
                        TicketsManagement.id_ticket
                        == TechnicalTicketManagement.ticket_id,
                    )
                )

                conditions = self._ticket_conditions(
                    filters,
                    TechnicalTicketManagement,
                )
                if filters.get("management_status"):
                    conditions.append(
                        TechnicalTicketManagement.management_status
                        == filters["management_status"]
                    )
                if filters.get("case_type"):
                    conditions.append(
                        TechnicalTicketManagement.case_type == filters["case_type"]
                    )

                if filters.get("ticket_technical_id") is not None:
                    conditions.append(TechnicalTicketManagement.id_management_technical == filters["ticket_technical_id"])

                if filters.get("pending_commercial") == 'true':
                    conditions.append(
                        TechnicalTicketManagement.status == "Listo para cotizar"
                    )

                    conditions.append(
                        ~exists().where(
                            CommercialTicketManagement.ticket_id
                            == TechnicalTicketManagement.ticket_id
                        )
                    )

                apply_search(
                    conditions,
                    filters.get("search"),
                    [
                        *SEARCH_COLUMNS_TECHNICAL_TICKETS,
                        TicketsManagement.title_ticket,
                        TicketsManagement.contact,
                        TicketsManagement.priority,
                        TicketsManagement.responsible_ticket,
                    ],
                )

                if conditions:
                    stmt = stmt.where(and_(*conditions))

                total_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
                total = session.execute(total_stmt).scalar() or 0

                paginated_stmt = (
                    stmt.order_by(
                        TechnicalTicketManagement.created_at.desc(),
                        TechnicalTicketManagement.id_management_technical.desc(),
                    )
                    .offset(pagination.offset)
                    .limit(pagination.page_size)
                )
                rows = session.execute(paginated_stmt).all()

                # client_names, location_names = self._get_client_and_location_names(
                #     [ticket.client_id for _, ticket in rows if ticket.client_id],
                #     [ticket.ubication_id for _, ticket in rows if ticket.ubication_id],
                #     internal,
                #     external,
                # )
                rows_with_names = [
                    (
                        management,
                        ticket,
                    )
                    for management, ticket in rows
                ]

                return rows_with_names, total
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
                    select(TicketsManagement).where(
                        TicketsManagement.ticket_glpi == body.get('ticket_id')
                    )
                ).scalar_one_or_none()

                if ticket is None:
                    raise CustomAPIException("Ticket no encontrado", 404)


                if body.get('status_id') == 5: 
                    ticket.management_area = 'Proyectos'
                    ticket.next_area = 'Financiera'

                    new_history_area = HistoryAreaTicket(
                        ticket_id=ticket.id_ticket,
                        previous_area="Comercial",
                        current_area="Proyectos",
                        created_by=body.get('user')
                    )
                    session.add(new_history_area)

                else:
                    ticket.management_area = 'Comercial'
                    ticket.next_area = 'Proyectos'

                new_register = CommercialTicketManagement(
                    ticket_id=ticket.id_ticket,
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
                        TicketsManagement,
                        CommercialOrigin.name.label("origin_name"),
                        CommercialTypeSolution.name.label("type_solution_name"),
                        CommercialTicketStatus.name.label("status_name"),
                        last_followup.c.last_followup_at,
                    )
                    .join(
                        TicketsManagement,
                        TicketsManagement.id_ticket
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


    def get_history_area(self, ticket_glpi, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                stmt = (
                    select(HistoryAreaTicket)
                    .join(
                        TicketsManagement,
                        TicketsManagement.id_ticket
                        == HistoryAreaTicket.ticket_id,
                    )
                    .where(TicketsManagement.ticket_glpi == ticket_glpi)
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
            conditions.append(TicketsManagement.management_area == "Proyectos")
        if filters.get("pending_financial") == "true":
            conditions.append(
                TicketsManagement.management_area
                == "Financiera"
            )
            conditions.append(
                TicketsManagement.next_area
                == "Financiera"
            )
        if filters.get("ticket_glpi") is not None:
            conditions.append(TicketsManagement.ticket_glpi == filters["ticket_glpi"])
        if filters.get("status"):
            conditions.append(management_model.status == filters["status"])
        if filters.get("responsible"):
            conditions.append(
                TicketsManagement.responsible_ticket == filters["responsible"]
            )
        if filters.get("client_id") is not None:
            conditions.append(TicketsManagement.client_id == filters["client_id"])
        if filters.get("ubication_id") is not None:
            conditions.append(
                TicketsManagement.ubication_id == filters["ubication_id"]
            )
        if filters.get("priority"):
            conditions.append(TicketsManagement.priority == filters["priority"])
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
                    select(TicketsManagement).where(
                        TicketsManagement.ticket_glpi == body.get("ticket_id")
                    )
                ).scalar_one_or_none()
                if ticket is None:
                    raise CustomAPIException("Ticket no encontrado", 404)

                ticket.management_area = "Financiera"

                if body.get("status") == "Cobrada":
                    ticket.status = "Finalizado"

                financial_management = FinancialTicketManagement(
                    ticket_id=ticket.id_ticket,
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
                    select(FinancialTicketManagement, TicketsManagement)
                    .join(
                        TicketsManagement,
                        TicketsManagement.id_ticket
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
                self._validate_update_body(body, "ticket_glpi")
                ticket = self._get_ticket_by_glpi(session, body.get("ticket_glpi"))
                management = self._get_latest_management(
                    session,
                    TechnicalTicketManagement,
                    ticket.id_ticket,
                    TechnicalTicketManagement.id_management_technical,
                )
                if management is None:
                    raise CustomAPIException("Gestión técnica no encontrada", 404)

                self._apply_fields(
                    ticket,
                    body,
                    {
                        "title_ticket": "title_ticket",
                        "contact": "contact",
                        "priority": "priority",
                        "responsible": "responsible_ticket",
                        "client_id": "client_id",
                        "ubication_id": "ubication_id",
                    },
                )
                self._apply_fields(
                    management,
                    body,
                    {
                        "case_type": "case_type",
                        "management_status": "management_status",
                        "next_action": "next_action",
                        "commitment_date": "commitment_date",
                        "requires_material": "requires_material",
                        "requires_monitoring": "requires_monitoring",
                        "observations": "observations",
                        "status": "status",
                    },
                )
                self._set_updated_by(body, ticket, management)

                if body.get("status") == 'Listo para cotizar':
                    ticket.management_area = "Comercial"
                    ticket.next_area = "Financiero"

                    new_history_area = HistoryAreaTicket(
                        ticket_id=ticket.id_ticket,
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
                self._validate_update_body(body, "ticket_id")
                ticket = self._get_ticket_by_glpi(session, body.get("ticket_id"))
                management = self._get_latest_management(
                    session,
                    CommercialTicketManagement,
                    ticket.id_ticket,
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

                if body.get('status_id') == 5: 
                    ticket.management_area = 'Proyectos'
                    ticket.next_area = 'Financiera'

                    new_history_area = HistoryAreaTicket(
                        ticket_id=ticket.id_ticket,
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
                self._validate_update_body(body, "ticket_id")
                ticket = self._get_ticket_by_glpi(session, body.get("ticket_id"))
                management = self._get_latest_management(
                    session,
                    FinancialTicketManagement,
                    ticket.id_ticket,
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
                    select(TicketsManagement).where(
                        TicketsManagement.id_ticket == ticket_commercial.ticket_id
                    )
                ).scalar_one_or_none()

                if ticket_management is None:
                    raise CustomAPIException("Ticket no encontrado", 404)

                ticket_management.management_area = "Financiera"
                ticket_management.next_area = "Financiera"
                ticket_management.updated_by = body.get("user")
                ticket_management.updated_at = datetime.now()

                new_history_area = HistoryAreaTicket(
                    ticket_id=ticket_management.id_ticket,
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
    def _get_ticket_by_glpi(session, ticket_glpi):
        ticket = session.execute(
            select(TicketsManagement).where(
                TicketsManagement.ticket_glpi == ticket_glpi
            )
        ).scalar_one_or_none()
        
        if ticket is None:
            raise CustomAPIException("Ticket no encontrado", 404)
        return ticket
