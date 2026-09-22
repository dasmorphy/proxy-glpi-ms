from swagger_server.models.db import Base
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    Sequence,
    String,
    Text,
    Time,
    ForeignKey,
    func
)


class TechnicalTicketManagement(Base):
    __tablename__ = 'technical_ticket_management'
    __table_args__ = {'schema': 'internal_management'}

    id_management_technical = Column(
        Integer,
        Sequence("technical_ticket_management_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False
    )

    ticket_id = Column(
        Integer,
        ForeignKey('internal_management.tickets_management.id_ticket', onupdate='NO ACTION', ondelete='NO ACTION'),
    )

    code_management = Column(Text)
    case_type = Column(Text)
    management_status = Column(Text)
    next_action = Column(Text)
    observations = Column(Text)
    requires_material = Column(Boolean)
    requires_monitoring = Column(Boolean)
    status = Column(Text)
    created_by = Column(Text)
    updated_by = Column(Text)
    commitment_date = Column(DateTime)

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )








