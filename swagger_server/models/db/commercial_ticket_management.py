from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, Sequence, Text, func

from swagger_server.models.db import Base


class CommercialTicketManagement(Base):
    __tablename__ = "commercial_ticket_management"
    __table_args__ = {"schema": "internal_management"}

    id_management_commercial = Column(
        Integer,
        Sequence(
            "commercial_ticket_management_id_seq",
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
    assigned_user = Column(Text)
    code_management = Column(Text)
    origin_id = Column(
        Integer,
        ForeignKey("internal_management.commercial_origin.id_origin"),
    )
    type_solution_id = Column(
        Integer,
        ForeignKey("internal_management.commercial_type_solution.id_solution"),
    )
    quoted_amount = Column(Numeric(12, 2))
    probability_closing = Column(Integer)
    closing_date = Column(DateTime)
    next_action = Column(Text)
    responsible_next_action = Column(Text)
    requires_technical = Column(Boolean)
    requires_material = Column(Boolean)
    scheduled_start_date = Column(DateTime)
    contract_received = Column(Boolean)
    date_finish = Column(DateTime)
    reason_loss = Column(Text)
    observations = Column(Text)
    status_id = Column(
        Integer,
        ForeignKey("internal_management.commmercial_ticket_status.id_status"),
    )
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Text)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Text)
