from sqlalchemy import Column, DateTime, Integer, Sequence, Text, func

from swagger_server.models.db import Base


class CommercialTypeSolution(Base):
    __tablename__ = "commercial_type_solution"
    __table_args__ = {"schema": "internal_management"}

    id_solution = Column(
        Integer,
        Sequence(
            "commercial_type_solution_id_seq",
            schema="internal_management",
        ),
        primary_key=True,
        nullable=False,
    )
    name = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Text)
