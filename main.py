import json
import logging
import uuid
import time
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from config import Config
from proxy_client import ProxyClient
from error_handler import ErrorHandler
from request_logger import RequestLogger
from error_logger import ErrorLogger
from requests.exceptions import HTTPError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize components
config = Config()
error_handler = ErrorHandler()

# Global request logger - will be initialized after config is loaded
global request_logger
request_logger = None

# Global error logger - will be initialized after config is loaded
global error_logger
error_logger = None

from utils import sanitize_headers_for_logging, process_messages_with_regex
from constants import DEFAULT_MODELS


def forward_request(request_data: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Forward request to target proxy with error handling and retry logic"""
    try:
        # Get target proxy configuration
        proxy_config = config.get_target_proxy_config()
        target_url = proxy_config.get("url")
        if not target_url:
            raise ValueError("target_proxy.url is not configured")
        
        # Get error handling configuration
        error_config = config.get_error_handling_config()
        max_retries = error_config.get("max_retries", 10)
        base_delay = error_config.get("base_delay", 1.0)
        max_delay = error_config.get("max_delay", 60.0)
        
        # Get hard stop configuration
        hard_stop_config = error_config.get("hard_stop_conditions", {})
        
        # Create error handler with configuration and error logger
        error_handler = ErrorHandler(max_retries=max_retries, base_delay=base_delay, max_delay=max_delay, 
                                   error_logger=error_logger, hard_stop_config=hard_stop_config)
        
        # Create proxy client
        proxy_client = ProxyClient(target_url, config=config)
        
        # Define the request function that will be retried
        def make_request():
            return proxy_client.forward_request(request_data, headers=headers, endpoint="")
        
        # Create context for error handling
        context = {
            "request_type": "forward_request",
            "target_url": target_url,
            "timestamp": time.time()
        }
        
        # Use error handler for retries
        return error_handler.retry_with_backoff(make_request, context)
        
    except Exception as e:
        logger.error(f"Error forwarding request: {e}")
        
        # Log to error logger if available
        if error_logger:
            error_logger.log_error(e, {
                "context": "forward_request",
                "error_type": "forward_request_error"
            })
        
        # Re-raise the original exception to preserve the stack trace
        raise


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"})


@app.route('/health/detailed', methods=['GET'])
def detailed_health_check():
    """Detailed health check endpoint with retry configuration"""
    try:
        # Get error handling configuration
        error_config = config.get_error_handling_config()
        
        health_info = {
            "status": "healthy",
            "timestamp": time.time(),
            "retry_config": {
                "max_retries": error_config.get("max_retries", 10),
                "base_delay": error_config.get("base_delay", 1.0),
                "max_delay": error_config.get("max_delay", 60.0),
                "retry_codes": error_config.get("retry_codes", [429, 502, 503, 504, 505, 507, 508, 511, 408, 409, 410, 423, 424, 425, 426, 428, 431, 451])
            }
        }
        
        return jsonify(health_info)
    except Exception as e:
        logger.error(f"Error in detailed health check: {e}")
        
        # Log to error logger if available
        if error_logger:
            error_logger.log_error(e, {
                "context": "health_check",
                "endpoint": "/health/detailed",
                "error_type": "health_check_error"
            })
        
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


@app.route('/logs/errors', methods=['GET'])
def get_error_logs():
    """Get error logs summary"""
    try:
        if not error_logger:
            return jsonify({"error": "Error logging is disabled"}), 400
        
        summary = error_logger.get_error_logs_summary()
        return jsonify(summary)
        
    except Exception as e:
        logger.error(f"Error getting error logs summary: {e}")
        
        # Log to error logger if available
        if error_logger:
            error_logger.log_error(e, {
                "context": "error_logs_endpoint",
                "endpoint": "/logs/errors",
                "error_type": "error_logs_summary_error"
            })
        
        return jsonify({"error": str(e)}), 500


@app.route('/models', methods=['GET'])
def models():
    """Return available models from target proxy"""
    try:
        # Generate unique request ID for tracking
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        
        logger.info(f"=== MODELS REQUEST [{request_id}] ===")
        logger.info(f"Headers: {sanitize_headers_for_logging(dict(request.headers))}")
        
        # Forward the models request to target proxy
        try:
            # Get target proxy configuration
            proxy_config = config.get_target_proxy_config()
            target_url = proxy_config.get("url")
            if not target_url:
                raise ValueError("target_proxy.url is not configured")
            
            # Extract base URL by removing /chat/completions from the end
            base_url = target_url.replace("/chat/completions", "")
            models_url = f"{base_url}/models"
            
            logger.info(f"Models URL: {models_url}")
            
            # Create proxy client for models endpoint
            proxy_client = ProxyClient(models_url, error_logger=error_logger)
            
            # Create error handler for models request
            error_config = config.get_error_handling_config()
            max_retries = error_config.get("max_retries", 10)
            base_delay = error_config.get("base_delay", 1.0)
            max_delay = error_config.get("max_delay", 60.0)
            
            # Get hard stop configuration
            hard_stop_config = error_config.get("hard_stop_conditions", {})
            
            models_error_handler = ErrorHandler(max_retries=max_retries, base_delay=base_delay, max_delay=max_delay, 
                                             error_logger=error_logger, hard_stop_config=hard_stop_config)
            
            # Define the models request function
            def make_models_request():
                return proxy_client.forward_request(
                    request_data={},  # Empty for GET request
                    headers=dict(request.headers),
                    method="GET",
                    endpoint=""  # Use empty endpoint since models_url already includes /models
                )
            
            # Forward the request with error handling and context
            context = {
                "request_type": "models_request",
                "models_url": models_url,
                "timestamp": time.time()
            }
            
            response_data = models_error_handler.retry_with_backoff(make_models_request, context)
            
            end_time = time.time()
            duration = end_time - start_time
            
            logger.info(f"=== MODELS RESPONSE [{request_id}] ===")
            logger.info(f"Response: {json.dumps(response_data, indent=2)}")
            
            # Log complete request/response to file if enabled
            if request_logger:
                request_logger.log_complete_request(
                    request_id, "/models", {}, dict(request.headers), 
                    response_data, None, start_time, end_time, duration
                )
            
            return jsonify(response_data)
            
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            
            logger.error(f"=== ERROR FORWARDING MODELS REQUEST [{request_id}] ===")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error message: {str(e)}")
            
            # Log to error logger if available
            if error_logger:
                error_logger.log_error(e, {
                    "context": "models_request",
                    "request_id": request_id,
                    "duration": duration,
                    "endpoint": "/models",
                    "error_type": "models_request_error"
                })
            
            # Log complete request/error to file if enabled
            if request_logger:
                request_logger.log_complete_request(
                    request_id, "/models", {}, dict(request.headers), 
                    None, None, start_time, end_time, duration, e
                )
            
            # Return fallback models if target proxy fails
            return jsonify({
                "object": "list",
                "data": DEFAULT_MODELS
            })
            
    except Exception as e:
        logger.error(f"Error in models endpoint: {e}")
        
        # Log to error logger if available
        if error_logger:
            error_logger.log_error(e, {
                "context": "models_endpoint",
                "endpoint": "/models",
                "error_type": "models_endpoint_error"
            })
        
        return jsonify({"error": {"message": str(e)}}), 500


@app.route('/chat/completions', methods=['POST'])
def chat_completions():
    """Handle chat completion requests"""
    try:
        # Validate request
        if not request.is_json:
            return jsonify({"error": {"message": "Content-Type must be application/json"}}), 400
        
        try:
            request_data = request.get_json()
        except Exception as e:
            # Handle invalid JSON
            logger.error(f"Invalid JSON in request body: {e}")
            
            # Log to error logger if available
            if error_logger:
                error_logger.log_error(e, {
                    "context": "json_parsing",
                    "endpoint": "/chat/completions",
                    "error_type": "invalid_json",
                    "request_body": request.get_data(as_text=True)[:1000] if request else "unknown"
                })
            
            return jsonify({"error": {"message": "Invalid JSON in request body"}}), 400
        
        # Basic validation
        if not request_data:
            return jsonify({"error": {"message": "Request body is required"}}), 400
        
        if "messages" not in request_data:
            return jsonify({"error": {"message": "messages field is required"}}), 400
        
        # Apply regex replacements to messages if enabled
        regex_config = config.get_regex_replacement_config()
        if regex_config.get("enabled", False):
            rules = regex_config.get("rules", [])
            if rules:
                original_messages = request_data.get("messages", [])
                processed_messages = process_messages_with_regex(original_messages, rules)
                request_data = request_data.copy()
                request_data["messages"] = processed_messages
                

        
        # Generate unique request ID for tracking
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        
        # Log the full request details
        logger.info(f"=== INCOMING REQUEST [{request_id}] ===")
        logger.info(f"Request ID: {request_id}")
        logger.info(f"Model: {request_data.get('model', 'unknown')}")
        logger.info(f"Messages count: {len(request_data.get('messages', []))}")
        logger.info(f"Temperature: {request_data.get('temperature', 'default')}")
        logger.info(f"Max tokens: {request_data.get('max_tokens', 'default')}")
        logger.info(f"Stream: {request_data.get('stream', False)}")
        logger.info(f"Full request: {json.dumps(request_data, indent=2)}")
        logger.info(f"Headers: {sanitize_headers_for_logging(dict(request.headers))}")
        
        # Forward request with error handling
        try:
            logger.info(f"=== FORWARDING REQUEST [{request_id}] ===")
            # Forward headers from SillyTavern (including API keys)
            response_data = forward_request(request_data, headers=dict(request.headers))
            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"=== RESPONSE RECEIVED [{request_id}] ===")
            logger.info(f"Request duration: {duration:.2f} seconds")
            logger.info(f"Response type: {type(response_data)}")
            if isinstance(response_data, dict):
                logger.info(f"Response keys: {list(response_data.keys())}")
                if 'choices' in response_data:
                    logger.info(f"Choices count: {len(response_data['choices'])}")
                logger.info(f"Full response: {json.dumps(response_data, indent=2)}")
            
            # Log complete request/response to file if enabled
            if request_logger:
                request_logger.log_complete_request(
                    request_id, "/chat/completions", request_data, dict(request.headers),
                    response_data, None, start_time, end_time, duration
                )
            
            response = jsonify(response_data)
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            
            logger.error(f"=== ERROR FORWARDING REQUEST [{request_id}] ===")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error message: {str(e)}")
            # Format error response
            error_response = error_handler.format_exception_response(e)
            logger.error(f"Error response: {json.dumps(error_response, indent=2)}")
            
            # Log complete request/error to file if enabled
            if request_logger:
                request_logger.log_complete_request(
                    request_id, "/chat/completions", request_data, dict(request.headers),
                    error_response, None, start_time, end_time, duration, e
                )
            
            return jsonify(error_response), 502
            
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        
        # Log to error logger if available
        if error_logger:
            error_logger.log_error(e, {
                "context": "chat_completions_endpoint",
                "endpoint": "/chat/completions",
                "error_type": "chat_completions_endpoint_error"
            })
        
        return jsonify({"error": {"message": str(e)}}), 500


@app.errorhandler(400)
def bad_request(error):
    """Handle bad request errors including JSON parsing errors"""
    error_message = "Bad request"
    if "JSON" in str(error) or "json" in str(error).lower():
        error_message = "Invalid JSON in request body"
    
    # Log to error logger if available
    if error_logger:
        error_logger.log_error(400, {
            "context": "flask_error_handler",
            "error_type": "bad_request",
            "error_message": error_message,
            "request_path": request.path if request else "unknown",
            "request_method": request.method if request else "unknown"
        })
    
    return jsonify({"error": {"message": error_message}}), 400


@app.errorhandler(404)
def not_found(error):
    """Handle not found errors"""
    # Log to error logger if available
    if error_logger:
        error_logger.log_error(404, {
            "context": "flask_error_handler",
            "error_type": "not_found",
            "error_message": "Endpoint not found",
            "request_path": request.path if request else "unknown",
            "request_method": request.method if request else "unknown"
        })
    
    return jsonify({"error": {"message": "Endpoint not found"}}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle internal server errors"""
    # Log to error logger if available
    if error_logger:
        error_logger.log_error(500, {
            "context": "flask_error_handler",
            "error_type": "internal_error",
            "error_message": "Internal server error",
            "request_path": request.path if request else "unknown",
            "request_method": request.method if request else "unknown",
            "original_error": str(error)
        })
    
    return jsonify({"error": {"message": "Internal server error"}}), 500


if __name__ == '__main__':
    # Load configuration from the same directory as the script
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.yaml")
    config.load_from_file(config_path)
    config.load_from_environment()
    
    # Validate configuration
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        
        # Log to error logger if available (create temporary logger for startup errors)
        try:
            temp_error_logger = ErrorLogger(config._config)
            temp_error_logger.log_error(e, {
                "context": "configuration_validation",
                "error_type": "config_validation_error",
                "startup_error": True
            })
        except Exception as log_error:
            logger.error(f"Failed to log configuration error: {log_error}")
        
        exit(1)
    
    # Get server configuration
    server_config = config.get_server_config()
    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 5000)
    debug = server_config.get("debug", False)
    
    # Initialize RequestLogger and ErrorLogger
    logging_config = config.get_logging_config()
    error_logging_config = config.get_error_logging_config()
    
    # Initialize error logger independently
    if error_logging_config.get("enabled"):
        error_logger = ErrorLogger(config._config)
        logger.info(f"Error logging enabled. Error logs will be written to: {error_logging_config.get('folder', 'logs/errors')} folder")
    else:
        logger.info("Error logging is disabled in configuration")
        error_logger = None
    
    # Initialize request logger if general logging is enabled
    if logging_config.get("enabled"):
        request_logger = RequestLogger(config._config, error_logger=error_logger)
        logger.info(f"Unified request logging enabled. Logs will be written to: {logging_config.get('folder', 'logs')} folder")
    else:
        logger.info("Request logging is disabled in configuration")
        request_logger = None
    
    logger.info(f"Starting proxy middleware on {host}:{port}")
    app.run(host=host, port=port, debug=debug)
