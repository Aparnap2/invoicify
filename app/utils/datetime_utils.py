"""
Date and time utilities for consistent datetime handling across the application.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Union
import iso8601


class DateTimeUtils:
    """Utility class for datetime operations and formatting."""
    
    @staticmethod
    def utc_now() -> datetime:
        """Get current UTC datetime."""
        return datetime.now(timezone.utc)
    
    @staticmethod
    def to_utc(dt: datetime) -> datetime:
        """Convert datetime to UTC."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    
    @staticmethod
    def from_iso_string(iso_string: str) -> datetime:
        """Parse ISO 8601 string to datetime."""
        try:
            return iso8601.parse_date(iso_string)
        except iso8601.ParseError:
            raise ValueError(f"Invalid ISO 8601 datetime string: {iso_string}")
    
    @staticmethod
    def to_iso_string(dt: datetime) -> str:
        """Convert datetime to ISO 8601 string."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    
    @staticmethod
    def format_duration(start_time: datetime, end_time: Optional[datetime] = None) -> str:
        """Format duration between two datetimes as human readable string."""
        if end_time is None:
            end_time = DateTimeUtils.utc_now()
        
        duration = end_time - start_time
        
        if duration.total_seconds() < 60:
            return f"{int(duration.total_seconds())} seconds"
        elif duration.total_seconds() < 3600:
            minutes = int(duration.total_seconds() / 60)
            return f"{minutes} minutes"
        elif duration.total_seconds() < 86400:
            hours = int(duration.total_seconds() / 3600)
            return f"{hours} hours"
        else:
            days = int(duration.total_seconds() / 86400)
            return f"{days} days"
    
    @staticmethod
    def add_business_days(dt: datetime, days: int) -> datetime:
        """Add business days to datetime (excluding weekends)."""
        current = dt
        added_days = 0
        
        while added_days < days:
            current += timedelta(days=1)
            if current.weekday() < 5:  # Monday to Friday
                added_days += 1
        
        return current
    
    @staticmethod
    def is_business_day(dt: datetime) -> bool:
        """Check if datetime falls on a business day."""
        return dt.weekday() < 5  # Monday to Friday
    
    @staticmethod
    def get_date_range(start_date: datetime, end_date: datetime) -> list[datetime]:
        """Get list of dates between start and end date (inclusive)."""
        dates = []
        current = start_date.date()
        end = end_date.date()
        
        while current <= end:
            dates.append(datetime.combine(current, datetime.min.time()))
            current += timedelta(days=1)
        
        return dates
    
    @staticmethod
    def get_quarter(dt: datetime) -> int:
        """Get quarter number from datetime."""
        return (dt.month - 1) // 3 + 1
    
    @staticmethod
    def get_fiscal_year(dt: datetime, start_month: int = 7) -> int:
        """Get fiscal year (default starts in July)."""
        if dt.month >= start_month:
            return dt.year + 1
        return dt.year
    
    @staticmethod
    def age_from_datetime(dt: datetime) -> str:
        """Get human readable age from datetime."""
        now = DateTimeUtils.utc_now()
        return DateTimeUtils.format_duration(dt, now)