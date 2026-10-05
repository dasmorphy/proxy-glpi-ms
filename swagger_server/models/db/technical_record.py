from sqlalchemy import (
    Column,
    Boolean,
    ForeignKey,
    Integer,
    Text,
    DateTime,
    Sequence,
    func
)
from swagger_server.models.db import Base


class TechnicalRecord(Base):
    __tablename__ = "technical_record"
    __table_args__ = {"schema": "technical"}

    id_record = Column(
        Integer,
        Sequence("technical_record_id_seq", schema="technical"),
        primary_key=True,
        nullable=False
    )

    task_id = Column(
        Integer,
        ForeignKey("technical.task_technical.id_task")
    )

    client_id = Column(
        Integer,
        ForeignKey("technical.clients.id_client")
    )

    location_id = Column(
        Integer,
        ForeignKey("technical.clients_location.id_location")
    )

    resume = Column(Text)
    vehicle = Column(Text)
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
