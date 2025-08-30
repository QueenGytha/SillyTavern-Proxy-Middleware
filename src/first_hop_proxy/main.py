"""
Main application module for First Hop Proxy
"""
import json
import logging
import uuid
import time
import sys
import os
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from requests.exceptions import HTTPError

from .config import Config
from .proxy_client import ProxyClient
from .error_handler import ErrorHandler
from .request_logger import RequestLogger
from .error_logger import ErrorLogger
from .utils import sanitize_headers_for_logging, process_messages_with_regex
from .constants import DEFAULT_MODELS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize components
config = Config()
# Only load config file if not in testing mode
if not os.environ.get('TESTING'):
    config.load_from_file("config.yaml")
error_handler = ErrorHandler()

# Global request logger - will be initialized after config is loaded
global request_logger
request_logger = None

# Global error logger - will be initialized after config is loaded
global error_logger
error_logger = None


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
        retry_codes = error_config.get("retry_codes", [429, 502, 503, 504])
        fail_codes = error_config.get("fail_codes", [400, 401, 403])
        conditional_retry_codes = error_config.get("conditional_retry_codes", [404, 411, 412])
        
        # Get hard stop configuration
        hard_stop_config = error_config.get("hard_stop_conditions", {})
        
        # Create error handler with configuration and error logger
        error_handler = ErrorHandler(
            max_retries=max_retries, 
            base_delay=base_delay, 
            max_delay=max_delay, 
            error_logger=error_logger, 
            hard_stop_config=hard_stop_config,
            retry_codes=retry_codes,
            fail_codes=fail_codes,
            conditional_retry_codes=conditional_retry_codes
        )
        
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
        error_config = config.get_error_handling_config()
        return jsonify({
            "status": "healthy",
            "retry_config": {
                "max_retries": error_config.get("max_retries", 10),
                "base_delay": error_config.get("base_delay", 1.0),
                "max_delay": error_config.get("max_delay", 60.0)
            }
        })
    except Exception as e:
        logger.error(f"Error in detailed health check: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


@app.route('/models', methods=['GET'])
def models_endpoint():
    """Models endpoint that forwards to target proxy"""
    try:
        # Get target proxy configuration
        proxy_config = config.get_target_proxy_config()
        target_url = proxy_config.get("url")
        if not target_url:
            raise ValueError("target_proxy.url is not configured")
        
        # Extract base URL by removing /chat/completions from the end
        base_url = target_url.replace("/chat/completions", "")
        models_url = f"{base_url}/models"
        
        # Create proxy client for models endpoint
        proxy_client = ProxyClient(models_url, config=config)
        
        # Create error handler for models request
        error_config = config.get_error_handling_config()
        max_retries = error_config.get("max_retries", 10)
        base_delay = error_config.get("base_delay", 1.0)
        max_delay = error_config.get("max_delay", 60.0)
        retry_codes = error_config.get("retry_codes", [429, 502, 503, 504])
        fail_codes = error_config.get("fail_codes", [400, 401, 403])
        conditional_retry_codes = error_config.get("conditional_retry_codes", [404, 411, 412])
        
        # Get hard stop configuration
        hard_stop_config = error_config.get("hard_stop_conditions", {})
        
        models_error_handler = ErrorHandler(
            max_retries=max_retries, 
            base_delay=base_delay, 
            max_delay=max_delay, 
            error_logger=error_logger, 
            hard_stop_config=hard_stop_config,
            retry_codes=retry_codes,
            fail_codes=fail_codes,
            conditional_retry_codes=conditional_retry_codes
        )
        
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
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error in models endpoint: {e}")
        
        # Return fallback models if target proxy fails
        from .constants import DEFAULT_MODELS
        return jsonify({
            "object": "list",
            "data": DEFAULT_MODELS
        })



@app.route('/chat/completions', methods=['POST'])
def chat_completions():
    """Chat completions endpoint"""
    try:
        # Get request data
        if not request.is_json:
            return jsonify({"error": {"message": "Content-Type must be application/json"}}), 400
        
        try:
            request_data = request.get_json()
        except Exception as e:
            return jsonify({"error": {"message": "Invalid JSON in request body"}}), 400
            
        if not request_data:
            return jsonify({"error": {"message": "No JSON data provided"}}), 400
        
        # Validate required fields
        if "messages" not in request_data:
            return jsonify({"error": {"message": "Missing required field: messages"}}), 400
        
        # Process messages with regex if configured
        if "messages" in request_data:
            regex_config = config.get_regex_replacement_config()
            if regex_config.get("enabled", False):
                rules = regex_config.get("rules", [])
                if rules:
                    request_data = request_data.copy()
                    request_data["messages"] = process_messages_with_regex(request_data["messages"], rules)
        
        # Forward the request
        result = forward_request(request_data, dict(request.headers))
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in chat completions: {e}")
        return jsonify({"error": {"message": str(e)}}), 500


def main():
    """Main entry point for the application"""
    try:
        # Initialize loggers
        global request_logger, error_logger
        
        # Initialize request logger
        request_logger = RequestLogger(config)
        
        # Initialize error logger
        error_logger = ErrorLogger(config)
        
        # Get server configuration
        server_config = config.get_server_config()
        host = server_config.get("host", "0.0.0.0")
        port = server_config.get("port", 5000)
        debug = server_config.get("debug", False)
        
        logger.info(f"Starting First Hop Proxy server on {host}:{port}")
        app.run(host=host, port=port, debug=debug)
        
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
