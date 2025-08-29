# SillyTavern Proxy Middleware

A robust proxy middleware that acts as an intermediary between SillyTavern and external AI service proxies, providing comprehensive error handling, automatic retries, response parsing, and reliable communication with complete error logging.

## Features

- **OpenAI-Compatible API**: Supports standard OpenAI chat completion endpoints
- **Comprehensive Error Handling**: Sophisticated error detection and retry logic with 10 retry attempts
- **Response Parsing**: Intelligent response body parsing with status code recategorization
- **Hard Stop Conditions**: Prevent retries for specific error patterns
- **Complete Error Logging**: Every error and retry logged to `/logs/errors/` subfolder
- **Independent Error Logging**: Error logging can be enabled/disabled separately from general logging
- **Configurable**: Flexible configuration for target proxies and retry settings
- **Streaming Support**: Handles both streaming and non-streaming responses
- **Unified Request Logging**: Single log file per request with complete request/response cycle
- **Separate Error Logs**: Individual error logs for each error type with timestamps
- **Regex Message Processing**: Apply regex replacement rules to messages before forwarding
- **Test-Driven Development**: Full test coverage with comprehensive edge case testing
- **Security**: Automatic API key obfuscation and config file protection

## Architecture

```
SillyTavern → Proxy Middleware → Target Proxy → AI Service
```

The middleware provides:
- Request forwarding with header preservation
- Error handling with exponential backoff (up to 10 retries)
- Response parsing and status code recategorization
- Hard stop conditions for specific error patterns
- Retry logic for transient failures
- Response formatting and validation
- Comprehensive unified request/response logging
- **Independent error logging to `/logs/errors/` subfolder**
- Security features for sensitive data protection
- Regex message processing for content modification

## Installation

1. **Clone or download** the project files to your desired directory

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Create configuration file**:
```bash
cp config.yaml.example config.yaml
```

4. **REQUIRED**: Edit `config.yaml` and set your target proxy URL in the `target_proxy.url` field.

5. **Security Note**: Never commit your `config.yaml` file to version control as it may contain sensitive information.

## Configuration

The middleware uses a comprehensive configuration system. Copy `config.yaml.example` to `config.yaml` and customize:

```yaml
target_proxy:
  url: "https://your-target-proxy.com/proxy/your-service/chat/completions"
  timeout: 30

# Regex replacement rules applied to messages before forwarding
regex_replacement:
  enabled: true
  rules:
    - pattern: "hello"
      replacement: "hi"
      flags: "i"
      apply_to: "user"

# Response body parsing to recategorize status codes based on error messages
response_parsing:
  enabled: true
  status_recategorization:
    enabled: true
    rules:
      - pattern: "The model is overloaded"
        original_status: 200
        new_status: 429
        description: "Recategorize Google AI overload errors as rate limit"

error_handling:
  # HTTP status codes that should trigger retries (server errors and transient client errors)
  retry_codes: [429, 502, 503, 504, 505, 507, 508, 511, 408, 409, 410, 423, 424, 425, 426, 428, 431, 451]
  
  # HTTP status codes that should fail immediately (permanent client errors)
  fail_codes: [400, 401, 403, 405, 406, 407, 411, 412, 413, 414, 415, 416, 417, 418, 421, 422]
  
  # HTTP status codes that might be retryable depending on context (conditional retry)
  conditional_retry_codes: [404, 411, 412, 413, 414, 416, 417, 418, 421, 423, 424, 425, 426, 428, 431, 451]
  
  # Retry settings
  max_retries: 10  # Increased from default 3 for better reliability
  base_delay: 1
  max_delay: 60
  
  # Conditional retry settings
  conditional_retry_enabled: true
  conditional_retry_max_attempts: 2
  conditional_retry_delay_multiplier: 0.5

  # Hard stop conditions - prevent retries for specific error patterns
  hard_stop_conditions:
    enabled: true
    rules:
      - pattern: "googleAIBlockingResponseHandler.*Cannot read properties of undefined"
        description: "Downstream proxy middleware failure due to malformed message content"
        user_message: "Your previous message contains characters or formatting that is breaking the downstream AI provider. Please check for special characters, unusual formatting, or try rephrasing your message."
        preserve_original_response: true
        add_user_message: true

server:
  host: "0.0.0.0"
  port: 8765  # Default port for SillyTavern proxy
  debug: false

logging:
  enabled: true
  folder: "logs"
  include_request_data: true
  include_response_data: true
  include_headers: true
  include_timing: true

error_logging:
  enabled: true
  folder: "logs/errors"
  include_stack_traces: true
  include_request_context: true
  include_timing: true
  max_file_size_mb: 10
  max_files: 100
```

