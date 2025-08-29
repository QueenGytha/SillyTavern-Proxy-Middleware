"""
Utility functions for the seaking-proxy middleware
"""
import re
from typing import Dict, Any, List
from constants import SENSITIVE_HEADERS


def sanitize_headers_for_logging(headers: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize headers for logging by obfuscating sensitive values
    
    Args:
        headers: Dictionary of headers to sanitize
        
    Returns:
        Dictionary with sensitive header values obfuscated
    """
    sanitized = {}
    
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADERS:
            if value and len(str(value)) > 8:
                # Show first 8 characters + "..." for API keys
                sanitized[key] = f"{str(value)[:8]}..."
            else:
                sanitized[key] = "[REDACTED]"
        else:
            sanitized[key] = value
    return sanitized


def format_duration(start_time: float, end_time: float) -> str:
    """
    Format duration between two timestamps
    
    Args:
        start_time: Start timestamp
        end_time: End timestamp
        
    Returns:
        Formatted duration string
    """
    duration = end_time - start_time
    if duration < 1:
        return f"{duration * 1000:.0f}ms"
    elif duration < 60:
        return f"{duration:.2f}s"
    else:
        minutes = int(duration // 60)
        seconds = duration % 60
        return f"{minutes}m {seconds:.2f}s"


def truncate_text(text: str, max_length: int = 500) -> str:
    """
    Truncate text to specified length with ellipsis
    
    Args:
        text: Text to truncate
        max_length: Maximum length before truncation
        
    Returns:
        Truncated text with ellipsis if needed
    """
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def safe_json_dumps(obj: Any, default: str = "Unable to serialize") -> str:
    """
    Safely serialize object to JSON string
    
    Args:
        obj: Object to serialize
        default: Default string if serialization fails
        
    Returns:
        JSON string or default string
    """
    try:
        import json
        return json.dumps(obj, indent=2, default=str)
    except (TypeError, ValueError):
        return default


def apply_regex_replacements(text: str, rules: List[Dict[str, Any]]) -> str:
    """
    Apply regex replacement rules to text
    
    Args:
        text: Text to apply replacements to
        rules: List of replacement rules with pattern, replacement, flags, and apply_to
        
    Returns:
        Text with replacements applied
    """
    if not text or not rules:
        return text
    
    result = text
    
    for rule in rules:
        try:
            pattern = rule.get("pattern")
            replacement = rule.get("replacement", "")
            flags_str = rule.get("flags", "")
            apply_to = rule.get("apply_to", "all")
            
            if not pattern:
                continue
            
            # Convert flags string to re flags
            flags = 0
            if "i" in flags_str:
                flags |= re.IGNORECASE
            if "m" in flags_str:
                flags |= re.MULTILINE
            if "s" in flags_str:
                flags |= re.DOTALL
            if "x" in flags_str:
                flags |= re.VERBOSE
            
            # Apply the replacement
            result = re.sub(pattern, replacement, result, flags=flags)
            
        except (re.error, TypeError, ValueError) as e:
            # Log error but continue with other rules
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Invalid regex rule: {rule}, error: {e}")
            continue
    
    return result


def process_messages_with_regex(messages: List[Dict[str, Any]], rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Process messages with regex replacement rules
    
    Args:
        messages: List of message dictionaries with 'role' and 'content' keys
        rules: List of replacement rules
        
    Returns:
        List of messages with replacements applied
    """
    if not messages or not rules:
        return messages
    
    processed_messages = []
    
    for message in messages:
        role = message.get("role", "").lower()
        content = message.get("content", "")
        
        if not content:
            processed_messages.append(message)
            continue
        
        # Filter rules based on apply_to
        applicable_rules = []
        for rule in rules:
            apply_to = rule.get("apply_to", "all").lower()
            if apply_to == "all" or apply_to == role:
                applicable_rules.append(rule)
        
        # Apply regex replacements
        processed_content = apply_regex_replacements(content, applicable_rules)
        
        # Create new message with processed content
        processed_message = message.copy()
        processed_message["content"] = processed_content
        processed_messages.append(processed_message)
    
    return processed_messages
