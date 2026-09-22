from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, Sequence, Text, func

from swagger_server.models.db import Base


class HistoryAreaTicket(Base):
    __tablename__ = "history_area_ticket"
    __table_args__ = {"schema": "internal_management"}

    id_history = Column(
        Integer,
        Sequence(
            "history_area_ticket_id_seq",
            schema="internal_management",
        ),
        primary_key=True,
        nullable=False,
    )

    ticket_id = Column(
        Integer,
        ForeignKey(
            "internal_management.tickets_management.id_ticket",
            onupdate="NO ACTION",
            ondelete="NO ACTION",
        ),
    )

    previous_area = Column(Text)
    current_area = Column(Text)
    
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Text)