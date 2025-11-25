"""
File handling utilities for consistent file operations across the application.
"""

import os
import hashlib
import mimetypes
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import magic


class FileUtils:
    """Utility class for file operations and validation."""
    
    # Allowed file extensions for different types
    ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    ALLOWED_DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt'}
    ALLOWED_SPREADSHEET_EXTENSIONS = {'.xls', '.xlsx', '.csv', '.ods'}
    ALLOWED_ARCHIVE_EXTENSIONS = {'.zip', '.rar', '.7z', '.tar', '.gz'}
    
    # Maximum file sizes (in bytes)
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_DOCUMENT_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_SPREADSHEET_SIZE = 20 * 1024 * 1024  # 20MB
    MAX_ARCHIVE_SIZE = 100 * 1024 * 1024  # 100MB
    
    @staticmethod
    def get_file_extension(filename: str) -> str:
        """Get file extension from filename."""
        return Path(filename).suffix.lower()
    
    @staticmethod
    def is_allowed_extension(filename: str, allowed_extensions: set) -> bool:
        """Check if file extension is in allowed set."""
        extension = FileUtils.get_file_extension(filename)
        return extension in allowed_extensions
    
    @staticmethod
    def is_image_file(filename: str) -> bool:
        """Check if file is an image."""
        return FileUtils.is_allowed_extension(filename, FileUtils.ALLOWED_IMAGE_EXTENSIONS)
    
    @staticmethod
    def is_document_file(filename: str) -> bool:
        """Check if file is a document."""
        return FileUtils.is_allowed_extension(filename, FileUtils.ALLOWED_DOCUMENT_EXTENSIONS)
    
    @staticmethod
    def is_spreadsheet_file(filename: str) -> bool:
        """Check if file is a spreadsheet."""
        return FileUtils.is_allowed_extension(filename, FileUtils.ALLOWED_SPREADSHEET_EXTENSIONS)
    
    @staticmethod
    def is_archive_file(filename: str) -> bool:
        """Check if file is an archive."""
        return FileUtils.is_allowed_extension(filename, FileUtils.ALLOWED_ARCHIVE_EXTENSIONS)
    
    @staticmethod
    def get_file_size(file_path: str) -> int:
        """Get file size in bytes."""
        return os.path.getsize(file_path)
    
    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """Format file size as human readable string."""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    @staticmethod
    def calculate_file_hash(file_path: str, algorithm: str = 'sha256') -> str:
        """Calculate file hash for integrity verification."""
        hash_func = hashlib.new(algorithm)
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    @staticmethod
    def get_mime_type(file_path: str) -> str:
        """Get MIME type of file."""
        mime_type, _ = mimetypes.guess_type(file_path)
        
        # Fallback to python-magic if available
        if not mime_type:
            try:
                mime_type = magic.from_file(file_path, mime=True)
            except:
                mime_type = 'application/octet-stream'
        
        return mime_type or 'application/octet-stream'
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename for safe storage."""
        # Remove directory traversal attempts
        filename = filename.replace('..', '').replace('/', '').replace('\\', '')
        
        # Remove null bytes and control characters
        filename = ''.join(char for char in filename if ord(char) >= 32)
        
        # Replace problematic characters
        filename = filename.replace(' ', '_')
        filename = ''.join(c for c in filename if c.isalnum() or c in '._-')
        
        # Limit length
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            filename = name[:255-len(ext)] + ext
        
        return filename.strip()
    
    @staticmethod
    def validate_file(file_path: str, max_size: Optional[int] = None, 
                     allowed_extensions: Optional[set] = None) -> Tuple[bool, str]:
        """Validate file against size and extension constraints."""
        if not os.path.exists(file_path):
            return False, "File does not exist"
        
        # Check file size
        file_size = FileUtils.get_file_size(file_path)
        if max_size and file_size > max_size:
            return False, f"File too large (max {FileUtils.format_file_size(max_size)})"
        
        # Check file extension
        if allowed_extensions:
            filename = os.path.basename(file_path)
            if not FileUtils.is_allowed_extension(filename, allowed_extensions):
                return False, "File type not allowed"
        
        return True, "File is valid"
    
    @staticmethod
    def create_directory(directory_path: str) -> bool:
        """Create directory if it doesn't exist."""
        try:
            os.makedirs(directory_path, exist_ok=True)
            return True
        except OSError:
            return False
    
    @staticmethod
    def ensure_directory_exists(file_path: str) -> bool:
        """Ensure directory exists for given file path."""
        directory = os.path.dirname(file_path)
        return FileUtils.create_directory(directory)
    
    @staticmethod
    def safe_delete_file(file_path: str) -> bool:
        """Safely delete file with error handling."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            return True
        except OSError:
            return False
    
    @staticmethod
    def copy_file_with_integrity(source: str, destination: str) -> Tuple[bool, str]:
        """Copy file with integrity verification."""
        try:
            # Ensure destination directory exists
            FileUtils.ensure_directory_exists(destination)
            
            # Copy file
            import shutil
            shutil.copy2(source, destination)
            
            # Verify integrity
            source_hash = FileUtils.calculate_file_hash(source)
            dest_hash = FileUtils.calculate_file_hash(destination)
            
            if source_hash == dest_hash:
                return True, "File copied successfully"
            else:
                FileUtils.safe_delete_file(destination)
                return False, "File integrity check failed"
                
        except Exception as e:
            return False, f"Copy failed: {str(e)}"
    
    @staticmethod
    def get_file_metadata(file_path: str) -> Dict[str, Any]:
        """Get comprehensive file metadata."""
        if not os.path.exists(file_path):
            return {}
        
        stat = os.stat(file_path)
        filename = os.path.basename(file_path)
        
        return {
            'filename': filename,
            'size': stat.st_size,
            'size_formatted': FileUtils.format_file_size(stat.st_size),
            'extension': FileUtils.get_file_extension(filename),
            'mime_type': FileUtils.get_mime_type(file_path),
            'created_time': stat.st_ctime,
            'modified_time': stat.st_mtime,
            'is_image': FileUtils.is_image_file(filename),
            'is_document': FileUtils.is_document_file(filename),
            'is_spreadsheet': FileUtils.is_spreadsheet_file(filename),
            'is_archive': FileUtils.is_archive_file(filename),
            'hash_sha256': FileUtils.calculate_file_hash(file_path, 'sha256'),
        }
    
    @staticmethod
    def find_files_by_extension(directory: str, extensions: List[str]) -> List[str]:
        """Find all files with specified extensions in directory."""
        found_files = []
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                if FileUtils.is_allowed_extension(file, set(extensions)):
                    found_files.append(file_path)
        
        return found_files
    
    @staticmethod
    def get_directory_size(directory: str) -> int:
        """Get total size of directory in bytes."""
        total_size = 0
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    total_size += os.path.getsize(file_path)
                except OSError:
                    continue
        
        return total_size
    
    @staticmethod
    def cleanup_old_files(directory: str, days_old: int = 30) -> int:
        """Clean up files older than specified days."""
        import time
        cutoff_time = time.time() - (days_old * 24 * 60 * 60)
        deleted_count = 0
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    if os.path.getmtime(file_path) < cutoff_time:
                        FileUtils.safe_delete_file(file_path)
                        deleted_count += 1
                except OSError:
                    continue
        
        return deleted_count