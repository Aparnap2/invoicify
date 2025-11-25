
"""
Enhanced logging utilities for consistent logging across the application.
"""

import logging
import json
import traceback
from typing import Any, Dict, Optional, Union
from datetime import datetime
from functools import wraps
from contextvars import ContextVar
import uuid

# Context variables for request tracking
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)


class StructuredLogger:
    """Structured logger with JSON formatting and context tracking."""
    
    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Avoid duplicate handlers
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = StructuredFormatter()
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def _log(self, level: int, message: str, **kwargs) -> None:
        """Internal logging method with structured data."""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': logging.getLevelName(level),
            'message': message,
            'request_id': request_id_var.get(),
            'user_id': user_id_var.get(),
            **kwargs
        }
        
        self.logger.log(level, json.dumps(log_data))
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, error: Optional[Exception] = None, **kwargs) -> None:
        """Log error message."""
        if error:
            kwargs['error_type'] = type(error).__name__
            kwargs['error_message'] = str(error)
            kwargs['traceback'] = traceback.format_exc()
        
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, error: Optional[Exception] = None, **kwargs) -> None:
        """Log critical message."""
        if error:
            kwargs['error_type'] = type(error).__name__
            kwargs['error_message'] = str(error)
            kwargs['traceback'] = traceback.format_exc()
        
        self._log(logging.CRITICAL, message, **kwargs)
    
    def audit(self, action: str, resource_type: str, resource_id: str, 
              user_id: Optional[str] = None, **kwargs) -> None:
        """Log audit event."""
        audit_data = {
            'event_type': 'audit',
            'action': action,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'audit_user_id': user_id,
            **kwargs
        }
        self.info(f"Audit: {action} on {resource_type} {resource_id}", **audit_data)
    
    def performance(self, operation: str, duration_ms: float, 
                    metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log performance metrics."""
        perf_data = {
            'event_type': 'performance',
            'operation': operation,
            'duration_ms': duration_ms,
            **(metadata or {})
        }
        self.info(f"Performance: {operation} took {duration_ms}ms", **perf_data)
    
    def security(self, event: str, severity: str = 'medium', 
                 details: Optional[Dict[str, Any]] = None) -> None:
        """Log security events."""
        security_data = {
            'event_type': 'security',
            'security_event': event,
            'severity': severity,
            **(details or {})
        }
        self.warning(f"Security: {event}", **security_data)


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add request context if available
        request_id = request_id_var.get()
        if request_id:
            log_data['request_id'] = request_id
        
        user_id = user_id_var.get()
        if user_id:
            log_data['user_id'] = user_id
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 
                          'pathname', 'filename', 'module', 'lineno', 
                          'funcName', 'created', 'msecs', 'relativeCreated',
                          'thread', 'threadName', 'processName', 'process',
                          'getMessage', 'exc_info', 'exc_text', 'stack_info']:
                log_data[key] = value
        
        return json.dumps(log_data)


class LoggingUtils:
    """Utility class for logging operations and decorators."""
    
    @staticmethod
    def get_logger(name: str) -> StructuredLogger:
        """Get structured logger instance."""
        return StructuredLogger(name)
    
    @staticmethod
    def set_request_context(request_id: Optional[str] = None, 
                          user_id: Optional[str] = None) -> None:
        """Set request context for logging."""
        if request_id:
            request_id_var.set(request_id)
        if user_id:
            user_id_var.set(user_id)
    
    @staticmethod
    def clear_request_context() -> None:
        """Clear request context."""
        request_id_var.set(None)
        user_id_var.set(None)
    
    @staticmethod
    def generate_request_id() -> str:
        """Generate unique request ID."""
        return str(uuid.uuid4())
    
    @staticmethod
    def log_function_call(logger: StructuredLogger, operation: str = None):
        """Decorator to log function calls with timing."""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                func_name = operation or f"{func.__module__}.{func.__name__}"
                start_time = datetime.utcnow()
                
                logger.debug(f"Starting {func_name}", 
                           function=func_name, 
                           args_count=len(args), 
                           kwargs_keys=list(kwargs.keys()))
                
                try:
                    result = func(*args, **kwargs)
                    duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    logger.info(f"Completed {func_name}", 
                              function=func_name, 
                              duration_ms=duration,
                              success=True)
                    
                    return result
                
                except Exception as e:
                    duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    logger.error(f"Failed {func_name}", 
                               function=func_name, 
                               duration_ms=duration,
                               success=False,
                               error=e)
                    
                    raise
            
            return wrapper
        return decorator
    
    @staticmethod
    def log_api_request(logger: StructuredLogger, method: str, path: str, 
                      user_id: Optional[str] = None, **kwargs):
        """Log API request."""
        logger.info(f"API Request: {method} {path}",
                   event_type='api_request',
                   method=method,
                   path=path,
                   user_id=user_id,
                   **kwargs)
    
    @staticmethod
    def log_api_response(logger: StructuredLogger, method: str, path: str, 
                       status_code: int, duration_ms: float, **kwargs):
        """Log API response."""
        logger.info(f"API Response: {method} {path} - {status_code}",
                   event_type='api_response',
                   method=method,
                   path=path,
                   status_code=status_code,
                   duration_ms=duration_ms,
                   **kwargs)
    
    @staticmethod
    def log_database_query(logger: StructuredLogger, query: str, duration_ms: float,
                          params: Optional[Dict[str, Any]] = None):
        """Log database query."""
        logger.debug(f"Database Query executed",
                    event_type='database_query',
                    query=query,
                    duration_ms=duration_ms,
                    params=params)
    
    @staticmethod
    def log_external_service_call(logger: StructuredLogger, service: str, 
                                endpoint: str, method: str, status_code: int,
                                duration_ms: float, **kwargs):
        """Log external service call."""
        logger.info(f"External Service Call: {service} {method} {endpoint}",
                   event_type='external_service',
                   service=service,
                   endpoint=endpoint,
                   method=method,
                   status_code=status_code,
                   duration_ms=duration_ms,
                   **kwargs)
    
    @staticmethod
    def log_business_event(logger: StructuredLogger, event_type: str, 
                          event_data: Dict[str, Any]):
        """Log business events."""
        logger.info(f"Business Event: {event_type}",
                   event_type='business',
                   business_event_type=event_type,
                   **event_data)
    
    @staticmethod
    def log_error_with_context(logger: StructuredLogger, error: Exception, 
                              context: Dict[str, Any]):
        """Log error with additional context."""
        logger.error(f"Error occurred: {str(error)}",
                   error_type=type(error).__name__,
                   error_message=str(error),
                   traceback=traceback.format_exc(),
                   **context)
    
    @staticmethod
    def create_log_filter(level: str = 'INFO'):
        """Create log filter for specific level."""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        
        log_level = level_map.get(level.upper(), logging.INFO)
        
        class LevelFilter(logging.Filter):
            def filter(self, record):
                return record.levelno >= log_level
        
        return LevelFilter()
    
    @staticmethod
    def configure_logging(config: Dict[str, Any]):
        """Configure logging from configuration."""
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(config.get('level', logging.INFO))
        
        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Add console handler
        if config.get('console', True):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(StructuredFormatter())
            root_logger.addHandler(console_handler)
        
        # Add file handler if configured
        if config.get('file'):
            file_handler = logging.FileHandler(config['file'])
            file_handler.setFormatter(StructuredFormatter())
            root_logger.addHandler(file_handler)
        
        # Configure specific loggers
        for logger_name, logger_config in config.get('loggers', {}).items():
            logger = logging.getLogger(logger_name)
            logger.setLevel(logger_config.get('level', logging.INFO))
                    