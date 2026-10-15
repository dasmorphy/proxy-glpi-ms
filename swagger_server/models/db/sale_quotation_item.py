from sqlalchemy import (
    Column,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    DateTime,
    Sequence,
    func
)
from swagger_server.models.db import Base


class SaleQuotationItem(Base):
    __tablename__ = "sale_quotation_item"
    __table_args__ = {"schema": "internal_management"}

    id_item = Column(
        Integer,
        Sequence("sales_quotation_item_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False
    )

    sale_quote_id = Column(
        Integer,
        ForeignKey("internal_management.sale_quotation.id_quote")
    )

    material_id = Column(
        Integer,
        ForeignKey("technical.technical_equipment.id_equipment")
    )

    item_number = Column(Integer)
    is_labor = Column(Boolean)
    is_bundle = Column(Boolean)
    is_new = Column(Boolean)
    description = Column(Text)
    model = Column(Text)
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
