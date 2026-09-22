from sqlalchemy import Column, DateTime, Integer, Sequence, Text, func

from swagger_server.models.db import Base


class CommercialTicketStatus(Base):
    # El nombre de tabla conserva la grafia existente en scripts.sql.
    __tablename__ = "commmercial_ticket_status"
    __table_args__ = {"schema": "internal_management"}

    id_status = Column(
        Integer,
        Sequence(
            "commmercial_ticket_status_id_seq",
            schema="internal_management",
        ),
        primary_key=True,
        nullable=False,
    )
    name = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Text)
