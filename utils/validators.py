"""
Validator utilities for Project Aether
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


def validate_api_key(api_key: str) -> Tuple[bool, str]:
    """
    Validate an API key.
    
    Args:
        api_key: The API key to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not api_key:
        return False, "API key is empty"
    
    if not isinstance(api_key, str):
        return False, "API key must be a string"
    
    api_key = api_key.strip()
    
    if len(api_key) < 10:
        return False, "API key is too short"
    
    # Check for OpenAI key format
    if api_key.startswith("sk-"):
        if len(api_key) < 20:
            return False, "OpenAI API key appears incomplete"
        return True, ""
    
    # Generic key validation
    if re.match(r'^[a-zA-Z0-9_-]+$', api_key):
        return True, ""
    
    return False, "API key contains invalid characters"


def validate_model_name(model_name: str) -> Tuple[bool, str]:
    """
    Validate a model name.
    
    Args:
        model_name: The model name to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not model_name:
        return False, "Model name is empty"
    
    if not isinstance(model_name, str):
        return False, "Model name must be a string"
    
    model_name = model_name.strip()
    
    if len(model_name) < 2:
        return False, "Model name is too short"
    
    # Basic pattern check
    if not re.match(r'^[a-zA-Z0-9._:-]+$', model_name):
        return False, "Model name contains invalid characters"
    
    return True, ""


def validate_url(url: str) -> Tuple[bool, str]:
    """
    Validate a URL.
    
    Args:
        url: The URL to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url:
        return False, "URL is empty"
    
    if not isinstance(url, str):
        return False, "URL must be a string"
    
    url = url.strip()
    
    # Basic URL pattern
    url_pattern = re.compile(
        r'^https?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )
    
    if url_pattern.match(url):
        return True, ""
    
    return False, "Invalid URL format"


def validate_config(config: Dict[str, Any]) -> List[str]:
    """
    Validate a configuration dictionary.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    # Check required fields
    required_fields = ["OPENAI_API_KEY", "MODEL_NAME"]
    for field in required_fields:
        if field not in config:
            errors.append(f"Missing required config field: {field}")
    
    # Validate API key if present
    if "OPENAI_API_KEY" in config:
        is_valid, msg = validate_api_key(config["OPENAI_API_KEY"])
        if not is_valid and config["OPENAI_API_KEY"] != "your_key_here":
            errors.append(f"Invalid OPENAI_API_KEY: {msg}")
    
    # Validate model name if present
    if "MODEL_NAME" in config:
        is_valid, msg = validate_model_name(config["MODEL_NAME"])
        if not is_valid:
            errors.append(f"Invalid MODEL_NAME: {msg}")
    
    # Validate USE_LOCAL_MODEL if present
    if "USE_LOCAL_MODEL" in config:
        if not isinstance(config["USE_LOCAL_MODEL"], bool):
            if config["USE_LOCAL_MODEL"] not in ["true", "false", "True", "False"]:
                errors.append("USE_LOCAL_MODEL must be a boolean")
    
    return errors


def validate_input(text: str, max_length: int = 4000) -> Tuple[bool, str]:
    """
    Validate user input.
    
    Args:
        text: User input text
        max_length: Maximum allowed length
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not text:
        return False, "Input is empty"
    
    if not isinstance(text, str):
        return False, "Input must be a string"
    
    text = text.strip()
    
    if len(text) == 0:
        return False, "Input is empty after stripping whitespace"
    
    if len(text) > max_length:
        return False, f"Input exceeds maximum length of {max_length} characters"
    
    return True, ""
