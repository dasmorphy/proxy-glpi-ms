from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Sequence,
    Text,
    func
)
from swagger_server.models.db import Base


class SaleQuotation(Base):
    __tablename__ = "sale_quotation"
    __table_args__ = {"schema": "internal_management"}

    id_quote = Column(
        Integer,
        Sequence("sale_quotation_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False
    )

    inspection_id = Column(
        Integer,
        ForeignKey("internal_management.inspection_technical.id_inspection")
    )

    client_company = Column(
        Integer,
        ForeignKey("technical.client_companies.id_company")
    )

    iva = Column(Numeric(15, 2))
    iva_rate = Column(Numeric(15, 2))
    subtotal = Column(Numeric(15, 2))
    total = Column(Numeric(15, 2))

    quote_number = Column(Text)
    delivery_time = Column(Text)
    payment_terms = Column(Text)
    validity_days = Column(Integer)

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
