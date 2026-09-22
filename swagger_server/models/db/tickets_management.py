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


class TicketsManagement(Base):
    __tablename__ = 'tickets_management'
    __table_args__ = {'schema': 'internal_management'}

    id_ticket = Column(
        Integer,
        Sequence("tickets_management_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False
    )

    ticket_glpi = Column(Integer)
    management_area = Column(Text)
    next_area = Column(Text)
    title_ticket = Column(Text)
    status = Column(Text)
    contact = Column(Text)
    client_id = Column(Integer)
    ubication_id = Column(Integer)
    client_name = Column(Text)
    ubication_name = Column(Text)
    priority = Column(Text)
    responsible_ticket = Column(Text)

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