### Configuration Sections

#### Target Proxy Configuration
- **url**: Required target proxy service URL (e.g., Hugging Face Space, local service)
- **timeout**: Request timeout in seconds (default: 30)

#### Regex Replacement Configuration
- **enabled**: Enable/disable regex replacement processing
- **rules**: List of regex replacement rules to apply to messages
  - **pattern**: Regex pattern to match
  - **replacement**: Text to replace matches with
  - **flags**: Regex flags (i, m, s, x)
  - **apply_to**: Message roles to apply to (all, user, assistant, system)

#### Response Parsing Configuration
- **enabled**: Enable/disable response parsing and status recategorization
- **status_recategorization**: Rules for recategorizing status codes based on response content
  - **enabled**: Enable status recategorization
  - **rules**: List of recategorization rules
    - **pattern**: Text pattern to match in response
    - **original_status**: Original HTTP status code
    - **new_status**: New status code to use
    - **description**: Description of the rule
- **json_extraction**: JSON path extraction for nested error messages
- **logging**: Logging configuration for recategorization events

#### Error Handling Configuration
- **retry_codes**: HTTP status codes that trigger automatic retries (18 codes)
- **fail_codes**: HTTP status codes that fail immediately (16 codes)
- **conditional_retry_codes**: Status codes that may be retried based on context
- **max_retries**: Maximum retry attempts (now 10 for better reliability)
- **base_delay**: Initial retry delay in seconds
- **max_delay**: Maximum retry delay in seconds (exponential backoff cap)
- **conditional_retry_enabled**: Enable context-based retry logic
- **conditional_retry_max_attempts**: Max attempts for conditional retries
- **conditional_retry_delay_multiplier**: Shorter delays for conditional retries
- **hard_stop_conditions**: Prevent retries for specific error patterns
  - **enabled**: Enable hard stop conditions
  - **rules**: List of hard stop rules
    - **pattern**: Error pattern to match
    - **description**: Description of the condition
    - **user_message**: Optional user-friendly message to include
    - **preserve_original_response**: Keep original error response
    - **add_user_message**: Add user message to response

#### Logging Configuration
- **enabled**: Enable/disable request logging
- **folder**: Directory to store log files (default: "logs")
- **include_request_data**: Log full request data (default: true)
- **include_response_data**: Log full response data (default: true)
- **include_headers**: Log request/response headers (default: true)
- **include_timing**: Log timing information (default: true)

#### Error Logging Configuration
- **enabled**: Enable/disable error logging (independent of general logging)
- **folder**: Directory to store error log files (default: "logs/errors")
- **include_stack_traces**: Include full stack traces in error logs (default: true)
- **include_request_context**: Include request details in error logs (default: true)
- **include_timing**: Include timing information in error logs (default: true)
- **max_file_size_mb**: Maximum size per error log file in MB (default: 10)
- **max_files**: Maximum number of error log files to keep (default: 100)

## Usage

1. **Start the proxy middleware**:
```bash
python main.py
```

2. **Configure SillyTavern** to use the middleware:
   - Set the API endpoint to `http://localhost:8765`
   - Use standard OpenAI API format
   - The middleware will handle all communication with your target proxy

3. **Monitor logs**:
   - Request logs: `logs/` directory
   - Error logs: `logs/errors/` directory
   - Check error summary: `GET http://localhost:8765/logs/errors`

