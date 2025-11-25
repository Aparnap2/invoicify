"""
Base service class for consistent service patterns and operations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, TypeVar, Union
from datetime import datetime
import uuid
from sqlalchemy.orm import Session

from app.db.base import BaseModel
from app.utils.logging_utils import LoggingUtils, StructuredLogger
from app.utils.validation_utils import ValidationUtils
from app.core.exceptions import APIntakeException

T = TypeVar('T', bound=BaseModel)


class BaseService(ABC):
    """Base service class with common functionality for all services."""
    
    def __init__(self, db: Session, logger_name: Optional[str] = None):
        self.db = db
        self.logger = LoggingUtils.get_logger(logger_name or self.__class__.__name__)
        self.model_class = self.get_model_class()
    
    @abstractmethod
    def get_model_class(self) -> Type[T]:
        """Return the model class this service manages."""
        pass
    
    # CRUD operations
    def get_by_id(self, record_id: Union[str, uuid.UUID], 
                  include_deleted: bool = False) -> Optional[T]:
        """Get record by ID."""
        try:
            if isinstance(record_id, str):
                record_id = uuid.UUID(record_id)
            
            record = self.model_class.find_by_id(self.db, record_id, include_deleted)
            
            if record:
                self.logger.debug(f"Retrieved {self.model_class.__name__} by ID",
                               record_id=str(record_id))
            
            return record
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve {self.model_class.__name__} by ID",
                           error=e, record_id=str(record_id))
            raise APIntakeException(f"Failed to retrieve record: {str(e)}")
    
    def get_all(self, include_deleted: bool = False) -> List[T]:
        """Get all records."""
        try:
            query = self.db.query(self.model_class)
            if not include_deleted:
                query = query.filter(self.model_class.is_deleted == False)
            
            records = query.all()
            
            self.logger.debug(f"Retrieved {len(records)} {self.model_class.__name__} records")
            return records
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve {self.model_class.__name__} records", error=e)
            raise APIntakeException(f"Failed to retrieve records: {str(e)}")
    
    def create(self, data: Dict[str, Any], user_id: Optional[uuid.UUID] = None) -> T:
        """Create new record."""
        try:
            # Validate data
            self._validate_create_data(data)
            
            # Add audit fields
            if user_id:
                data['created_by'] = user_id
            
            record = self.model_class(**data)
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            
            self.logger.info(f"Created {self.model_class.__name__}",
                          action='create',
                          resource_type=self.model_class.__name__,
                          resource_id=str(record.id),
                          user_id=str(user_id) if user_id else None)
            
            return record
            
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Failed to create {self.model_class.__name__}",
                           error=e, data=data)
            raise APIntakeException(f"Failed to create record: {str(e)}")
    
    def update(self, record_id: Union[str, uuid.UUID], data: Dict[str, Any],
               user_id: Optional[uuid.UUID] = None) -> T:
        """Update existing record."""
        try:
            # Get record
            record = self.get_by_id(record_id)
            if not record:
                raise APIntakeException(f"{self.model_class.__name__} not found")
            
            # Validate data
            self._validate_update_data(data, record)
            
            # Add audit fields
            if user_id:
                data['updated_by'] = user_id
            
            # Update record
            for key, value in data.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            
            self.db.commit()
            self.db.refresh(record)
            
            self.logger.info(f"Updated {self.model_class.__name__}",
                          action='update',
                          resource_type=self.model_class.__name__,
                          resource_id=str(record.id),
                          user_id=str(user_id) if user_id else None,
                          changes=data)
            
            return record
            
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Failed to update {self.model_class.__name__}",
                           error=e, record_id=str(record_id), data=data)
            raise APIntakeException(f"Failed to update record: {str(e)}")
    
    def delete(self, record_id: Union[str, uuid.UUID], 
               user_id: Optional[uuid.UUID] = None, 
               soft_delete: bool = True) -> bool:
        """Delete record (soft delete by default)."""
        try:
            record = self.get_by_id(record_id)
            if not record:
                raise APIntakeException(f"{self.model_class.__name__} not found")
            
            if soft_delete:
                record.soft_delete()
                action = 'soft_delete'
            else:
                self.db.delete(record)
                action = 'hard_delete'
            
            self.db.commit()
            
            self.logger.info(f"{action.replace('_', ' ').title()} {self.model_class.__name__}",
                          action=action,
                          resource_type=self.model_class.__name__,
                          resource_id=str(record.id),
                          user_id=str(user_id) if user_id else None)
            
            return True
            
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Failed to delete {self.model_class.__name__}",
                           error=e, record_id=str(record_id))
            raise APIntakeException(f"Failed to delete record: {str(e)}")
    
    def restore(self, record_id: Union[str, uuid.UUID],
               user_id: Optional[uuid.UUID] = None) -> T:
        """Restore soft deleted record."""
        try:
            record = self.get_by_id(record_id, include_deleted=True)
            if not record or not record.is_deleted:
                raise APIntakeException(f"{self.model_class.__name__} not found or not deleted")
            
            record.restore()
            self.db.commit()
            self.db.refresh(record)
            
            self.logger.info(f"Restored {self.model_class.__name__}",
                          action='restore',
                          resource_type=self.model_class.__name__,
                          resource_id=str(record.id),
                          user_id=str(user_id) if user_id else None)
            
            return record
            
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Failed to restore {self.model_class.__name__}",
                           error=e, record_id=str(record_id))
            raise APIntakeException(f"Failed to restore record: {str(e)}")
    
    # Query operations
    def find_by_filters(self, filters: Dict[str, Any], 
                       include_deleted: bool = False) -> List[T]:
        """Find records by filters."""
        try:
            query = self.db.query(self.model_class)
            
            if not include_deleted:
                query = query.filter(self.model_class.is_deleted == False)
            
            # Apply filters
            for field, value in filters.items():
                if hasattr(self.model_class, field) and value is not None:
                    column = getattr(self.model_class, field)
                    
                    if isinstance(value, dict):
                        # Handle complex filters
                        if 'eq' in value:
                            query = query.filter(column == value['eq'])
                        elif 'ne' in value:
                            query = query.filter(column != value['ne'])
                        elif 'gt' in value:
                            query = query.filter(column > value['gt'])
                        elif 'gte' in value:
                            query = query.filter(column >= value['gte'])
                        elif 'lt' in value:
                            query = query.filter(column < value['lt'])
                        elif 'lte' in value:
                            query = query.filter(column <= value['lte'])
                        elif 'in' in value:
                            query = query.filter(column.in_(value['in']))
                        elif 'like' in value:
                            query = query.filter(column.like(f"%{value['like']}%"))
                        elif 'ilike' in value:
                            query = query.filter(column.ilike(f"%{value['ilike']}%"))
                    elif isinstance(value, list):
                        query = query.filter(column.in_(value))
                    else:
                        query = query.filter(column == value)
            
            records = query.all()
            
            self.logger.debug(f"Found {len(records)} {self.model_class.__name__} records with filters",
                           filters=filters)
            
            return records
            
        except Exception as e:
            self.logger.error(f"Failed to find {self.model_class.__name__} by filters",
                           error=e, filters=filters)
            raise APIntakeException(f"Failed to find records: {str(e)}")
    
    def search(self, search_term: str, search_fields: List[str],
               include_deleted: bool = False) -> List[T]:
        """Search records across multiple fields."""
        try:
            query = self.db.query(self.model_class)
            
            if not include_deleted:
                query = query.filter(self.model_class.is_deleted == False)
            
            # Build search conditions
            from sqlalchemy import or_
            search_conditions = []
            
            for field in search_fields:
                if hasattr(self.model_class, field):
                    column = getattr(self.model_class, field)
                    search_conditions.append(column.ilike(f"%{search_term}%"))
            
            if search_conditions:
                query = query.filter(or_(*search_conditions))
            
            records = query.all()
            
            self.logger.debug(f"Search found {len(records)} {self.model_class.__name__} records",
                           search_term=search_term, search_fields=search_fields)
            
            return records
            
        except Exception as e:
            self.logger.error(f"Failed to search {self.model_class.__name__} records",
                           error=e, search_term=search_term, search_fields=search_fields)
            raise APIntakeException(f"Failed to search records: {str(e)}")
    
    # Bulk operations
    def bulk_create(self, items: List[Dict[str, Any]],
                   user_id: Optional[uuid.UUID] = None) -> List[T]:
        """Bulk create records."""
        try:
            records = []
            
            for item_data in items:
                # Validate data
                self._validate_create_data(item_data)
                
                # Add audit fields
                if user_id:
                    item_data['created_by'] = user_id
                
                record = self.model_class(**item_data)
                records.append(record)
                self.db.add(record)
            
            self.db.commit()
            
            # Refresh all records
            for record in records:
                self.db.refresh(record)
            
            self.logger.info(f"Bulk created {len(records)} {self.model_class.__name__} records",
                          action='bulk_create',
                          resource_type=self.model_class.__name__,
                          user_id=str(user_id) if user_id else None,
                          count=len(records))
            
            return records
            
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Failed to bulk create {self.model_class.__name__} records",
                           error=e, items_count=len(items))
            raise APIntakeException(f"Failed to bulk create records: {str(e)}")
    
    def bulk_update(self, updates: List[Dict[str, Any]],
                   user_id: Optional[uuid.UUID] = None) -> int:
        """Bulk update records."""
        try:
            updated_count = 0
            
            for update_data in updates:
                if 'id' not in update_data:
                    continue
                
                record_id = update_data.pop('id')
                record = self.get_by_id(record_id)
                
                if record:
                    # Validate data
                    self._validate_update_data(update_data, record)
                    
                    # Add audit fields
                    if user_id:
                        update_data['updated_by'] = user_id
                    
                    # Update record
                    for key, value in update_data.items():
                        if hasattr(record, key):
                            setattr(record, key, value)
                    
                    updated_count += 1
            
            self.db.commit()
            
            self.logger.info(f"Bulk updated {updated_count} {self.model_class.__name__} records",
                          action='bulk_update',
                          resource_type=self.model_class.__name__,
                          user_id=str(user_id) if user_id else None,
                          count=updated_count)
            
            return updated_count
            
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Failed to bulk update {self.model_class.__name__} records",
                           error=e, updates_count=len(updates))
            raise APIntakeException(f"Failed to bulk update records: {str(e)}")
    
    # Validation methods (to be overridden by subclasses)
    def _validate_create_data(self, data: Dict[str, Any]) -> None:
        """Validate data for create operation."""
        pass
    
    def _validate_update_data(self, data: Dict[str, Any], record: T) -> None:
        """Validate data for update operation."""
        pass
    
    # Utility methods
    def count(self, include_deleted: bool = False) -> int:
        """Count total records."""
        try:
            query = self.db.query(self.model_class)
            
            if not include_deleted:
                query = query.filter(self.model_class.is_deleted == False)
            
            count = query.count()
            
            self.logger.debug(f"Counted {count} {self.model_class.__name__} records")
            
            return count
            
        except Exception as e:
            self.logger.error(f"Failed to count {self.model_class.__name__} records", error=e)
            raise APIntakeException(f"Failed to count records: {str(e)}")
    
    def exists(self, record_id: Union[str, uuid.UUID],
              include_deleted: bool = False) -> bool:
        """Check if record exists."""
        try:
            if isinstance(record_id, str):
                record_id = uuid.UUID(record_id)
            
            query = self.db.query(self.model_class).filter(self.model_class.id == record_id)
            
            if not include_deleted:
                query = query.filter(self.model_class.is_deleted == False)
            
            exists = query.first() is not None
            
            self.logger.debug(f"Checked existence of {self.model_class.__name__}",
                           record_id=str(record_id), exists=exists)
            
            return exists
            
        except Exception as e:
            self.logger.error(f"Failed to check {self.model_class.__name__} existence",
                           error=e, record_id=str(record_id))
            return False
    
    def get_metadata(self, record_id: Union[str, uuid.UUID]) -> Dict[str, Any]:
        """Get metadata for record."""
        try:
            record = self.get_by_id(record_id)
            if not record:
                return {}
            
            if hasattr(record, 'get_metadata'):
                return record.get_metadata()
            
            return {}
            
        except Exception as e:
            self.logger.error(f"Failed to get {self.model_class.__name__} metadata",
                           error=e, record_id=str(record_id))
            return {}
    
    def set_metadata(self, record_id: Union[str, uuid.UUID], 
                    metadata: Dict[str, Any]) -> bool:
        """Set metadata for record."""
        try:
            record = self.get_by_id(record_id)
            if not record:
                return False
            
            if hasattr(record, 'set_metadata'):
                record.set_metadata(metadata)
                self.db.commit()
                
                self.logger.info(f"Updated {self.model_class.__name__} metadata",
                              action='update_metadata',
                              resource_type=self.model_class.__name__,
                              resource_id=str(record.id),
                              metadata_keys=list(metadata.keys()))
                
                return True
            
            return False
            
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Failed to set {self.model_class.__name__} metadata",
                           error=e, record_id=str(record_id))
            return False