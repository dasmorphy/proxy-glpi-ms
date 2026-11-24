from sqlalchemy import Column, DateTime, ForeignKey, Integer, Sequence, Uuid, func

from swagger_server.models.db import Base


class TechStaffRecord(Base):
    """Personal técnico de un registro. Los registros de proyecto
    (technical-control-ms) usan record_id; los registros de campo de un
    Soporte / Asistencia usan inspection_id + management_technical_id."""

    __tablename__ = "tech_staff_record"
    __table_args__ = {"schema": "technical"}

    id_staff_record = Column(
        Integer,
        Sequence("tech_staff_record_id_seq", schema="technical"),
        primary_key=True,
        nullable=False,
    )

    record_id = Column(Integer, ForeignKey("technical.technical_record.id_record"))

    inspection_id = Column(
        Integer,
        ForeignKey("internal_management.inspection_technical.id_inspection"),
    )

    management_technical_id = Column(
        Integer,
        ForeignKey("internal_management.technical_ticket_management.id_management_technical"),
    )

    tech_staff_id = Column(Integer)

    user_tech_id = Column(Uuid)

    created_at = Column(DateTime, server_default=func.now())
