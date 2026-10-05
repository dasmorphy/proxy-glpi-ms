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

class MaterialTechTicket(Base):
    __tablename__ = "material_tech_ticket"
    __table_args__ = {"schema": "internal_management"}

    id_material = Column(
        Integer,
        Sequence("material_tech_ticket_id_seq", schema="internal_management"),
        primary_key=True,
        nullable=False
    )

    tech_ticket = Column(
        Integer,
        ForeignKey("internal_management.technical_ticket_management.id_management_technical")
    )

    material_id = Column(
        Integer,
        ForeignKey("technical.technical_equipment.id_equipment")
    )

    material_description = Column(Text)
    other = Column(Text)
    quantity = Column(Integer)


    created_at = Column(
        DateTime,
        server_default=func.now()
    )
