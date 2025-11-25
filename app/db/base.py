"""
Unified base models for database entities.

This module provides standardized base classes with common functionality
for all database models following SOLID principles.
"""

import uuid
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import Column, DateTime, Boolean, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class UUIDMixin:
    """Mixin to add UUID primary key to models."""
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )


class TimestampMixin:
    """Mixin to add timestamp fields to models."""
    
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Timestamp when record was created"
    )
    
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Timestamp when record was last updated"
    )


class SoftDeleteMixin:
    """Mixin to add soft delete functionality to models."""
    
    is_deleted = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Flag indicating if record is soft deleted"
    )
    
    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when record was soft deleted"
    )
    
    def soft_delete(self):
        """Mark record as deleted."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
    
    def restore(self):
        """Restore soft deleted record."""
        self.is_deleted = False
        self.deleted_at = None


class AuditMixin:
    """Mixin to add audit trail fields to models."""
    
    created_by = Column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID of user who created the record"
    )
    
    updated_by = Column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID of user who last updated the record"
    )
    
    version = Column(
        String(50),
        nullable=True,
        comment="Version of the record for optimistic locking"
    )


class MetadataMixin:
    """Mixin to add metadata storage to models."""
    
    metadata = Column(
        Text,
        nullable=True,
        comment="JSON metadata for additional model attributes"
    )
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata as dictionary."""
        import json
        if self.metadata:
            try:
                return json.loads(self.metadata)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    
    def set_metadata(self, data: Dict[str, Any]):
        """Set metadata from dictionary."""
        import json
        self.metadata = json.dumps(data) if data else None


class BaseModel(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, MetadataMixin):
    """
    Unified base model for all entities.
    
    This base class provides common functionality for all database models:
    - UUID primary key
    - Timestamps (created_at, updated_at)
    - Soft delete functionality
    - Audit trail (created_by, updated_by, version)
    - Metadata storage
    """
    
    __abstract__ = True
    
    # Add query helper methods
    @classmethod
    def active_query(cls, session):
        """Get query for active (non-deleted) records."""
        return session.query(cls).filter(cls.is_deleted == False)
    
    @classmethod
    def find_by_id(cls, session, record_id: uuid.UUID, include_deleted: bool = False):
        """Find record by ID, optionally including deleted records."""
        query = session.query(cls)
        if not include_deleted:
            query = query.filter(cls.is_deleted == False)
        return query.filter(cls.id == record_id).first()
    
    def to_dict(self, include_metadata: bool = True) -> Dict[str, Any]:
        """Convert model to dictionary."""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                result[column.name] = value.isoformat() if value else None
            elif isinstance(value, uuid.UUID):
                result[column.name] = str(value) if value else None
            else:
                result[column.name] = value
        
        if include_metadata and hasattr(self, 'get_metadata'):
            result['metadata_dict'] = self.get_metadata()
        
        return result
    
    def update_from_dict(self, data: Dict[str, Any], exclude_fields: list = None):
        """Update model from dictionary, excluding specified fields."""
        exclude_fields = exclude_fields or ['id', 'created_at', 'updated_at']
        
        for key, value in data.items():
            if key not in exclude_fields and hasattr(self, key):
                setattr(self, key, value)
    
    def __repr__(self) -> str:
        """String representation of model."""
        class_name = self.__class__.__name__
        if hasattr(self, 'id'):
            return f"<{class_name}(id={self.id})>"
        return f"<{class_name}>"