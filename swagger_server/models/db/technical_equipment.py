from sqlalchemy import (
    Column,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    DateTime,
    Sequence,
    func
)
from swagger_server.models.db import Base


class TechnicalEquipment(Base):
    __tablename__ = "technical_equipment"
    __table_args__ = {"schema": "technical"}

    id_equipment = Column(
        Integer,
        Sequence("technical_equipment_id_seq", schema="technical"),
        primary_key=True,
        nullable=False
    )

    code = Column(Text)
    product = Column(Text)
    unit = Column(Text)
    model = Column(Text)

    base_price = Column(Numeric(12, 2))
    profit_margin = Column(Numeric(12, 2))
    profit_margin_dollar = Column(Numeric(12, 2))
    price = Column(Numeric(12, 2))

    provider = Column(Text)
    description = Column(Text)
    stock = Column(Integer)
    

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
