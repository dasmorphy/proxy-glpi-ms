from dataclasses import dataclass

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.models.db.inspection_technical import InspectionTechnical
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

    def post_inspection_technical(self, body, internal, external):
        return self.internal_management_repository.post_inspection_technical(body, internal, external)

    def update_inspection_technical(self, id_inspection, body, internal, external):
        return self.internal_management_repository.update_inspection_technical(
            id_inspection,
            body,
            internal,
            external,
        )

    def update_ticket_technical(self, body, internal, external):
        return self.internal_management_repository.update_ticket_technical(
            body,
            internal,
            external,
        )

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
                "pending_commercial": params.get("pending_commercial"),
                "user": params.get("user"),
                "ticket_technical_id": params.get("ticket_technical_id"),
            }
        )

        rows = self.internal_management_repository.get_ticket_technical(
            filters,
            internal,
            external,
        )

        return [
            {
                **self._serialize_ticket(ticket),
                "id_management_technical": management.id_management_technical,
                "code_management": management.code_management,
                "description": management.description,
                "status": management.status,
                "created_at": management.created_at,
                "updated_at": management.updated_at,
                "created_by": management.created_by,
                "updated_by": management.updated_by,
                "materials": [
                    {
                        "id_material": material.id_material,
                        "material_id": material.material_id,
                        "material_description": material.material_description,
                        "other": material.other,
                        "quantity": material.quantity,
                        "created_at": material.created_at,
                    }
                    for material in materials
                ],
            }
            for management, ticket, materials in rows
        ]
        

    def get_inspection_technical(self, headers, params, internal, external):
        filters = self._build_ticket_filters(params)
        rows = self.internal_management_repository.get_inspection_technical(
            filters,
            internal,
            external,
        )

        return [
            {
                **self._serialize_ticket(inspection),
                "project_id": project_id,
                "commercial_status_id": commercial_status_id,
                "commercial_status": commercial_status,
                "technical_id": technical_id,
                # Comercial aprobado (status_id 5) y sin proyecto: se puede crear el proyecto
                "ready_for_project": commercial_status_id == 5 and project_id is None,
            }
            for inspection, project_id, commercial_status_id, commercial_status, technical_id in rows
        ]

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
            "id_inspection": params.get("id_inspection"),
            "responsible_id": params.get("responsible_id"),
            "ticket_id": self._optional_int(params.get("ticket_id"), "ticket_id"),
            "responsible": params.get("responsible"),
            "pending_technical": params.get("pending_technical"),
            "pending_commercial": params.get("pending_commercial"),
            "ready_for_project": params.get("ready_for_project"),
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
    def _serialize_ticket(ticket: InspectionTechnical):
        return {
            "id_inspection": ticket.id_inspection,
            "management_area": ticket.management_area,
            "next_area": ticket.next_area,
            "title_ticket": ticket.title_ticket,
            "status": ticket.status,
            "contact": ticket.contact,
            "commitment_date": ticket.commitment_date,
            "code": ticket.code,
            # "management_status": ticket.management_status,
            "case_type": ticket.case_type,
            "client_id": ticket.client_id,
            "ubication_id": ticket.ubication_id,
            "priority": ticket.priority,
            "client_name": ticket.client_name,
            "location_name": ticket.ubication_name,
            "responsible_id": ticket.responsible_id,
            "responsible_name": ticket.responsible_name,
            "created_at": ticket.created_at,
            "updated_at": ticket.updated_at,
            "created_by": ticket.created_by,
            "updated_by": ticket.updated_by,
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

    def get_history_area(self, id_inspection: int, internal, external) -> None:
        rows = self.internal_management_repository.get_history_area(id_inspection, internal, external)

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

    def get_inspection_materials(self, params, internal, external):
        inspection_id = params.get("inspection_id")
        if inspection_id is None or not str(inspection_id).isdigit():
            raise CustomAPIException("El parámetro inspection_id es requerido", 400)

        rows = self.internal_management_repository.get_inspection_materials(
            int(inspection_id), internal, external
        )

        def to_float(value):
            return float(value) if value is not None else None

        return [
            {
                "id_material": material.id_material,
                "tech_ticket": material.tech_ticket,
                "material_id": material.material_id,
                "material_description": material.material_description,
                "other": material.other,
                "quantity": material.quantity,
                "equipment": {
                    "id_equipment": equipment.id_equipment,
                    "code": equipment.code,
                    "product": equipment.product,
                    "unit": equipment.unit,
                    "model": equipment.model,
                    "base_price": to_float(equipment.base_price),
                    "profit_margin": to_float(equipment.profit_margin),
                    "profit_margin_dollar": to_float(equipment.profit_margin_dollar),
                    "price": to_float(equipment.price),
                    "provider": equipment.provider,
                    "description": equipment.description,
                    "stock": equipment.stock,
                } if equipment is not None else None,
            }
            for material, equipment in rows
        ]

    def approve_technical_inspection(self, body, internal, external):
        return self.internal_management_repository.approve_technical_inspection(
            body,
            internal,
            external,
        )

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

    DASHBOARD_AREAS = ("Técnica", "Comercial", "Proyectos", "Financiera")

    def get_dashboard(self, params, internal, external):
        filters = {
            "start_date": params.get("start_date"),
            "end_date": params.get("end_date"),
        }
        counts = self.internal_management_repository.get_dashboard_counts(
            filters,
            internal,
            external,
        )
        sla_rows, inspection_rows = self.internal_management_repository.get_dashboard_area_times(
            filters,
            internal,
            external,
        )

        pending = dict(zip(self.DASHBOARD_AREAS, (
            counts["pending_technical"],
            counts["pending_commercial"],
            counts["pending_projects"],
            counts["pending_financial"],
        )))
        finished = dict(zip(self.DASHBOARD_AREAS, (
            counts["finished_technical"],
            counts["quotations_approved"],
            counts["finished_projects"],
            counts["invoices_collected"],
        )))
        finished_total = sum(finished.values())
        quotations_total = counts["quotations_approved"] + counts["quotations_rejected"]
        invoices_total = counts["invoices_issued"] + counts["invoices_collected"]

        return {
            "pending_by_area": [
                {"area": area, "count": count} for area, count in pending.items()
            ],
            "finished_by_area": {
                "total": finished_total,
                "areas": [
                    {
                        "area": area,
                        "count": count,
                        "percentage": self._percentage(count, finished_total),
                    }
                    for area, count in finished.items()
                ],
            },
            "quotations": {
                "total": quotations_total,
                "approved": {
                    "count": counts["quotations_approved"],
                    "percentage": self._percentage(counts["quotations_approved"], quotations_total),
                },
                "rejected": {
                    "count": counts["quotations_rejected"],
                    "percentage": self._percentage(counts["quotations_rejected"], quotations_total),
                },
            },
            "invoices": {
                "issued": counts["invoices_issued"],
                "collected": counts["invoices_collected"],
                "collected_percentage": self._percentage(counts["invoices_collected"], invoices_total),
            },
            "sla_by_area": [
                {
                    "area": area,
                    "average_seconds": round(float(average_seconds)),
                    "average_duration": self._format_duration(average_seconds),
                    "transitions": transitions,
                }
                for area, average_seconds, transitions in sorted(
                    sla_rows,
                    key=lambda row: row.average_seconds,
                )
            ],
            "inspection_area_times": self._group_inspection_area_times(inspection_rows),
        }

    def get_project_activities(self, internal, external):
        rows = self.internal_management_repository.get_project_activities(internal, external)
        return [
            {
                "id_task": id_task,
                "code": code,
                "total_records": total_records,
            }
            for id_task, code, total_records in rows
        ]

    def _group_inspection_area_times(self, rows):
        inspections = {}
        for row in rows:
            inspection = inspections.setdefault(
                row.id_inspection,
                {
                    "id_inspection": row.id_inspection,
                    "title_ticket": row.title_ticket,
                    "management_area": row.management_area,
                    "areas": [],
                },
            )
            inspection["areas"].append(
                {
                    "area": row.area,
                    "seconds": round(float(row.seconds)),
                    "duration": self._format_duration(row.seconds),
                    "in_progress": row.in_progress,
                }
            )
        return list(inspections.values())

    @staticmethod
    def _percentage(value, total):
        return round(value * 100 / total, 2) if total else 0

    @staticmethod
    def _format_duration(seconds):
        """Convierte segundos a texto legible con las dos unidades mayores: '2 días 3 horas'."""
        remaining = max(0, int(round(float(seconds or 0))))
        units = (
            (86400, "día", "días"),
            (3600, "hora", "horas"),
            (60, "minuto", "minutos"),
            (1, "segundo", "segundos"),
        )
        parts = []
        for size, singular, plural in units:
            value, remaining = divmod(remaining, size)
            if value:
                parts.append(f"{value} {singular if value == 1 else plural}")
            if len(parts) == 2:
                break
        return " ".join(parts) or "0 segundos"

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