## API Endpoints

### POST /chat/completions
Handles chat completion requests in OpenAI format with comprehensive error handling and retry logic.

### GET /models
Returns available models list from target proxy with fallback to default models.

### GET /health
Basic health check endpoint.

### GET /health/detailed
Detailed health check with circuit breaker status and configuration.

### GET /logs/errors
Returns summary of error logs with file information and statistics.

## Error Handling

The middleware implements sophisticated error handling with **comprehensive logging to `/logs/errors/`**:

### **Retryable Errors** (18 status codes)
- **Server Errors**: 502, 503, 504, 505, 507, 508, 511
- **Rate Limiting**: 429
- **Transient Client Errors**: 408, 409, 410, 423, 424, 425, 426, 428, 431, 451
- **Retry Strategy**: Up to 10 attempts with exponential backoff

### **Non-Retryable Errors** (16 status codes)
- **Client Errors**: 400, 401, 403, 405, 406, 407, 411, 412, 413, 414, 415, 416, 417, 418, 421, 422
- **Immediate Failure**: No retry attempts, logged directly

### **Conditional Retries**
- **Context-Based**: 404, 411, 412, 413, 414, 416, 417, 418, 421, 423, 424, 425, 426, 428, 431, 451
- **Smart Logic**: Retry based on request type, endpoint, and context
- **Limited Attempts**: Maximum 2 attempts with shorter delays

### **Hard Stop Conditions**
- **Pattern Matching**: Prevent retries when specific error patterns are detected
- **User Messages**: Provide user-friendly error messages for specific conditions
- **Response Preservation**: Maintain original error responses when needed
- **Configurable Rules**: Define custom patterns and responses

### **Network Errors**
- **Connection Failures**: DNS resolution, connection timeouts
- **SSL/TLS Errors**: Certificate issues, SSL handshake failures
- **Content Errors**: JSON parsing, encoding issues

### **Response Parsing and Recategorization**
- **Status Recategorization**: Convert status codes based on response content
- **JSON Path Extraction**: Extract error messages from nested JSON structures
- **Pattern Matching**: Match error patterns in response bodies
- **Logging**: Comprehensive logging of recategorization events

## Response Parsing and Status Recategorization

The middleware includes intelligent response parsing that can recategorize HTTP status codes based on the actual content of error responses:

### **Status Recategorization**
Many AI services return 200 status codes even when errors occur, with error details in the response body. The response parser can:

- **Detect Error Patterns**: Match specific error messages in response bodies
- **Recategorize Status Codes**: Convert 200 responses to appropriate error codes (e.g., 429 for rate limits)
- **Extract Error Messages**: Parse nested JSON structures for error details
- **Log Recategorization Events**: Track when and why status codes are changed

### **Configuration Examples**
```yaml
response_parsing:
  enabled: true
  status_recategorization:
    enabled: true
    rules:
      # Google AI model overloaded errors
      - pattern: "The model is overloaded"
        original_status: 200
        new_status: 429
        description: "Recategorize Google AI overload errors as rate limit"
      
      # Generic service unavailable errors
      - pattern: "service unavailable"
        original_status: 200
        new_status: 429
        description: "Recategorize service unavailable as rate limit"
      
      # Proxy-wrapped errors
      - pattern: "HTTP 503 Service Unavailable"
        original_status: 200
        new_status: 503
        description: "Recategorize proxy-wrapped 503 errors"
```

### **JSON Path Extraction**
The parser can extract error messages from nested JSON structures:
```yaml
json_extraction:
  enabled: true
  paths:
    - "error.message"
    - "proxy_note"
    - "choices[0].finish_reason"
    - "choices[0].message.content"
```

## Hard Stop Conditions

Hard stop conditions prevent retries when specific error patterns are detected, providing immediate failure with user-friendly messages:

