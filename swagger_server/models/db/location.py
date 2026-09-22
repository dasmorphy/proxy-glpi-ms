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


class ClientLocation(Base):
    __tablename__ = "clients_location"
    __table_args__ = {"schema": "technical"}

    id_location = Column(
        Integer,
        Sequence("clients_location_id_seq", schema="technical"),
        primary_key=True,
        nullable=False
    )

    client_id = Column(
        Integer,
        ForeignKey("technical.clients.id_client")
    )

    name = Column(
        Text,
    )

    address = Column(
        Text,
    )

    long = Column(
        Text,
    )

    lat = Column(
        Text,
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
