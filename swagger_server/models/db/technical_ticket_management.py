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

    inspection_id = Column(
        Integer,
        ForeignKey('internal_management.inspection_technical.id_inspection', onupdate='NO ACTION', ondelete='NO ACTION'),
        unique=True,
    )

    code_management = Column(Text)
    description = Column(Text)
    status = Column(Text)
    created_by = Column(Text)
    updated_by = Column(Text)

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )








