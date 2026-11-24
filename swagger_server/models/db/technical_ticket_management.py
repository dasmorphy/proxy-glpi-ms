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

    # Una inspección tiene una gestión técnica (web) y puede tener varios
    # registros de campo (app, is_field_record = true)
    inspection_id = Column(
        Integer,
        ForeignKey('internal_management.inspection_technical.id_inspection', onupdate='NO ACTION', ondelete='NO ACTION'),
    )

    code_management = Column(Text)
    description = Column(Text)
    status = Column(Text)
    vehicle = Column(Text)
    # Completado / Incompleto del registro de campo (status es el del flujo)
    record_status = Column(Text)
    is_field_record = Column(Boolean, nullable=False, server_default="false", default=False)
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








