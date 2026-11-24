from sqlalchemy import Column, DateTime, ForeignKey, Integer, Sequence, Text, func

from swagger_server.models.db import Base


class TechRecordImage(Base):
    """Imágenes de un registro técnico (las guarda technical-control-ms; aquí
    solo se leen para el detalle del registro de un Soporte / Asistencia)."""

    __tablename__ = "tech_record_image"
    __table_args__ = {"schema": "technical"}

    id_image = Column(
        Integer,
        Sequence("tech_record_image_id_seq", schema="technical"),
        primary_key=True,
        nullable=False,
    )

    record_id = Column(
        Integer,
        ForeignKey("technical.technical_record.id_record"),
    )

    image_path = Column(Text)

    created_at = Column(DateTime, server_default=func.now())