### **Configuration**
```yaml
hard_stop_conditions:
  enabled: true
  rules:
    # Stop retries for malformed message content
    - pattern: "googleAIBlockingResponseHandler.*Cannot read properties of undefined"
      description: "Downstream proxy middleware failure due to malformed message content"
      user_message: "Your previous message contains characters or formatting that is breaking the downstream AI provider. Please check for special characters, unusual formatting, or try rephrasing your message."
      preserve_original_response: true
      add_user_message: true
```

### **Features**
- **Pattern Matching**: Use regex patterns to match error messages
- **User Messages**: Provide helpful error messages to users
- **Response Preservation**: Keep original error details for debugging
- **Immediate Failure**: Skip retry logic for matched conditions

## Comprehensive Error Logging

**Error logging is now an independent setting** that can be enabled/disabled separately from general logging. When enabled, every error and retry is logged to `/logs/errors/` subfolder with detailed context:

### **Error Log Types**
1. **Basic Exceptions**: All caught exceptions throughout the application
2. **HTTP Errors**: 4xx/5xx status codes with full response details
3. **Retry Attempts**: Each retry with attempt number and delay
4. **Final Errors**: After all retries are exhausted
5. **Conditional Retry Errors**: Context-dependent retry failures
6. **Hard Stop Conditions**: When hard stop conditions are triggered
7. **Response Parsing Errors**: Status recategorization and parsing errors
8. **Proxy Client Errors**: Network, parsing, and response validation errors
9. **Request Logger Errors**: File system and permission errors
10. **Flask Error Handlers**: 400, 404, 500 errors
11. **Configuration Errors**: Startup validation errors
12. **JSON Parsing Errors**: Invalid request body errors
13. **Health Check Errors**: Health endpoint failures
14. **Endpoint-Specific Errors**: Errors in specific API endpoints
15. **Regex Processing Errors**: Invalid patterns and replacement failures

### **Error Log Format**
Each error log contains:
- **Header**: Error code, timestamp, and file information
- **Retry Information**: Attempt number, delay, context
- **Error Details**: JSON-formatted error context with full details
- **Rich Context**: Request details, timing, retry info, hard stop conditions

### **Error Log Management**
```bash
# View error logs
ls -la logs/errors/

# Monitor error logs in real-time
tail -f logs/errors/*.log

# Get error summary via API
curl http://localhost:8765/logs/errors

# Search for specific error types
grep -r "503" logs/errors/

# Check error logging configuration
curl http://localhost:8765/health/detailed
```

## Unified Logging

Each request is logged to a single file containing the complete request/response cycle:

- **Single File Per Request**: Timestamp-based naming with request ID
- **Complete Audit Trail**: Request data, response data, headers, timing
- **Security**: API keys automatically obfuscated
- **Error Tracking**: Full error details and stack traces
- **Performance Metrics**: Request duration and timing information

### Log File Format

#### Request Logs
Log files are named: `YYYYMMDD_HHMMSS_mmm_requestid.log`

Example log structure:
```
================================================================================
UNIFIED REQUEST LOG - 2024-08-30T14:30:45.123456
================================================================================
Request ID: a1b2c3d4
Endpoint: /chat/completions
Timestamp: 2024-08-30T14:30:45.123456
Start Time: 1735569045.123456

----------------------------------------
REQUEST HEADERS:
----------------------------------------
Content-Type: application/json
Authorization: Bearer sk-123456...
User-Agent: SillyTavern/1.0

----------------------------------------
REQUEST DATA:
----------------------------------------
{
  "model": "gpt-3.5-turbo",
  "messages": [
    {"role": "user", "content": "Hello, how are you?"}
  ],
  "temperature": 0.7,
  "max_tokens": 100
}

----------------------------------------
FINAL RESPONSE DATA:
----------------------------------------
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "choices": [
    {
      "message": {"role": "assistant", "content": "Hello! I'm doing well, thank you for asking."}
    }
  ]
}

----------------------------------------
TIMING INFORMATION:
----------------------------------------
End Time: 1735569046.234567
Total Duration: 1.111 seconds

================================================================================
LOG COMPLETE - 2024-08-30T14:30:46.234567
================================================================================
```

