from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    DateTime,
    Sequence,
    func
)
from swagger_server.models.db import Base


class SaleAdditionalMaterials(Base):
    __tablename__ = "sale_additional_materials"
    __table_args__ = {"schema": "internal_management"}

    id_extra = Column(
        Integer,
        Sequence("sale_additional_materials_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False
    )

    sale_quote_id = Column(
        Integer,
        ForeignKey("internal_management.sale_quotation.id_quote")
    )

    # Ítem bundle de la proforma al que pertenece el material
    quotation_item_id = Column(
        Integer,
        ForeignKey("internal_management.sale_quotation_item.id_item")
    )

    material_id = Column(
        Integer,
        ForeignKey("technical.technical_equipment.id_equipment")
    )

    base_price = Column(Numeric(15, 2))
    profit_margin = Column(Numeric(15, 2))
    profit_margin_dollar = Column(Numeric(15, 2))
    quantity = Column(Numeric(15, 2))
    total = Column(Numeric(15, 2))

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )

    created_by = Column(Text)
    updated_by = Column(Text)
