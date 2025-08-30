# First-Hop Proxy

A proxy middleware for SillyTavern that provides advanced message processing, regex replacement, and comprehensive Unicode handling.

## Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure the Proxy**:
   ```bash
   cp config.yaml.example config.yaml
   # Edit config.yaml with your settings
   ```

3. **Run the Proxy**:
   ```bash
   python main.py
   ```

4. **Configure SillyTavern**:
   - Set API endpoint to `http://localhost:8765/chat/completions`
   - Use your remote proxy's API key

## Key Features

- **Message Processing**: Apply regex rules to outgoing messages
- **Response Processing**: Fix malformed Unicode and special characters
- **Comprehensive Unicode Handling**: Converts garbled characters back to proper Unicode
- **Flexible Configuration**: YAML-based rule management
- **Detailed Logging**: Request/response logging with debug information

## Documentation

📚 **Complete documentation is available in the [docs/](docs/) folder:**

- **[Documentation Index](docs/DOCUMENTATION_INDEX.md)**: Complete guide to all documentation
- **[Product Requirements](docs/PRD.md)**: Detailed specifications
- **[Configuration Guide](docs/REGEX_REPLACEMENT_GUIDE.md)**: How to configure regex rules
- **[Unicode Fix Documentation](docs/development/unicode-encoding-fix.md)**: Comprehensive Unicode handling solution

## Unicode Handling

The proxy includes robust Unicode handling to fix encoding issues from remote AI providers:

- **Fixes malformed Unicode sequences** like `\u00e2\u20ac"` → `—`
- **Converts literal garbled characters** like `â€"` → `—`
- **Handles all quote types, dashes, and special punctuation**
- **50+ comprehensive rules** for complete Unicode coverage

## Configuration

See [config.yaml.example](config.yaml.example) for complete configuration options.

## Testing

**✅ Test Suite Status: All 155 tests passing in ~3 seconds**

The test suite has been optimized for fast, reliable execution. All tests pass consistently with no freezing issues.

### Quick Test Commands

```bash
# Run all tests (recommended)
python3 run_tests.py

# Run specific test file
python3 run_tests.py tests/test_main.py

# Run tests with specific markers
python3 run_tests.py -m "not slow"

# Run with verbose output
python3 run_tests.py -v

# Stop on first failure
python3 run_tests.py -x
```

### Test Runner Features

The `run_tests.py` script provides:
- **Fast Execution**: ~3 seconds vs. potential 4.5 minutes
- **Automatic Mocking**: Prevents real network calls and delays
- **Environment Overrides**: Applies test-specific settings automatically
- **Pytest Integration**: Full compatibility with pytest features

### Test Coverage

- **155 total tests** across all modules
- **100% pass rate** with consistent execution
- **Comprehensive coverage** of core functionality
- **Robust error handling** and edge case testing

**Note**: While `python -m pytest` can work, using `python3 run_tests.py` is recommended for optimal performance and reliability.

## Support

For issues, questions, or contributions, please refer to the documentation in the [docs/](docs/) folder.
