"""
Helper utilities for Project Aether
"""

import re
from typing import Any, Dict, List, Optional


def sanitize_input(text: str) -> str:
    """
    Sanitize user input by removing potentially harmful characters.
    
    Args:
        text: Raw user input
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    # Remove null bytes and control characters (except newlines/tabs)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text


def truncate_text(text: str, max_length: int = 1000, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def format_prompt(prompt_template: str, **kwargs: Any) -> str:
    """
    Format a prompt template with provided variables.
    
    Args:
        prompt_template: Template string with {variable} placeholders
        **kwargs: Variables to substitute
        
    Returns:
        Formatted prompt
    """
    try:
        return prompt_template.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Missing variable in prompt template: {e}")


def parse_json_response(text: str) -> Optional[Dict]:
    """
    Attempt to parse JSON from a response string.
    
    Args:
        text: Response text that may contain JSON
        
    Returns:
        Parsed JSON dict or None if parsing fails
    """
    import json
    
    # Try direct parsing first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON from markdown code blocks
    json_pattern = r'```(?:json)?\s*({.*?})\s*```'
    match = re.search(json_pattern, text, re.DOTALL)
    
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    return None


def split_messages(conversation: List[Dict]) -> str:
    """
    Convert a list of message dicts to a formatted string.
    
    Args:
        conversation: List of {role, content} dicts
        
    Returns:
        Formatted conversation string
    """
    lines = []
    for msg in conversation:
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    
    return "\n\n".join(lines)


def is_valid_api_key(key: str) -> bool:
    """
    Check if an API key looks valid.
    
    Args:
        key: API key string
        
    Returns:
        True if key appears valid
    """
    if not key:
        return False
    
    # OpenAI keys start with 'sk-'
    if key.startswith("sk-"):
        return len(key) >= 20
    
    # Generic check for non-empty key
    return len(key) >= 10
