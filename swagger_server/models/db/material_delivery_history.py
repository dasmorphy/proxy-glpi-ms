from sqlalchemy import Column, DateTime, ForeignKey, Integer, Sequence, Text, func

from swagger_server.models.db import Base


class MaterialDeliveryHistory(Base):
    """Cabecera de una entrega de materiales de bodega a un técnico del proyecto."""

    __tablename__ = "material_delivery_history"
    __table_args__ = {"schema": "internal_management"}

    STATUS_REGISTERED = "Registrada"

    id_history = Column(
        Integer,
        Sequence("material_delivery_history_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False,
    )

    task_id = Column(
        Integer,
        ForeignKey("technical.task_technical.id_task"),
        nullable=False,
    )

    quote_id = Column(
        Integer,
        ForeignKey("internal_management.sale_quotation.id_quote"),
        nullable=False,
    )

    delivered_to = Column(Text, nullable=False)
    observation = Column(Text)
    status = Column(Text, nullable=False, default=STATUS_REGISTERED)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Text)
