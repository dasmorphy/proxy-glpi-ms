
from loguru import logger
from sqlalchemy import exists, select

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.models.db.technical_ticket_management import TechnicalTicketManagement
from swagger_server.resources.databases.postgresql import PostgreSQLClient


class InternalManagementRepository:
    def __init__(self):
        self.db_telearseg = PostgreSQLClient("TELEARSEG")
        self.db_zentinel = PostgreSQLClient("ZENTINEL")


    def post_ticket_technical(self, body, internal, external):
        with self.db_telearseg.session_factory() as session:
            try:
                new_register = TechnicalTicketManagement(
                    ticket_glpi=body.get('ticket_glpi'),
                    code_management=body.get('code_management'),
                    client_id=body.get('client_id'),
                    ubication_client_id=body.get('ubication_id'),
                    contact=body.get('contact'),
                    case_type=body.get('case_type'),
                    priority=body.get('priority'),
                    responsible=body.get('responsible'),
                    management_status=body.get('management_status'),
                    next_action=body.get('next_action'),
                    commitment_date=body.get('commitment_date'),
                    requires_material=body.get('requires_material'),
                    requires_monitoring=body.get('requires_monitoring'),
                    status=body.get('status'),
                    created_by=body.get('user'),
                    updated_by=body.get('user'),
                )

                session.add(new_register)
                session.commit()

            except Exception as exception:
                session.rollback()
                logger.error('Error: {}', str(exception), internal=internal, external=external)
                if isinstance(exception, CustomAPIException):
                    raise exception
                
                raise CustomAPIException("Error al insertar en la base de datos", 500)

            finally:
                session.close()