#### Error Logs
Error logs are stored in the `logs/errors/` directory and are named: `{error_code}_{YYYYMMDD_HHMMSS_mmm}.log`

Example error log structure:
```
================================================================================
ERROR LOG - 2024-08-30T14:30:45.123456
================================================================================
Error Code: 503
File: 503_20250830_143045_123.log

----------------------------------------
RETRY ATTEMPT #2
Retry Delay: 4.00 seconds
----------------------------------------

ERROR DETAILS:
----------------------------------------
{
  "timestamp": "2024-08-30T14:30:45.123456",
  "error_type": "HTTPResponse",
  "error_message": "HTTP 503",
  "status_code": 503,
  "status_text": "Service Unavailable",
  "url": "https://target-proxy.com/chat/completions",
  "headers": {
    "Content-Type": "application/json",
    "Server": "nginx/1.18.0"
  },
  "response_text": "The model is overloaded. Please try again later.",
  "context": {
    "request_type": "forward_request",
    "target_url": "https://target-proxy.com/chat/completions",
    "timestamp": 1735569045.123456
  },
  "retry_attempt": 2,
  "retry_delay": 4.0
}
```

## Security

### **Configuration Security**
- **Never commit `config.yaml`**: Contains sensitive information
- **Use `config.yaml.example`**: Template for setup
- **Environment variables**: Support for secure configuration
- **API key obfuscation**: Automatic masking in logs

### **Error Log Security**
- **Sensitive data protection**: API keys and tokens automatically obfuscated
- **Structured logging**: No sensitive data in error logs
- **Access control**: Error logs stored in separate directory
- **Independent control**: Error logging can be disabled independently of general logging
- **File management**: Automatic rotation and size limits for error log files

## Troubleshooting

### **Common Issues**

1. **Proxy not starting**
   - Check if port 8765 is available
   - Verify `config.yaml` exists and is valid
   - Check Python dependencies are installed

2. **Connection errors**
   - Verify target proxy URL is correct
   - Check network connectivity
   - Review error logs in `logs/errors/`

3. **High retry rates**
   - Check upstream service status
   - Review error logs for patterns
   - Consider adjusting retry settings

4. **Response parsing issues**
   - Check response parsing configuration
   - Review recategorization rules
   - Monitor response parsing logs

5. **Hard stop conditions triggering**
   - Review hard stop condition patterns
   - Check if error patterns match expected conditions
   - Adjust patterns if needed

### **Debug Commands**
```bash
# Check if proxy is running
curl http://localhost:8765/health

# Get detailed health status
curl http://localhost:8765/health/detailed

# View error logs summary
curl http://localhost:8765/logs/errors

# Monitor error logs in real-time
tail -f logs/errors/*.log

# Check request logs
ls -la logs/
```

### **Performance Monitoring**
- **Request duration**: Check timing in request logs
- **Error rates**: Monitor `/logs/errors/` directory
- **Response parsing**: Monitor recategorization events
- **Retry patterns**: Analyze error log patterns
- **Hard stop triggers**: Monitor hard stop condition matches

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=.

# Run specific test file
pytest tests/test_error_handler.py

# Run error logging tests
pytest tests/test_error_logger.py
```

## Development

This project follows Test-Driven Development (TDD):

1. Write tests first
2. Ensure tests fail
3. Implement minimum code to pass tests
4. Refactor while maintaining test coverage

### **Error Logging Development**
- All error scenarios are logged to `/logs/errors/` when error logging is enabled
- Independent error logging configuration for flexible deployment
- Comprehensive test coverage for error handling
- Error log format validation
- Performance testing for high-volume error logging
- File rotation and size management for error logs

## Contributing

1. Write tests for new features
2. Ensure all tests pass
3. Follow the existing code style
4. Update documentation as needed
5. Test error logging for new error scenarios

## License

This project is part of the SillyTavern ecosystem.
