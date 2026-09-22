from sqlalchemy import Column, DateTime, ForeignKey, Integer, Sequence, Text, func

from swagger_server.models.db import Base


class CommercialFollowup(Base):
    __tablename__ = "commercial_followup"
    __table_args__ = {"schema": "internal_management"}

    id_followup = Column(
        Integer,
        Sequence("commercial_followup_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False,
    )

    management_commercial_id = Column(
        Integer,
        ForeignKey(
            "internal_management.commercial_ticket_management.id_management_commercial",
            onupdate="NO ACTION",
            ondelete="NO ACTION",
        ),
    )

    observations = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Text)
