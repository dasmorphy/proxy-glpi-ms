from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, Sequence, Text, func

from swagger_server.models.db import Base


class PendingMaterial(Base):
    """Producto nuevo que aún no existe en el catálogo. Nace en el registro
    técnico (material_tech_ticket_id) o en la proforma aprobada
    (quotation_item_id); el del técnico se vincula a la proforma al aprobarse."""

    __tablename__ = "pending_material"
    __table_args__ = {"schema": "internal_management"}

    STATUS_PENDING = "Pendiente"
    STATUS_CREATED = "Creado"
    # Producto del técnico que el comercial quitó de la proforma
    STATUS_REMOVED = "Eliminado de proforma"

    id_pending_material = Column(
        Integer,
        Sequence("pending_material_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False,
    )

    inspection_id = Column(
        Integer,
        ForeignKey("internal_management.inspection_technical.id_inspection"),
        nullable=False,
    )

    material_tech_ticket_id = Column(
        Integer,
        ForeignKey("internal_management.material_tech_ticket.id_material"),
        unique=True,
    )

    # Nulos mientras el pendiente del técnico no se vincule a una proforma aprobada
    quote_id = Column(
        Integer,
        ForeignKey("internal_management.sale_quotation.id_quote"),
    )

    quotation_item_id = Column(
        Integer,
        ForeignKey("internal_management.sale_quotation_item.id_item"),
        unique=True,
    )

    name_material = Column(Text)
    description = Column(Text)
    model = Column(Text)
    quantity = Column(Numeric(15, 2))
    base_price = Column(Numeric(15, 2))
    profit_margin = Column(Numeric(15, 2))
    profit_margin_dollar = Column(Numeric(15, 2))
    status = Column(Text, nullable=False, default=STATUS_PENDING)

    material_id = Column(
        Integer,
        ForeignKey("technical.technical_equipment.id_equipment"),
    )

    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Text)
    resolved_at = Column(DateTime)
    resolved_by = Column(Text)
