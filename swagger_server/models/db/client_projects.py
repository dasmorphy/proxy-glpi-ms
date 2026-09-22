from sqlalchemy import (
    Column,
    Boolean,
    Integer,
    Text,
    DateTime,
    Sequence,
    func
)
from swagger_server.models.db import Base


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = {"schema": "technical"}

    id_client = Column(
        Integer,
        Sequence("clients_id_seq", schema="technical"),
        primary_key=True,
        nullable=False
    )

    name = Column(
        Text,
        nullable=False
    )

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
