from dataclasses import dataclass

from swagger_server.exception.custom_error_exception import CustomAPIException
from swagger_server.models.db.inspection_technical import InspectionTechnical
from swagger_server.repository.internal_management_repository import InternalManagementRepository
from swagger_server.utils.inspection_documents import (
    document_mimetype,
    document_name,
    resolve_document_path,
)
from swagger_server.utils.proforma_pdf import format_quantity, generate_proforma_pdf

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

    def post_ticket_technical(self, body, internal, external, files=None):
        return self.internal_management_repository.post_ticket_technical(
            body, internal, external, files=files
        )

    def post_inspection_technical(self, body, internal, external, files=None):
        return self.internal_management_repository.post_inspection_technical(
            body, internal, external, files=files
        )

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
                "description_technical": technical_description,
                "commercial_status_id": commercial_status_id,
                "commercial_status": commercial_status,
                "technical_id": technical_id,
                "technical_id": technical_id,
                "identity": identity,
                "company_name": company_name,
                "client_company_id": client_company_id,
                # PDF de la proforma: /sale-quotation/{sale_quote_id}/pdf
                "sale_quote_id": sale_quote_id,
                # Total de la proforma: valor facturado de la gestión financiera
                "sale_quote_total": sale_quote_total,
                # Comercial aprobado (status_id 5) y sin proyecto: se puede crear el proyecto
                "ready_for_project": commercial_status_id == 5 and project_id is None,
                "documents": [
                    {
                        "id_document": document.id_document,
                        "document_path": document.document_path,
                        # Los registros previos a name_document se resuelven desde la ruta
                        "document_name": document.name_document or document_name(document.document_path),
                        "type": document.type_document,
                        "created_at": document.created_at,
                    }
                    for document in documents
                ],
            }
            for inspection, project_id, commercial_status_id, commercial_status, technical_id, technical_description, identity, company_name, client_company_id, sale_quote_id, sale_quote_total, documents in rows
        ]

    def get_inspection_document(self, id_document, internal, external):
        """Retorna la ruta absoluta del archivo, su nombre original y su tipo MIME."""
        document = self.internal_management_repository.get_inspection_document(
            id_document,
            internal,
            external,
        )
        name = document.name_document or document_name(document.document_path)
        return (
            resolve_document_path(document.document_path),
            name,
            document.type_document or document_mimetype(name),
        )


    def post_ticket_commercial(self, body, internal, external, files=None):
        return self.internal_management_repository.post_ticket_commercial(
            body, internal, external, files=files
        )

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
            "sales_user": params.get("sales_user", "").strip() or None,
            "pending_technical": params.get("pending_technical"),
            "pending_commercial": params.get("pending_commercial"),
            "ready_for_project": params.get("ready_for_project"),
            # Acepta uno o varios ids separados por coma: client_id=1,2,3
            "client_id": self._optional_int_list(params.get("client_id"), "client_id"),
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
    def _optional_int_list(value, field_name):
        if value is None or str(value).strip() == "":
            return None
        try:
            values = [int(item) for item in str(value).split(",") if item.strip()]
        except (TypeError, ValueError):
            raise CustomAPIException(
                f"El parámetro {field_name} debe ser una lista de números enteros separados por coma",
                400,
            )
        return values or None

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
            "sales_user": ticket.sales_user,
            "created_at": ticket.created_at,
            "updated_at": ticket.updated_at,
            "created_by": ticket.created_by,
            "updated_by": ticket.updated_by,
        }

    def get_type_solution(self, internal, external):
        return self.internal_management_repository.get_type_solution(internal, external)

    def get_providers(self, internal, external):
        return self.internal_management_repository.get_providers(internal, external)

    def get_commercial_ticket_status(self, internal, external):
        return self.internal_management_repository.get_commercial_ticket_status(internal, external)

    def get_commercial_origin(self, internal, external):
        return self.internal_management_repository.get_commercial_origin(internal, external)

    def post_ticket_financial(self, body, internal, external, files=None):
        return self.internal_management_repository.post_ticket_financial(
            body,
            internal,
            external,
            files=files,
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
                "number_document": management.number_document,
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
                "last_followup_at": last_followup_at,
            }
            for management, ticket, last_followup_at in rows
        ]


    def get_ticket_commercial(self, headers, params, internal, external):
        filters = self._build_ticket_filters(params, include_status=False)
        filters.update(
            {
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
                "last_followup_at": last_followup_at,
                "sale_quotation": self._serialize_sale_quotation(sale_quotation),
            }
            for management, ticket, origin_name, type_solution_name, status_name, last_followup_at, sale_quotation in rows
        ]

    @staticmethod
    def _amount(value):
        # Numeric llega como Decimal y Flask lo serializaría como texto
        return float(value) if value is not None else None

    def _serialize_sale_quotation(self, sale_quotation):
        if sale_quotation is None:
            return None

        quotation, items, components = sale_quotation
        components_by_item = {}
        for component in components:
            components_by_item.setdefault(component.quotation_item_id, []).append(component)

        def prices(record):
            return {
                "material_id": record.material_id,
                "quantity": self._amount(record.quantity),
                "base_price": self._amount(record.base_price),
                "profit_margin": self._amount(record.profit_margin),
                "profit_margin_dollar": self._amount(record.profit_margin_dollar),
                "total": self._amount(record.total),
            }

        return {
            "id_quote": quotation.id_quote,
            "client_company": quotation.client_company,
            "items": [
                {
                    "id_item": item.id_item,
                    "item": item.item_number,
                    **prices(item),
                    "is_bundle": bool(item.is_bundle),
                    "is_labor": bool(item.is_labor),
                    "is_new": bool(item.is_new),
                    "material_tech_ticket_id": item.material_tech_ticket_id,
                    "model": item.model,
                    "description": item.description,
                    "components": [
                        {
                            **prices(component),
                            "id_extra": component.id_extra,
                            "is_new": bool(component.is_new),
                            "material_tech_ticket_id": component.material_tech_ticket_id,
                            "model": component.model,
                            "description": component.description,
                        }
                        for component in components_by_item.get(item.id_item, [])
                    ],
                }
                for item in items
            ],
            "subtotal": self._amount(quotation.subtotal),
            "iva_rate": self._amount(quotation.iva_rate),
            "iva": self._amount(quotation.iva),
            "total": self._amount(quotation.total),
            "delivery_time": quotation.delivery_time,
            "payment_terms": quotation.payment_terms,
            "validity_days": quotation.validity_days,
        }

    def generate_sale_quotation_pdf(self, id_quote, internal, external):
        """Retorna el PDF de la proforma en bytes y el nombre del archivo."""
        quotation, inspection, company, seller, items, components, equipment = (
            self.internal_management_repository.get_sale_quotation_document(
                id_quote, internal, external
            )
        )

        components_by_item = {}
        for component in components:
            components_by_item.setdefault(component.quotation_item_id, []).append(component)

        def product(material_id):
            record = equipment.get(material_id)
            return record.product if record else None

        pdf_items = []
        for item in items:
            label = None
            model = item.model
            description = item.description
            if item.is_bundle:
                label, model = "Materiales varios", model or "M/V"
                description = ", ".join(
                    f"{format_quantity(component.quantity)} {name}"
                    for component in components_by_item.get(item.id_item, [])
                    for name in [product(component.material_id) or component.description]
                    if name
                )
            elif item.is_labor:
                label, model = "Mano de obra", model or "M/V"
            elif not item.is_new and item.material_id in equipment:
                model = equipment[item.material_id].model
                description = equipment[item.material_id].product

            quantity = item.quantity or 0
            pdf_items.append({
                "item_number": item.item_number,
                "model": model,
                "label": label,
                "description": description,
                "quantity": item.quantity,
                "price": (item.total or 0) / quantity if quantity else item.total,
                "total": item.total,
            })

        seller_attributes = (seller.attributes if seller else None) or {}
        content = generate_proforma_pdf({
            "quote_number": quotation.quote_number,
            "date": quotation.created_at,
            "ruc": company.identity if company else None,
            "client": company.company_name if company else None,
            "requested_by": inspection.contact if inspection else None,
            "project": inspection.title_ticket if inspection else None,
            "seller_name": seller_attributes.get("fullname") or quotation.created_by or "",
            "items": pdf_items,
            "subtotal": quotation.subtotal,
            "iva": quotation.iva,
            "total": quotation.total,
            "delivery_time": quotation.delivery_time,
            "payment_terms": quotation.payment_terms,
            "validity_days": quotation.validity_days,
        })
        return content, f"proforma_{quotation.quote_number or quotation.id_quote}.pdf"

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

    def assign_sales_user(self, body, internal, external):
        return self.internal_management_repository.assign_sales_user(
            body,
            internal,
            external,
        )

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

    def new_followup_financial(self, body, internal, external):
        return self.internal_management_repository.new_followup_financial(
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
        quotations_total = counts["quotations_approved"] + counts["quotations_rejected"] + counts["quotations_pending"]
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
                "pending": {
                    "count": counts["quotations_pending"],
                    "percentage": self._percentage(counts["quotations_pending"], quotations_total),
                }
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
                    "finished": row.finished_at is not None,
                    "finished_at": row.finished_at,
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

    def get_followup_financial(self, params, internal, external):
        filters = {
            "user": params.get("user"),
            "id_financial": params.get("id_financial"),
            "id_commercial": params.get("id_commercial"),
            "type": params.get("type")
        }

        rows = self.internal_management_repository.get_followup_financial(filters, internal, external)

        results = [
            {
                "id_followup": c.id_followup,
                "management_financial_id": c.management_financial_id,
                "management_commercial_id": c.management_commercial_id,
                "type": c.type,
                "observations": c.observations,
                "created_at": c.created_at,
                "created_by": c.created_by,
            }
            for c in rows
        ]

        return results

    # ------------------------------------------------------------------
    # Entrega de materiales (bodega)
    # ------------------------------------------------------------------

    @staticmethod
    def _quantity(value):
        """Cantidad de la proforma (Numeric) como número JSON: entero si no tiene decimales."""
        if value is None:
            return 0
        amount = float(value)
        return int(amount) if amount.is_integer() else amount

    @staticmethod
    def _required_int(value, field_name):
        if isinstance(value, bool):
            value = None
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if isinstance(value, str) and value.strip().isdigit():
            value = int(value.strip())
        if not isinstance(value, int):
            raise CustomAPIException(f"El campo {field_name} debe ser un número entero", 400)
        return value

    @staticmethod
    def _optional_text(value):
        if value is None:
            return None
        return str(value).strip() or None

    @staticmethod
    def _line_key_text(quotation_item_id, additional_material_id):
        # Clave estable de la línea de la proforma para el frontend
        if quotation_item_id is not None:
            return f"item-{quotation_item_id}"
        return f"additional-{additional_material_id}"

    def get_project_materials(self, id_task, internal, external):
        id_task = self._required_int(id_task, "id_task")
        data = self.internal_management_repository.get_project_materials(
            id_task, internal, external
        )
        equipment = data["equipment"]
        pendings = data["pendings"]
        delivered = data["delivered"]
        fullnames = data["fullnames"]
        line_key = InternalManagementRepository.line_key

        def material_row(quotation_item_id, additional_material_id, approved, material_id,
                         fallback_product, fallback_model, group, pending=None):
            record = equipment.get(material_id) if material_id else None
            delivered_quantity = delivered.get(line_key(quotation_item_id, additional_material_id), 0)
            approved_quantity = self._quantity(approved)
            return {
                "key": self._line_key_text(quotation_item_id, additional_material_id),
                "quotation_item_id": quotation_item_id,
                "additional_material_id": additional_material_id,
                "material_id": material_id,
                "product": (record.product if record else None) or fallback_product or "Material sin nombre",
                "model": (record.model if record else None) or fallback_model,
                "code": record.code if record else None,
                "unit": record.unit if record else None,
                "quantity": approved_quantity,
                "delivered": delivered_quantity,
                "pending": max(0, approved_quantity - delivered_quantity),
                # Sin producto en el catálogo no hay stock que controlar
                "stock": (record.stock or 0) if record else None,
                "is_new": pending is not None,
                "group": group,
                "pending_material": {
                    "id_pending_material": pending.id_pending_material,
                    "status": pending.status,
                    "name_material": pending.name_material,
                    "description": pending.description,
                    "model": pending.model,
                    "quantity": self._quantity(pending.quantity),
                    "base_price": self._amount(pending.base_price),
                    "profit_margin": self._amount(pending.profit_margin),
                    "profit_margin_dollar": self._amount(pending.profit_margin_dollar),
                } if pending is not None else None,
            }

        components_by_item = {}
        for component in data["components"]:
            components_by_item.setdefault(component.quotation_item_id, []).append(component)

        materials = []
        for item in data["items"]:
            if item.is_labor:
                continue
            if item.is_bundle:
                group = f"Materiales varios (ítem {item.item_number})"
                for component in components_by_item.get(item.id_item, []):
                    pending = (
                        pendings.get(line_key(None, component.id_extra))
                        if component.material_id is None else None
                    )
                    materials.append(material_row(
                        None, component.id_extra, component.quantity,
                        component.material_id or (pending.material_id if pending else None),
                        (pending.name_material if pending else None) or component.description,
                        (pending.model if pending else None) or component.model,
                        group,
                        pending,
                    ))
                continue

            pending = pendings.get(line_key(item.id_item, None)) if item.material_id is None else None
            materials.append(material_row(
                item.id_item, None, item.quantity,
                item.material_id or (pending.material_id if pending else None),
                (pending.name_material if pending else None) or item.description,
                (pending.model if pending else None) or item.model,
                None,
                pending,
            ))

        details_by_history = {}
        for detail in data["details"]:
            details_by_history.setdefault(detail.history_id, []).append(detail)

        deliveries = [
            {
                "id_delivery": history.id_history,
                "technician": history.delivered_to,
                "technician_name": fullnames.get(history.delivered_to) or history.delivered_to,
                "delivered_by": fullnames.get(history.created_by) or history.created_by,
                "created_at": history.created_at,
                "observations": history.observation,
                "status": history.status,
                "items": [
                    {
                        "key": self._line_key_text(detail.quotation_item_id, detail.additional_material_id),
                        "material_id": detail.material_id,
                        "pending_material_id": detail.pending_material_id,
                        "quantity": detail.quantity_delivered,
                    }
                    for detail in details_by_history.get(history.id_history, [])
                ],
            }
            for history in data["histories"]
        ]

        quotation = data["quotation"]
        return {
            "project_id": data["task"].id_task,
            "quote_id": quotation.id_quote,
            "proforma_code": quotation.quote_number,
            "technicians": [
                {"user": user, "fullname_user": fullnames.get(user) or user}
                for user in data["technicians"]
            ],
            "materials": materials,
            "deliveries": deliveries,
        }

    def post_material_delivery(self, body, internal, external):
        body = body or {}
        delivered_to = self._optional_text(body.get("delivered_to"))
        if not delivered_to:
            raise CustomAPIException("Seleccione el técnico que recibe los materiales", 400)

        entries = body.get("items")
        if not isinstance(entries, list) or not entries:
            raise CustomAPIException("Ingrese al menos un material a entregar", 400)

        items = []
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise CustomAPIException("Los materiales de la entrega no son válidos", 400)
            has_item = entry.get("quotation_item_id") is not None
            has_additional = entry.get("additional_material_id") is not None
            if has_item == has_additional:
                raise CustomAPIException(
                    "Cada material debe indicar quotation_item_id o additional_material_id",
                    400,
                )
            quotation_item_id = (
                self._required_int(entry["quotation_item_id"], "quotation_item_id")
                if has_item else None
            )
            additional_material_id = (
                self._required_int(entry["additional_material_id"], "additional_material_id")
                if has_additional else None
            )
            # Solo enteros: el stock del catálogo es entero
            quantity = entry.get("quantity")
            if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) \
                    or (isinstance(quantity, float) and not quantity.is_integer()):
                raise CustomAPIException("Las cantidades entregadas deben ser números enteros", 400)
            quantity = int(quantity)
            if quantity <= 0:
                raise CustomAPIException("Las cantidades entregadas deben ser mayores a cero", 400)

            key = (quotation_item_id, additional_material_id)
            if key in seen:
                raise CustomAPIException("Un material se repite en la entrega", 400)
            seen.add(key)
            items.append({
                "quotation_item_id": quotation_item_id,
                "additional_material_id": additional_material_id,
                "quantity": quantity,
            })

        return self.internal_management_repository.post_material_delivery(
            {
                "task_id": self._required_int(body.get("task_id"), "task_id"),
                "delivered_to": delivered_to,
                "observation": self._optional_text(body.get("observation")),
                "items": items,
                "user": body.get("user"),
            },
            internal,
            external,
        )

    def get_pending_materials(self, params, internal, external):
        rows = self.internal_management_repository.get_pending_materials(
            {
                "quote_id": self._optional_int(params.get("quote_id"), "quote_id"),
                "inspection_id": self._optional_int(params.get("inspection_id"), "inspection_id"),
                "status": params.get("status"),
            },
            internal,
            external,
        )
        return [
            {
                "id_pending_material": pending.id_pending_material,
                # Técnico: nació en el registro técnico; Proforma: lo agregó el comercial
                "origin": "Técnico" if pending.material_tech_ticket_id is not None else "Proforma",
                "inspection_id": pending.inspection_id,
                "inspection_code": inspection.code,
                "title_ticket": inspection.title_ticket,
                "client_name": inspection.client_name,
                "material_tech_ticket_id": pending.material_tech_ticket_id,
                "quote_id": pending.quote_id,
                "quote_number": quote_number,
                "quotation_item_id": pending.quotation_item_id,
                "additional_material_id": pending.additional_material_id,
                "name_material": pending.name_material,
                "description": pending.description,
                "model": pending.model,
                "quantity": self._quantity(pending.quantity),
                "base_price": self._amount(pending.base_price),
                "profit_margin": self._amount(pending.profit_margin),
                "profit_margin_dollar": self._amount(pending.profit_margin_dollar),
                "status": pending.status,
                "material_id": pending.material_id,
                "created_at": pending.created_at,
                "created_by": pending.created_by,
                "resolved_at": pending.resolved_at,
                "resolved_by": pending.resolved_by,
            }
            for pending, quote_number, inspection in rows
        ]

    def resolve_pending_material(self, id_pending_material, body, internal, external):
        body = body or {}
        product = self._optional_text(body.get("product"))
        if not product:
            raise CustomAPIException("El nombre del producto es obligatorio", 400)

        stock = body.get("stock")
        if isinstance(stock, bool) or not isinstance(stock, (int, float)) \
                or (isinstance(stock, float) and not stock.is_integer()) or stock < 0:
            raise CustomAPIException("El stock debe ser un número entero mayor o igual a cero", 400)

        provider_id = body.get("provider_id")
        return self.internal_management_repository.resolve_pending_material(
            self._required_int(id_pending_material, "id_pending_material"),
            {
                "product": product,
                "code": self._optional_text(body.get("code")),
                "model": self._optional_text(body.get("model")),
                "unit": self._optional_text(body.get("unit")),
                "description": self._optional_text(body.get("description")),
                "provider_id": (
                    self._required_int(provider_id, "provider_id")
                    if provider_id is not None else None
                ),
                "base_price": body.get("base_price"),
                "profit_margin": body.get("profit_margin"),
                "profit_margin_dollar": body.get("profit_margin_dollar"),
                "price": body.get("price"),
                "stock": int(stock),
                "user": body.get("user"),
            },
            internal,
            external,
        )