from swagger_server.repository.internal_management_repository import InternalManagementRepository


class InternalManagementUseCase:
    def __init__(self):
        self.internal_management_repository = InternalManagementRepository()

    def post_ticket_technical(self, body, internal, external):
        return self.internal_management_repository.post_ticket_technical(body, internal, external)