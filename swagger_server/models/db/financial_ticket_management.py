from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, Sequence, Text, func

from swagger_server.models.db import Base


class FinancialTicketManagement(Base):
    __tablename__ = "financial_ticket_management"
    __table_args__ = {"schema": "internal_management"}

    id_management_financial = Column(
        Integer,
        Sequence(
            "financial_ticket_management_id_seq",
            schema="internal_management",
        ),
        primary_key=True,
        nullable=False,
    )

    ticket_id = Column(
        Integer,
        ForeignKey(
            "internal_management.inspection_technical.id_inspection",
            onupdate="NO ACTION",
            ondelete="NO ACTION",
        ),
    )
    
    code_management = Column(Text)
    type_management = Column(Text)
    number_document = Column(Text)
    

    amount_pending = Column(Numeric(12, 2))
    amount_paid = Column(Numeric(12, 2))
    invoice_price = Column(Numeric(12, 2))

    observations = Column(Text)
    status = Column(Text)
    date_document = Column(DateTime)

    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Text)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Text)
