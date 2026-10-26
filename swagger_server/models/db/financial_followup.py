from sqlalchemy import Column, DateTime, ForeignKey, Integer, Sequence, Text, func

from swagger_server.models.db import Base


class FinancialFollowup(Base):
    __tablename__ = "financial_followup"
    __table_args__ = {"schema": "internal_management"}

    id_followup = Column(
        Integer,
        Sequence("financial_followup_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False,
    )

    management_financial_id = Column(
        Integer,
        ForeignKey(
            "internal_management.financial_ticket_management.id_management_financial",
            onupdate="NO ACTION",
            ondelete="NO ACTION",
        ),
    )

    # Solo para type 'Pendiente': gestión comercial aún sin gestión financiera
    management_commercial_id = Column(
        Integer,
        ForeignKey(
            "internal_management.commercial_ticket_management.id_management_commercial",
            onupdate="NO ACTION",
            ondelete="NO ACTION",
        ),
    )

    observations = Column(Text)
    # 'Pendiente' o 'Registrado'
    type = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Text)
