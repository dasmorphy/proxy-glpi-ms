from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, Sequence, func

from swagger_server.models.db import Base


class MaterialDeliveryDetail(Base):
    """Material entregado en una entrega. Referencia la línea de la proforma
    (ítem o componente de "Materiales varios") y el producto del catálogo, o el
    pendiente mientras el producto no exista."""

    __tablename__ = "material_delivery_detail"
    __table_args__ = {"schema": "internal_management"}

    id_delivery_material = Column(
        Integer,
        Sequence("material_delivery_detail_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False,
    )

    history_id = Column(
        Integer,
        ForeignKey("internal_management.material_delivery_history.id_history"),
        nullable=False,
    )

    quotation_item_id = Column(
        Integer,
        ForeignKey("internal_management.sale_quotation_item.id_item"),
    )

    additional_material_id = Column(
        Integer,
        ForeignKey("internal_management.sale_additional_materials.id_extra"),
    )

    material_id = Column(
        Integer,
        ForeignKey("technical.technical_equipment.id_equipment"),
    )

    pending_material_id = Column(
        Integer,
        ForeignKey("internal_management.pending_material.id_pending_material"),
    )

    quantity_delivered = Column(Integer, nullable=False)
    quantity_remaining = Column(Numeric(15, 2))
    created_at = Column(DateTime, server_default=func.now())
