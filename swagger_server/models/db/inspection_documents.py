from swagger_server.models.db import Base
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    Time,
    ForeignKey,
    func
)


class InspectionDocuments(Base):
    __tablename__ = 'inspection_documents'
    __table_args__ = {'schema': 'internal_management'}

    id_document = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    inspection_id = Column(
        Integer,
        ForeignKey('internal_management.inspection_technical.id_inspection', onupdate='NO ACTION', ondelete='NO ACTION'),
    )

    document_path = Column(Text)
    name_document = Column(Text)
    type_document = Column(Text)

    created_at = Column(
        DateTime,
        server_default=func.now()
    )
