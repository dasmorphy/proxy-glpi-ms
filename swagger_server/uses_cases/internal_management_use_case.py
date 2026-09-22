from dataclasses import dataclass

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.repository.internal_management_repository import InternalManagementRepository

@dataclass
class PaginationParams:
    page: int = 1
    page_size: int = 20

    @property
    def offset(self):
        return (self.page - 1) * self.page_size

class InternalManagementUseCase:
    def __init__(self, internal_management_repository=None):
        self.internal_management_repository = (
            internal_management_repository or InternalManagementRepository()
        )

    def post_ticket_technical(self, body, internal, external):
        return self.internal_management_repository.post_ticket_technical(body, internal, external)

    def update_ticket_technical(self, body, internal, external):
        return self.internal_management_repository.update_ticket_technical(
            body,
            internal,
            external,
        )

    def add_management_area_to_tickets(self, tickets, internal, external):
        """Agrega management_area y priority_intern a la pagina de GLPI."""
        if not isinstance(tickets, list):
            return tickets

        ticket_ids = set()
        for ticket in tickets:
            ticket_id = self._normalize_ticket_id(ticket)
            if ticket_id is not None:
                ticket_ids.add(ticket_id)

        management_data = (
            self.internal_management_repository.get_management_areas_by_ticket_ids(
                sorted(ticket_ids),
                internal,
                external,
            )
        )

        enriched_tickets = []
        for ticket in tickets:
            if not isinstance(ticket, dict):
                enriched_tickets.append(ticket)
                continue
            enriched_ticket = dict(ticket)
            ticket_id = self._normalize_ticket_id(ticket)
            ticket_management = management_data.get(ticket_id, {})
            enriched_ticket["management_area"] = ticket_management.get(
                "management_area"
            )
            enriched_ticket["priority_intern"] = ticket_management.get("priority")
            enriched_tickets.append(enriched_ticket)
        return enriched_tickets

    @staticmethod
    def _normalize_ticket_id(ticket):
        if not isinstance(ticket, dict):
            return None
        try:
            return int(ticket.get("id"))
        except (TypeError, ValueError):
            return None


    def get_ticket_technical(self, headers, params, internal, external):
        filters = self._build_ticket_filters(params)
        filters.update(
            {
                "management_status": params.get("management_status"),
                "case_type": params.get("case_type"),
                "pending_commercial": params.get("pending_commercial"),
                "ticket_technical_id": params.get("ticket_technical_id"),
            }
        )
        pagination = self.parse_pagination(params)
        rows, total = self.internal_management_repository.get_ticket_technical(
            filters,
            pagination,
            internal,
            external,
        )

        return {
            "data": [
                {
                    **self._serialize_ticket(ticket),
                    "id_management_technical": management.id_management_technical,
                    "code_management": management.code_management,
                    "case_type": management.case_type,
                    "management_status": management.management_status,
                    "next_action": management.next_action,
                    "commitment_date": management.commitment_date,
                    "requires_material": management.requires_material,
                    "requires_monitoring": management.requires_monitoring,
                    "observations": management.observations,
                    "status": management.status,
                    "created_at": management.created_at,
                    "updated_at": management.updated_at,
                    "created_by": management.created_by,
                    "updated_by": management.updated_by,
                }
                for management, ticket in rows
            ],
            "pagination": {
                "page": pagination.page,
                "page_size": pagination.page_size,
                "total": total,
                "total_pages": -(-total // pagination.page_size),
                "has_next": (pagination.offset + pagination.page_size) < total,
                "has_prev": pagination.page > 1,
            },
        }

    def parse_pagination(self, params: dict) -> PaginationParams:
        try:
            page = max(1, int(params.get("page", 1)))
            page_size = min(100, max(1, int(params.get("page_size", 20))))  # máximo 100
            return PaginationParams(page=page, page_size=page_size)
        except (ValueError, TypeError):
            return PaginationParams()


    def post_ticket_commercial(self, body, internal, external):
        return self.internal_management_repository.post_ticket_commercial(body, internal, external)

    def update_ticket_commercial(self, body, internal, external):
        return self.internal_management_repository.update_ticket_commercial(
            body,
            internal,
            external,
        )


    def _build_ticket_filters(self, params, include_status=True):
        filters = {
            "start_date": params.get("start_date"),
            "end_date": params.get("end_date"),
            "ticket_id": self._optional_int(params.get("ticket_id"), "ticket_id"),
            "ticket_glpi": self._optional_int(
                params.get("ticket_glpi"),
                "ticket_glpi",
            ),
            "responsible": params.get("responsible"),
            "client_id": self._optional_int(params.get("client_id"), "client_id"),
            "ubication_id": self._optional_int(
                params.get("ubication_id"),
                "ubication_id",
            ),
            "priority": params.get("priority"),
            "search": params.get("search", "").strip() or None,
        }
        if include_status:
            filters["status"] = params.get("status")
        return filters

    @staticmethod
    def _optional_int(value, field_name):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise CustomAPIException(
                f"El parámetro {field_name} debe ser un número entero",
                400,
            )

    @staticmethod
    def _serialize_ticket(ticket):
        return {
            "ticket_id": ticket.id_ticket,
            "ticket_glpi": ticket.ticket_glpi,
            "management_area": ticket.management_area,
            "next_area": ticket.next_area,
            "title_ticket": ticket.title_ticket,
            "ticket_status": ticket.status,
            "contact": ticket.contact,
            "client_id": ticket.client_id,
            "ubication_id": ticket.ubication_id,
            "priority": ticket.priority,
            "client_name": ticket.client_name,
            "location_name": ticket.ubication_name,
            "responsible_ticket": ticket.responsible_ticket,
            "ticket_created_at": ticket.created_at,
            "ticket_updated_at": ticket.updated_at,
            "ticket_created_by": ticket.created_by,
            "ticket_updated_by": ticket.updated_by,
        }

    def get_type_solution(self, internal, external):
        return self.internal_management_repository.get_type_solution(internal, external)

    def get_commercial_ticket_status(self, internal, external):
        return self.internal_management_repository.get_commercial_ticket_status(internal, external)

    def get_commercial_origin(self, internal, external):
        return self.internal_management_repository.get_commercial_origin(internal, external)

    def post_ticket_financial(self, body, internal, external):
        return self.internal_management_repository.post_ticket_financial(
            body,
            internal,
            external,
        )

    def update_ticket_financial(self, body, internal, external):
        return self.internal_management_repository.update_ticket_financial(
            body,
            internal,
            external,
        )

    def get_ticket_financial(self, headers, params, internal, external):
        filters = self._build_ticket_filters(params)
        filters.update(
            {
                "type_management": params.get("type_management"),
                "code_management": params.get("code_management"),
                "ticket_financial_id": params.get("ticket_financial_id"),
                "user": params.get("user"),
            }
        )
        rows = self.internal_management_repository.get_ticket_financial(
            filters,
            internal,
            external,
        )

        return [
            {
                **self._serialize_ticket(ticket),
                "id_management_financial": management.id_management_financial,
                "code_management": management.code_management,
                "type_management": management.type_management,
                "amount_pending": management.amount_pending,
                "amount_paid": management.amount_paid,
                "invoice_price": management.invoice_price,
                "observations": management.observations,
                "status": management.status,
                "date_document": management.date_document,
                "created_at": management.created_at,
                "updated_at": management.updated_at,
                "created_by": management.created_by,
                "updated_by": management.updated_by,
            }
            for management, ticket in rows
        ]


    def get_ticket_commercial(self, headers, params, internal, external):
        filters = self._build_ticket_filters(params, include_status=False)
        filters.update(
            {
                "assigned_user": params.get("assigned_user"),
                "ticket_commercial_id": params.get("ticket_commercial_id"),
                "is_registred": params.get("is_registred"),
                "pending_financial": params.get("pending_financial"),
                "origin_id": self._optional_int(params.get("origin_id"), "origin_id"),
                "type_solution_id": self._optional_int(
                    params.get("type_solution_id"),
                    "type_solution_id",
                ),
                "status_id": self._optional_int(params.get("status_id"), "status_id"),
            }
        )

        rows = self.internal_management_repository.get_ticket_commercial(
            filters,
            internal,
            external,
        )

        return [
            {
                **self._serialize_ticket(ticket),
                "id_management_commercial": management.id_management_commercial,
                "assigned_user": management.assigned_user,
                "code_management": management.code_management,
                "origin_id": management.origin_id,
                "origin_name": origin_name,
                "type_solution_id": management.type_solution_id,
                "type_solution_name": type_solution_name,
                "quoted_amount": management.quoted_amount,
                "probability_closing": management.probability_closing,
                "closing_date": management.closing_date,
                "next_action": management.next_action,
                "responsible_next_action": management.responsible_next_action,
                "requires_technical": management.requires_technical,
                "requires_material": management.requires_material,
                "scheduled_start_date": management.scheduled_start_date,
                "contract_received": management.contract_received,
                "date_finish": management.date_finish,
                "reason_loss": management.reason_loss,
                "observations": management.observations,
                "status_id": management.status_id,
                "status_name": status_name,
                "created_at": management.created_at,
                "updated_at": management.updated_at,
                "created_by": management.created_by,
                "updated_by": management.updated_by,
                "last_followup_at": last_followup_at
            }
            for management, ticket, origin_name, type_solution_name, status_name, last_followup_at in rows
        ]

    def get_history_area(self, id_ticket: int, internal, external) -> None:
        rows = self.internal_management_repository.get_history_area(id_ticket, internal, external)

        return [
            {
                "id_history": c.id_history,
                "ticket_id": c.ticket_id,
                "previous_area": c.previous_area,
                "current_area": c.current_area,
                "created_at": c.created_at,
                "created_by": c.created_by,
            }
            for c in rows
        ]

    def approve_ticket_commercial(self, body, internal, external):
        return self.internal_management_repository.approve_ticket_commercial(
            body,
            internal,
            external,
        )

    def new_followup_commercial(self, body, internal, external):
        return self.internal_management_repository.new_followup_commercial(
            body,
            internal,
            external,
        )

    def get_followup_commercial(self, params, internal, external):
        filters = {
            "user": params.get("user"),
            "id_commercial": params.get("id_commercial")
        }

        rows = self.internal_management_repository.get_followup_commercial(filters, internal, external)

        results = [
            {
                "id_followup": c.id_followup,
                "management_commercial_id": c.management_commercial_id,
                "observations": c.observations,
                "created_at": c.created_at,
                "created_by": c.created_by,
            }
            for c in rows
        ]

        return results

