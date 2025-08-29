import time
import random
import logging
import socket
import ssl
import json
from typing import Callable, Any, Dict, List, Optional
from requests.exceptions import (
    RequestException, Timeout, ConnectionError, HTTPError,
    ProxyError, URLRequired, InvalidURL, ContentDecodingError,
    ChunkedEncodingError, TooManyRedirects, MissingSchema
)
from urllib3.exceptions import (
    SSLError, MaxRetryError, ProtocolError,
    DecodeError, ReadTimeoutError, ConnectTimeoutError
)

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Error handling and retry logic for the proxy middleware"""
    
    def __init__(self, max_retries: int = 10, base_delay: float = 1.0, max_delay: float = 60.0, 
                 error_logger=None):
        """Initialize error handler with retry settings"""
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.error_logger = error_logger
        
        # Extended retry codes for future-proofing
        self.retry_codes = [429, 502, 503, 504, 505, 507, 508, 511, 408, 409, 410, 423, 424, 425, 426, 428, 431, 451]
        
        # Extended fail codes for client errors
        self.fail_codes = [400, 401, 403, 405, 406, 407, 411, 412, 413, 414, 415, 416, 417, 418, 421, 422]
        
        # Conditional retry codes - might be retryable depending on context
        self.conditional_retry_codes = [404, 411, 412, 413, 414, 416, 417, 418, 421, 423, 424, 425, 426, 428, 431, 451]
        
        # Conditional retry settings
        self.conditional_retry_enabled = True
        self.conditional_retry_max_attempts = 2
        self.conditional_retry_delay_multiplier = 0.5
    
    def should_retry(self, response) -> bool:
        """Determine if a response should be retried"""
        if hasattr(response, 'status_code'):
            return response.status_code in self.retry_codes
        return False
    
    def should_retry_conditionally(self, response) -> bool:
        """Determine if a response should be retried conditionally"""
        if hasattr(response, 'status_code'):
            return response.status_code in self.conditional_retry_codes
        return False
    
    def is_permanent_failure(self, response) -> bool:
        """Determine if a response represents a permanent failure"""
        if hasattr(response, 'status_code'):
            return response.status_code in self.fail_codes
        return False
    
    def should_retry_exception(self, exception: Exception) -> bool:
        """Determine if an exception should be retried"""
        # Network-level retryable exceptions
        network_retryable = (
            Timeout, ConnectionError, RequestException,
            socket.gaierror,  # DNS resolution failures
            socket.timeout,   # Socket timeouts
            MaxRetryError,    # Max retry errors
            ReadTimeoutError, ConnectTimeoutError,
            ProtocolError,    # Protocol-level errors
            DecodeError       # Content decoding errors
        )
        
        # SSL/TLS errors that might be transient
        ssl_retryable = (
            SSLError,
            ssl.SSLError,
            ssl.CertificateError
        )
        
        # Content errors that might be transient
        content_retryable = (
            ContentDecodingError,
            ChunkedEncodingError,
            json.JSONDecodeError
        )
        
        # Check if it's a retryable exception type
        if isinstance(exception, network_retryable + ssl_retryable + content_retryable):
            return True
        
        # Check HTTPError with retryable status codes
        if isinstance(exception, HTTPError):
            if hasattr(exception, 'response') and exception.response is not None:
                return exception.response.status_code in self.retry_codes
        
        # Check for specific non-retryable exceptions
        non_retryable = (
            URLRequired, InvalidURL, MissingSchema,  # URL/configuration errors
            TooManyRedirects,  # Infinite redirects
            ProxyError,        # Proxy configuration issues
            ValueError,        # Invalid parameters
            TypeError         # Type errors
        )
        
        if isinstance(exception, non_retryable):
            return False
        
        # Default to not retrying unknown exceptions
        return False
    
    def calculate_retry_delay(self, attempt: int) -> float:
        """Calculate retry delay with exponential backoff and jitter"""
        # Exponential backoff: base_delay * 2^(attempt-1)
        delay = self.base_delay * (2 ** (attempt - 1))
        
        # Add jitter (±25% of the delay)
        jitter = delay * 0.25 * random.uniform(-1, 1)
        delay += jitter
        
        # Ensure delay doesn't exceed max_delay
        return min(delay, self.max_delay)
    
    def retry_with_backoff(self, func: Callable, context: Optional[Dict[str, Any]] = None, *args, **kwargs) -> Any:
        """Retry a function with exponential backoff"""
        last_exception = None
        context = context or {}
        
        for attempt in range(1, self.max_retries + 2):  # +2 because we start at 1 and include the initial attempt
            try:
                result = func(*args, **kwargs)
                
                # If we get here, the function succeeded
                if attempt > 1:
                    logger.info(f"Function succeeded after {attempt} attempts")
                return result
                
            except Exception as e:
                last_exception = e
                
                # Log error if error logger is available
                if self.error_logger:
                    self.error_logger.log_error(e, context, retry_attempt=attempt)
                
                # Check if we should retry this exception
                if not self.should_retry_exception(e):
                    logger.error(f"Non-retryable error: {e}")
                    if self.error_logger:
                        self.error_logger.log_final_error(e, attempt, context)
                    raise e
                
                # Check if we've exceeded max retries
                if attempt > self.max_retries:
                    logger.error(f"Max retries ({self.max_retries}) exceeded. Last error: {e}")
                    if self.error_logger:
                        self.error_logger.log_final_error(e, attempt, context)
                    raise e
                
                # Calculate delay and wait
                delay = self.calculate_retry_delay(attempt)
                logger.warning(f"Attempt {attempt} failed: {e}. Retrying in {delay:.2f} seconds...")
                
                # Log retry attempt if error logger is available
                if self.error_logger:
                    self.error_logger.log_retry_attempt(e, attempt, delay, context)
                
                time.sleep(delay)
        
        # This should never be reached, but just in case
        raise last_exception
    
    def retry_with_conditional_logic(self, func: Callable, context: Dict[str, Any] = None, *args, **kwargs) -> Any:
        """Retry a function with conditional logic based on context"""
        last_exception = None
        context = context or {}
        
        for attempt in range(1, self.max_retries + 2):
            try:
                result = func(*args, **kwargs)
                
                # If we get here, the function succeeded
                if attempt > 1:
                    logger.info(f"Function succeeded after {attempt} attempts")
                return result
                
            except HTTPError as e:
                last_exception = e
                
                if hasattr(e, 'response') and e.response is not None:
                    status_code = e.response.status_code
                    
                    # Log error if error logger is available
                    if self.error_logger:
                        self.error_logger.log_error(e, context, retry_attempt=attempt)
                    
                    # Check if this is a permanent failure
                    if self.is_permanent_failure(e.response):
                        logger.error(f"Permanent failure (HTTP {status_code}): {e}")
                        if self.error_logger:
                            self.error_logger.log_final_error(e, attempt, context)
                        raise e
                    
                    # Check if this should be retried unconditionally
                    if self.should_retry(e.response):
                        if attempt > self.max_retries:
                            logger.error(f"Max retries ({self.max_retries}) exceeded for HTTP {status_code}")
                            if self.error_logger:
                                self.error_logger.log_final_error(e, attempt, context)
                            raise e
                        
                        delay = self.calculate_retry_delay(attempt)
                        logger.warning(f"HTTP {status_code} - Attempt {attempt} failed. Retrying in {delay:.2f} seconds...")
                        
                        # Log retry attempt if error logger is available
                        if self.error_logger:
                            self.error_logger.log_retry_attempt(e, attempt, delay, context)
                        
                        time.sleep(delay)
                        continue
                    
                    # Check if this should be retried conditionally
                    if self.should_retry_conditionally(e.response) and self.conditional_retry_enabled:
                        # Apply conditional retry logic based on context
                        if self._should_retry_conditionally(status_code, context, attempt):
                            if attempt > self.conditional_retry_max_attempts:
                                logger.error(f"Max conditional retries ({self.conditional_retry_max_attempts}) exceeded for HTTP {status_code}")
                                if self.error_logger:
                                    self.error_logger.log_final_error(e, attempt, context)
                                raise e
                            
                            delay = self.calculate_retry_delay(attempt) * self.conditional_retry_delay_multiplier
                            logger.warning(f"HTTP {status_code} - Conditional retry {attempt}. Retrying in {delay:.2f} seconds...")
                            
                            # Log retry attempt if error logger is available
                            if self.error_logger:
                                self.error_logger.log_retry_attempt(e, attempt, delay, context)
                            
                            time.sleep(delay)
                            continue
                        else:
                            logger.info(f"HTTP {status_code} - Not retrying conditionally based on context")
                            if self.error_logger:
                                self.error_logger.log_final_error(e, attempt, context)
                            raise e
                    
                    # If we get here, it's not retryable
                    logger.error(f"Non-retryable HTTP {status_code}: {e}")
                    if self.error_logger:
                        self.error_logger.log_final_error(e, attempt, context)
                    raise e
                
                # If no response object, treat as non-retryable
                logger.error(f"HTTPError without response: {e}")
                raise e
                
            except Exception as e:
                last_exception = e
                
                # Check if we should retry this exception
                if not self.should_retry_exception(e):
                    logger.error(f"Non-retryable error: {e}")
                    raise e
                
                # Check if we've exceeded max retries
                if attempt > self.max_retries:
                    logger.error(f"Max retries ({self.max_retries}) exceeded. Last error: {e}")
                    raise e
                
                # Calculate delay and wait
                delay = self.calculate_retry_delay(attempt)
                logger.warning(f"Attempt {attempt} failed: {e}. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        
        # This should never be reached, but just in case
        raise last_exception
    
    def _should_retry_conditionally(self, status_code: int, context: Dict[str, Any], attempt: int) -> bool:
        """Determine if a conditional retry should be attempted based on context"""
        
        # Context-based retry logic
        request_type = context.get('request_type', 'unknown')
        endpoint = context.get('endpoint', '')
        is_models_request = 'models' in endpoint.lower()
        
        # Different logic for different status codes
        if status_code == 404:
            # 404 might be retryable for models endpoint (service might be starting up)
            if is_models_request and attempt <= 2:
                return True
            # 404 might be retryable for chat completions if it's a temporary service issue
            if 'chat/completions' in endpoint and attempt <= 1:
                return True
        
        elif status_code in [408, 409, 410, 423, 424, 425, 426, 428]:
            # These are typically transient server issues
            return attempt <= 2
        
        elif status_code in [411, 412, 413, 414, 416, 417, 418, 421]:
            # These might be server configuration issues that could resolve
            return attempt <= 1
        
        elif status_code in [431, 451]:
            # These are often temporary (rate limits, legal blocks)
            return attempt <= 2
        
        return False
    
    def format_error_response(self, response) -> Dict[str, Any]:
        """Format error response in OpenAI-compatible format"""
        error_type_map = {
            # Client errors (4xx)
            400: "bad_request",
            401: "authentication",
            403: "authorization",
            404: "not_found",
            405: "method_not_allowed",
            406: "not_acceptable",
            407: "proxy_authentication_required",
            408: "request_timeout",
            409: "conflict",
            410: "gone",
            411: "length_required",
            412: "precondition_failed",
            413: "payload_too_large",
            414: "uri_too_long",
            415: "unsupported_media_type",
            416: "range_not_satisfiable",
            417: "expectation_failed",
            418: "teapot",
            421: "misdirected_request",
            422: "unprocessable_entity",
            423: "locked",
            424: "failed_dependency",
            425: "too_early",
            426: "upgrade_required",
            428: "precondition_required",
            429: "rate_limit",
            431: "request_header_fields_too_large",
            451: "unavailable_for_legal_reasons",
            
            # Server errors (5xx)
            500: "internal_server_error",
            501: "not_implemented",
            502: "bad_gateway",
            503: "service_unavailable",
            504: "gateway_timeout",
            505: "http_version_not_supported",
            506: "variant_also_negotiates",
            507: "insufficient_storage",
            508: "loop_detected",
            510: "not_extended",
            511: "network_authentication_required"
        }
        
        error_type = error_type_map.get(response.status_code, "unknown_error")
        error_response = {
            "error": {
                "message": getattr(response, 'text', str(response)),
                "type": error_type,
                "status_code": response.status_code
            }
        }
        
        # Add retry_after for rate limiting
        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After', 30)
            try:
                retry_after = int(retry_after)
            except (ValueError, TypeError):
                retry_after = 30
            error_response["error"]["retry_after"] = retry_after
        
        # Add additional headers for debugging
        if hasattr(response, 'headers'):
            error_response["error"]["headers"] = dict(response.headers)
        
        return error_response
    
    def format_exception_response(self, exception: Exception) -> Dict[str, Any]:
        """Format exception response in OpenAI-compatible format"""
        error_type_map = {
            # Network errors
            Timeout: "timeout",
            ConnectionError: "connection_error",
            RequestException: "request_error",
            socket.gaierror: "dns_error",
            socket.timeout: "socket_timeout",
            MaxRetryError: "max_retry_error",
            ReadTimeoutError: "read_timeout",
            ConnectTimeoutError: "connect_timeout",
            ProtocolError: "protocol_error",
            DecodeError: "decode_error",
            
            # SSL/TLS errors
            ssl.SSLError: "ssl_error",
            SSLError: "ssl_error",
            ssl.CertificateError: "certificate_error",
            
            # Content errors
            ContentDecodingError: "content_decoding_error",
            ChunkedEncodingError: "chunked_encoding_error",
            json.JSONDecodeError: "json_decode_error",
            
            # URL/Configuration errors
            URLRequired: "url_required",
            InvalidURL: "invalid_url",
            MissingSchema: "missing_schema",
            TooManyRedirects: "too_many_redirects",
            ProxyError: "proxy_error",
            
            # HTTP errors
            HTTPError: "http_error"
        }
        
        error_type = error_type_map.get(type(exception), "unknown_error")
        
        error_response = {
            "error": {
                "message": str(exception),
                "type": error_type,
                "exception_type": type(exception).__name__
            }
        }
        
        # Add additional context for specific error types
        if isinstance(exception, HTTPError) and hasattr(exception, 'response'):
            error_response["error"]["status_code"] = exception.response.status_code
            error_response["error"]["response_text"] = exception.response.text
        
        return error_response
