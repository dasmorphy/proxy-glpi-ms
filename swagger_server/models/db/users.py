import uuid
from sqlalchemy import (
    Column,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from swagger_server.models.db import Base


class Users(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "public"}

    id_user = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )

    user = Column(Text, nullable=False)
    email = Column(Text, nullable=True)
    password = Column(Text, nullable=False)
    platform = Column(Text)

    role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("public.roles.id_rol", onupdate="NO ACTION", ondelete="NO ACTION"),
        nullable=False
    )

    attributes = Column(JSONB, nullable=True)

    is_active = Column(Boolean, default=True)

    created_at = Column(
        DateTime(timezone=False),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now()
    )