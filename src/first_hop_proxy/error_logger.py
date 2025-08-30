import os
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, Union
import logging
from requests import Response
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class ErrorLogger:
    """Handles independent logging of errors and retries to separate files"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize error logger with configuration"""
        # Use the new independent error logging configuration
        self.config = config.get("error_logging", {})
        self.enabled = self.config.get("enabled", False)
        self.error_logs_folder = self.config.get("folder", "logs/errors")
        
        # Additional error logging settings
        self.include_stack_traces = self.config.get("include_stack_traces", True)
        self.include_request_context = self.config.get("include_request_context", True)
        self.include_timing = self.config.get("include_timing", True)
        self.max_file_size_mb = self.config.get("max_file_size_mb", 10)
        self.max_files = self.config.get("max_files", 100)
        
        # Create error logs directory if enabled
        if self.enabled:
            os.makedirs(self.error_logs_folder, exist_ok=True)
    
    def _get_error_filename(self, error_code: Union[int, str], timestamp: Optional[float] = None) -> str:
        """Generate filename for error log based on error code and timestamp"""
        if timestamp is None:
            timestamp = time.time()
        
        # Convert timestamp to datetime for filename
        dt = datetime.fromtimestamp(timestamp)
        timestamp_str = dt.strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Include milliseconds
        
        # Sanitize error code for filename
        if isinstance(error_code, int):
            error_code_str = str(error_code)
        else:
            # For exception types, use a sanitized version
            error_code_str = str(error_code).replace(" ", "_").replace("<", "").replace(">", "").replace("'", "")
        
        return f"{error_code_str}_{timestamp_str}.log"
    
    def _get_error_code(self, error: Union[Exception, Response, int]) -> Union[int, str]:
        """Extract error code from various error types"""
        if isinstance(error, int):
            return error
        
        if isinstance(error, Response):
            return error.status_code
        
        # Check if error has a status_code attribute (for Mock objects or custom error types)
        if hasattr(error, 'status_code') and error.status_code is not None:
            return error.status_code
        
        if isinstance(error, Exception):
            # For exceptions, use the exception type name
            return type(error).__name__
        
        return "unknown_error"
    
    def _format_error_context(self, error: Union[Exception, Response], 
                            context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Format error context for logging"""
        error_context = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__ if isinstance(error, Exception) else "HTTPResponse",
            "error_message": str(error) if isinstance(error, Exception) else f"HTTP {error.status_code}",
        }
        
        # Add timing information if enabled
        if self.include_timing:
            error_context["timestamp_unix"] = time.time()
        
        # Add HTTP-specific information
        if isinstance(error, Response):
            error_context.update({
                "status_code": error.status_code,
                "status_text": error.reason,
                "url": error.url,
                "headers": dict(error.headers),
                "response_text": error.text[:1000] if error.text else None,  # Limit response text
            })
        
        # Add exception-specific information
        if isinstance(error, Exception):
            error_context.update({
                "exception_type": type(error).__name__,
                "exception_args": error.args,
            })
            
            # Add stack trace if enabled
            if self.include_stack_traces:
                import traceback
                error_context["stack_trace"] = traceback.format_exc()
            
            # Add HTTP error specific info
            if hasattr(error, 'response') and error.response is not None:
                error_context.update({
                    "http_status_code": error.response.status_code,
                    "http_status_text": error.response.reason,
                    "http_url": error.response.url,
                    "http_headers": dict(error.response.headers),
                    "http_response_text": error.response.text[:1000] if error.response.text else None,
                })
        
        # Add context information if enabled
        if context and self.include_request_context:
            error_context["context"] = context
        
        return error_context
    
    def log_error(self, error: Union[Exception, Response, int], 
                  context: Optional[Dict[str, Any]] = None,
                  retry_attempt: Optional[int] = None,
                  retry_delay: Optional[float] = None) -> str:
        """Log an error to a separate file based on error code and timestamp"""
        if not self.enabled:
            return ""
        
        # Manage file rotation before writing
        self._manage_file_rotation()
        
        error_code = self._get_error_code(error)
        error_context = self._format_error_context(error, context)
        
        # Add retry information if available
        if retry_attempt is not None:
            error_context["retry_attempt"] = retry_attempt
        if retry_delay is not None:
            error_context["retry_delay"] = retry_delay
        
        # Generate filename
        filename = self._get_error_filename(error_code)
        filepath = os.path.join(self.error_logs_folder, filename)
        
        # Create log content
        log_content = []
        log_content.append("=" * 80)
        log_content.append(f"ERROR LOG - {datetime.now().isoformat()}")
        log_content.append("=" * 80)
        log_content.append(f"Error Code: {error_code}")
        log_content.append(f"File: {filename}")
        log_content.append("")
        
        # Add retry information header if this is a retry
        if retry_attempt is not None:
            log_content.append("-" * 40)
            log_content.append(f"RETRY ATTEMPT #{retry_attempt}")
            if retry_delay is not None:
                log_content.append(f"Retry Delay: {retry_delay:.2f} seconds")
            log_content.append("-" * 40)
            log_content.append("")
        
        # Add error details
        log_content.append("ERROR DETAILS:")
        log_content.append("-" * 40)
        log_content.append(json.dumps(error_context, indent=2, default=str))
        
        # Write to file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(log_content))
            
            logger.info(f"Error logged to: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to write error log to {filepath}: {e}")
            return ""
    
    def log_retry_attempt(self, error: Union[Exception, Response], 
                         attempt: int, delay: float,
                         context: Optional[Dict[str, Any]] = None) -> str:
        """Log a retry attempt specifically"""
        return self.log_error(error, context, retry_attempt=attempt, retry_delay=delay)
    
    def log_final_error(self, error: Union[Exception, Response],
                       total_attempts: int,
                       context: Optional[Dict[str, Any]] = None) -> str:
        """Log the final error after all retries are exhausted"""
        error_context = self._format_error_context(error, context)
        error_context["total_retry_attempts"] = total_attempts
        error_context["final_error"] = True
        
        return self.log_error(error, error_context)
    

    
    def _manage_file_rotation(self) -> None:
        """Manage file rotation based on size and count limits"""
        if not self.enabled or not os.path.exists(self.error_logs_folder):
            return
        
        try:
            # Get all log files
            log_files = []
            for filename in os.listdir(self.error_logs_folder):
                if filename.endswith('.log'):
                    filepath = os.path.join(self.error_logs_folder, filename)
                    file_stat = os.stat(filepath)
                    log_files.append({
                        'filename': filename,
                        'filepath': filepath,
                        'size_mb': file_stat.st_size / (1024 * 1024),
                        'modified': file_stat.st_mtime
                    })
            
            # Sort by modification time (oldest first)
            log_files.sort(key=lambda x: x['modified'])
            
            # Remove oldest files if we exceed max_files
            if len(log_files) >= self.max_files:
                files_to_remove = len(log_files) - self.max_files + 1
                for i in range(files_to_remove):
                    try:
                        os.remove(log_files[i]['filepath'])
                        logger.info(f"Removed old error log file: {log_files[i]['filename']}")
                    except Exception as e:
                        logger.error(f"Failed to remove old error log file {log_files[i]['filename']}: {e}")
            
            # Check for oversized files
            for log_file in log_files:
                if log_file['size_mb'] > self.max_file_size_mb:
                    try:
                        # Create a backup with timestamp
                        backup_filename = f"{log_file['filename']}.backup_{int(time.time())}"
                        backup_filepath = os.path.join(self.error_logs_folder, backup_filename)
                        os.rename(log_file['filepath'], backup_filepath)
                        logger.info(f"Rotated oversized error log file: {log_file['filename']}")
                    except Exception as e:
                        logger.error(f"Failed to rotate oversized error log file {log_file['filename']}: {e}")
        
        except Exception as e:
            logger.error(f"Error during file rotation: {e}")
    
    def get_error_logs_summary(self) -> Dict[str, Any]:
        """Get a summary of error logs"""
        if not self.enabled or not os.path.exists(self.error_logs_folder):
            return {"error_logs": [], "total_errors": 0}
        
        error_logs = []
        total_errors = 0
        
        try:
            for filename in os.listdir(self.error_logs_folder):
                if filename.endswith('.log'):
                    filepath = os.path.join(self.error_logs_folder, filename)
                    file_stat = os.stat(filepath)
                    
                    # Parse error code from filename
                    error_code = filename.split('_')[0]
                    
                    error_logs.append({
                        "filename": filename,
                        "error_code": error_code,
                        "size_bytes": file_stat.st_size,
                        "size_mb": round(file_stat.st_size / (1024 * 1024), 2),
                        "created": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                        "modified": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                    })
                    total_errors += 1
        except Exception as e:
            logger.error(f"Error reading error logs directory: {e}")
        
        return {
            "error_logs": sorted(error_logs, key=lambda x: x["modified"], reverse=True),
            "total_errors": total_errors,
            "max_files": self.max_files,
            "max_file_size_mb": self.max_file_size_mb
        }
