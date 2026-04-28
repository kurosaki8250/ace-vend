"""
Configuration settings for Project Aether
Loads environment variables and provides configuration access
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv


class Settings:
    """
    Configuration settings manager.
    Loads settings from .env file and environment variables.
    """
    
    def __init__(self, env_path: Optional[str] = None):
        """
        Initialize settings.
        
        Args:
            env_path: Path to .env file (default: .env in project root)
        """
        if env_path is None:
            # Look for .env in project root
            env_path = Path(__file__).parent.parent / ".env"
        
        # Load environment variables
        load_dotenv(env_path)
        
        # Configuration values
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
        self.MODEL_NAME: str = os.getenv("MODEL_NAME", "gpt-4o-mini")
        self.USE_LOCAL_MODEL: bool = os.getenv("USE_LOCAL_MODEL", "false").lower() == "true"
        self.LOCAL_MODEL_URL: str = os.getenv("LOCAL_MODEL_URL", "http://localhost:11434")
        self.LOCAL_MODEL_NAME: str = os.getenv("LOCAL_MODEL_NAME", "qwen2.5:7b")
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
        self.MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "1024"))
        self.TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.7"))
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        return {
            "OPENAI_API_KEY": self.OPENAI_API_KEY,
            "MODEL_NAME": self.MODEL_NAME,
            "USE_LOCAL_MODEL": self.USE_LOCAL_MODEL,
            "LOCAL_MODEL_URL": self.LOCAL_MODEL_URL,
            "LOCAL_MODEL_NAME": self.LOCAL_MODEL_NAME,
            "LOG_LEVEL": self.LOG_LEVEL,
            "MAX_TOKENS": self.MAX_TOKENS,
            "TEMPERATURE": self.TEMPERATURE,
        }
    
    def validate(self) -> list:
        """
        Validate current settings.
        
        Returns:
            List of validation error messages
        """
        errors = []
        
        if not self.OPENAI_API_KEY and not self.USE_LOCAL_MODEL:
            errors.append(
                "OPENAI_API_KEY is not set and local model is not enabled. "
                "Please set OPENAI_API_KEY in .env file or enable USE_LOCAL_MODEL."
            )
        
        if self.USE_LOCAL_MODEL and not self.LOCAL_MODEL_URL:
            errors.append("LOCAL_MODEL_URL is required when using local models")
        
        return errors
    
    def is_configured(self) -> bool:
        """Check if settings are properly configured."""
        if self.USE_LOCAL_MODEL:
            return bool(self.LOCAL_MODEL_URL)
        return bool(self.OPENAI_API_KEY)


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings


def reload_settings(env_path: Optional[str] = None) -> Settings:
    """Reload settings from .env file."""
    global settings
    settings = Settings(env_path)
    return settings
