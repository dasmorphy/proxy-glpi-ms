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


class ClientCompany(Base):
    __tablename__ = "client_companies"
    __table_args__ = {"schema": "technical"}

    id_company = Column(
        Integer,
        Sequence("client_companies_id_seq", schema="technical"),
        primary_key=True,
        nullable=False
    )

    type_document = Column(
        Text,
    )

    company_name = Column(
        Text,
    )

    identity = Column(
        Text,
    )

    created_by = Column(Text)

    created_at = Column(
        DateTime,
        server_default=func.now()
    )
