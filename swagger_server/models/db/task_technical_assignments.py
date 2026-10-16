from sqlalchemy import Column, DateTime, ForeignKey, Integer, Sequence, Text, func

from swagger_server.models.db import Base


class TaskTechnicalAssignment(Base):
    __tablename__ = "task_technical_assignments"
    __table_args__ = {"schema": "technical"}

    id_assignment = Column(
        Integer,
        Sequence("task_technical_assignments_id_seq", schema="technical"),
        primary_key=True,
        nullable=False,
    )

    task_id = Column(
        Integer,
        ForeignKey("technical.task_technical.id_task"),
    )

    user = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
