"""
Database utilities for consistent database operations and query patterns.
"""

from typing import Any, Dict, List, Optional, Union, Type, TypeVar, Callable
from datetime import datetime, date
from sqlalchemy import and_, or_, not_, func, desc, asc
from sqlalchemy.orm import Session, Query
from sqlalchemy.sql import text
from sqlalchemy.ext.declarative import declarative_base
import uuid

from app.db.base import BaseModel

T = TypeVar('T', bound=BaseModel)


class DatabaseUtils:
    """Utility class for database operations and query patterns."""
    
    @staticmethod
    def get_by_id_or_404(db: Session, model: Type[T], record_id: Union[str, uuid.UUID], 
                        include_deleted: bool = False) -> T:
        """Get record by ID or raise 404 error."""
        if isinstance(record_id, str):
            try:
                record_id = uuid.UUID(record_id)
            except ValueError:
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"{model.__name__} not found"
                )
        
        record = model.find_by_id(db, record_id, include_deleted)
        if not record:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{model.__name__} not found"
            )
        return record
    
    @staticmethod
    def paginate_query(query: Query, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """Paginate query results."""
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 20
        
        total = query.count()
        offset = (page - 1) * page_size
        
        items = query.offset(offset).limit(page_size).all()
        
        total_pages = (total + page_size - 1) // page_size
        
        return {
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1,
        }
    
    @staticmethod
    def build_filter_query(db: Session, model: Type[T], filters: Dict[str, Any]) -> Query:
        """Build query with dynamic filters."""
        query = model.active_query(db)
        
        for field, value in filters.items():
            if not hasattr(model, field) or value is None:
                continue
            
            column = getattr(model, field)
            
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
                elif 'not_in' in value:
                    query = query.filter(column.notin_(value['not_in']))
                elif 'like' in value:
                    query = query.filter(column.like(f"%{value['like']}%"))
                elif 'ilike' in value:
                    query = query.filter(column.ilike(f"%{value['ilike']}%"))
                elif 'is_null' in value:
                    if value['is_null']:
                        query = query.filter(column.is_(None))
                    else:
                        query = query.filter(column.isnot(None))
            elif isinstance(value, list):
                # Handle list filters (IN clause)
                query = query.filter(column.in_(value))
            else:
                # Handle simple equality
                query = query.filter(column == value)
        
        return query
    
    @staticmethod
    def build_search_query(db: Session, model: Type[T], search_term: str, 
                          search_fields: List[str]) -> Query:
        """Build query with text search across multiple fields."""
        query = model.active_query(db)
        
        if not search_term or not search_fields:
            return query
        
        search_conditions = []
        for field in search_fields:
            if hasattr(model, field):
                column = getattr(model, field)
                search_conditions.append(column.ilike(f"%{search_term}%"))
        
        if search_conditions:
            query = query.filter(or_(*search_conditions))
        
        return query
    
    @staticmethod
    def build_date_range_query(db: Session, model: Type[T], 
                              start_date: Optional[date] = None,
                              end_date: Optional[date] = None,
                              date_field: str = 'created_at') -> Query:
        """Build query with date range filter."""
        query = model.active_query(db)
        
        if not hasattr(model, date_field):
            return query
        
        date_column = getattr(model, date_field)
        
        if start_date:
            query = query.filter(date_column >= start_date)
        
        if end_date:
            # Include end date by adding one day
            end_datetime = datetime.combine(end_date, datetime.max.time())
            query = query.filter(date_column <= end_datetime)
        
        return query
    
    @staticmethod
    def apply_sorting(query: Query, sort_by: str, sort_order: str = 'desc') -> Query:
        """Apply sorting to query."""
        try:
            # Handle multiple sort fields
            sort_fields = sort_by.split(',')
            sort_orders = sort_order.split(',')
            
            for i, field in enumerate(sort_fields):
                field = field.strip()
                order = sort_orders[i].strip() if i < len(sort_orders) else 'desc'
                
                if hasattr(query.column_descriptions[0]['type'], field):
                    column = getattr(query.column_descriptions[0]['type'], field)
                    if order.lower() == 'asc':
                        query = query.order_by(asc(column))
                    else:
                        query = query.order_by(desc(column))
        except (IndexError, AttributeError):
            # Fallback to default sorting
            pass
        
        return query
    
    @staticmethod
    def bulk_create(db: Session, model: Type[T], items: List[Dict[str, Any]]) -> List[T]:
        """Bulk create records with error handling."""
        try:
            records = []
            for item_data in items:
                record = model(**item_data)
                db.add(record)
                records.append(record)
            
            db.commit()
            return records
        except Exception as e:
            db.rollback()
            raise e
    
    @staticmethod
    def bulk_update(db: Session, model: Type[T], 
                    updates: List[Dict[str, Any]]) -> int:
        """Bulk update records with error handling."""
        try:
            updated_count = 0
            for update_data in updates:
                if 'id' not in update_data:
                    continue
                
                record_id = update_data.pop('id')
                record = model.find_by_id(db, record_id)
                if record:
                    for key, value in update_data.items():
                        if hasattr(record, key):
                            setattr(record, key, value)
                    updated_count += 1
            
            db.commit()
            return updated_count
        except Exception as e:
            db.rollback()
            raise e
    
    @staticmethod
    def soft_delete_by_id(db: Session, model: Type[T], record_id: Union[str, uuid.UUID]) -> bool:
        """Soft delete record by ID."""
        try:
            record = DatabaseUtils.get_by_id_or_404(db, model, record_id)
            record.soft_delete()
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
    
    @staticmethod
    def restore_by_id(db: Session, model: Type[T], record_id: Union[str, uuid.UUID]) -> bool:
        """Restore soft deleted record by ID."""
        try:
            record = model.find_by_id(db, record_id, include_deleted=True)
            if record and record.is_deleted:
                record.restore()
                db.commit()
                return True
            return False
        except Exception:
            db.rollback()
            return False
    
    @staticmethod
    def execute_raw_query(db: Session, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute raw SQL query with parameters."""
        try:
            result = db.execute(text(query), params or {})
            return [dict(row._mapping) for row in result]
        except Exception as e:
            raise e
    
    @staticmethod
    def get_aggregate_stats(db: Session, model: Type[T], 
                           group_by: Optional[str] = None,
                           count_field: str = 'id',
                           sum_fields: Optional[List[str]] = None,
                           avg_fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get aggregate statistics for model."""
        query = db.query(model)
        
        # Select fields
        select_fields = []
        
        if group_by and hasattr(model, group_by):
            group_column = getattr(model, group_by)
            select_fields.append(group_column)
        
        # Count field
        if hasattr(model, count_field):
            count_column = getattr(model, count_field)
            select_fields.append(func.count(count_column).label('count'))
        
        # Sum fields
        if sum_fields:
            for field in sum_fields:
                if hasattr(model, field):
                    sum_column = getattr(model, field)
                    select_fields.append(func.sum(sum_column).label(f'{field}_sum'))
        
        # Average fields
        if avg_fields:
            for field in avg_fields:
                if hasattr(model, field):
                    avg_column = getattr(model, field)
                    select_fields.append(func.avg(avg_column).label(f'{field}_avg'))
        
        query = query.query(*select_fields)
        
        # Group by
        if group_by and hasattr(model, group_by):
            group_column = getattr(model, group_by)
            query = query.group_by(group_column)
        
        results = query.all()
        
        # Convert to list of dictionaries
        return [dict(row._mapping) for row in results]
    
    @staticmethod
    def get_related_records(db: Session, model: Type[T], record_id: Union[str, uuid.UUID],
                           relationship_name: str, **filters) -> List[Any]:
        """Get related records through relationship."""
        try:
            record = DatabaseUtils.get_by_id_or_404(db, model, record_id)
            
            if not hasattr(record, relationship_name):
                return []
            
            related_query = getattr(record, relationship_name)
            
            # Apply filters if provided
            if filters:
                if hasattr(related_query, 'filter'):
                    related_query = related_query.filter_by(**filters)
            
            return related_query.all() if hasattr(related_query, 'all') else [related_query]
        except Exception:
            return []
    
    @staticmethod
    def create_with_audit(db: Session, model: Type[T], data: Dict[str, Any], 
                        user_id: Optional[uuid.UUID] = None) -> T:
        """Create record with audit trail."""
        try:
            if user_id:
                data['created_by'] = user_id
            
            record = model(**data)
            db.add(record)
            db.commit()
            db.refresh(record)
            return record
        except Exception as e:
            db.rollback()
            raise e
    
    @staticmethod
    def update_with_audit(db: Session, model: Type[T], record_id: Union[str, uuid.UUID],
                        data: Dict[str, Any], user_id: Optional[uuid.UUID] = None) -> T:
        """Update record with audit trail."""
        try:
            record = DatabaseUtils.get_by_id_or_404(db, model, record_id)
            
            if user_id:
                data['updated_by'] = user_id
            
            for key, value in data.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            
            db.commit()
            db.refresh(record)
            return record
        except Exception as e:
            db.rollback()
            raise e
    
    @staticmethod
    def transaction_wrapper(db: Session, operations: List[Callable]) -> bool:
        """Execute multiple operations in a single transaction."""
        try:
            for operation in operations:
                operation(db)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e