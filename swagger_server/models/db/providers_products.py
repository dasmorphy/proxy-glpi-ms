from swagger_server.models.db import Base
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    Sequence,
    String,
    Text,
    Time,
    ForeignKey,
    Uuid,
    func
)


class ProvidersProducts(Base):
    __tablename__ = 'providers_products'
    __table_args__ = {'schema': 'internal_management'}

    id_provider = Column(
        Integer,
        Sequence("providers_products_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False
    )

    ruc = Column(Text)
    provider = Column(Text)
    address = Column(Text)
    seller = Column(Text)
    number_contact = Column(Text)
    email = Column(DateTime)
    status = Column(Text)
    
    created_by = Column(Text)    
    created_at = Column(
        DateTime,
        server_default=func.now()
    )