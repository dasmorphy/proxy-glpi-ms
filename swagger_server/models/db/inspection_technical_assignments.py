from sqlalchemy import Column, DateTime, ForeignKey, Integer, Sequence, Text, Uuid, func

from swagger_server.models.db import Base


class InspectionTechnicalAssignment(Base):
    """Personal técnico de un Soporte / Asistencia (equivalente a
    technical.task_technical_assignments de un proyecto). user_id es
    public.users.id_user."""

    __tablename__ = "inspection_technical_assignments"
    __table_args__ = {"schema": "internal_management"}

    id_assignment = Column(
        Integer,
        Sequence("inspection_technical_assignments_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False,
    )

    inspection_id = Column(
        Integer,
        ForeignKey("internal_management.inspection_technical.id_inspection"),
        nullable=False,
    )

    user_id = Column(Uuid, nullable=False)

    created_by = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
