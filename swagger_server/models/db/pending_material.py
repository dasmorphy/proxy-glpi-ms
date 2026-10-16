from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, Sequence, Text, func

from swagger_server.models.db import Base


class PendingMaterial(Base):
    """Producto nuevo de una proforma aprobada que aún no existe en el catálogo."""

    __tablename__ = "pending_material"
    __table_args__ = {"schema": "internal_management"}

    STATUS_PENDING = "Pendiente"
    STATUS_CREATED = "Creado"

    id_pending_material = Column(
        Integer,
        Sequence("pending_material_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False,
    )

    quote_id = Column(
        Integer,
        ForeignKey("internal_management.sale_quotation.id_quote"),
        nullable=False,
    )

    quotation_item_id = Column(
        Integer,
        ForeignKey("internal_management.sale_quotation_item.id_item"),
        nullable=False,
        unique=True,
    )

    name_material = Column(Text)
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
