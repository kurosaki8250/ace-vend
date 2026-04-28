"""
LLM (Large Language Model) interface for Project Aether
Supports OpenAI API and optional local models (Ollama/Qwen)
"""

import time
from typing import Dict, List, Optional

import requests

from config.settings import get_settings
from utils.logger import get_logger, log_request, log_response, log_error


class LLMClient:
    """
    LLM client that supports multiple backends.
    
    Supports:
    - OpenAI API (default)
    - Local models via Ollama or compatible APIs
    """
    
    def __init__(self):
        """Initialize the LLM client."""
        self.settings = get_settings()
        self.logger = get_logger("aether.llm")
        
        self.model_name = self.settings.MODEL_NAME
        self.use_local = self.settings.USE_LOCAL_MODEL
        self.local_url = self.settings.LOCAL_MODEL_URL
        self.local_model = self.settings.LOCAL_MODEL_NAME
        self.api_key = self.settings.OPENAI_API_KEY
        self.max_tokens = self.settings.MAX_TOKENS
        self.temperature = self.settings.TEMPERATURE
        
        if not self.use_local and not self.api_key:
            self.logger.warning(
                "No API key configured. Set OPENAI_API_KEY in .env or enable USE_LOCAL_MODEL"
            )
    
    def chat(self, messages: List[Dict[str, str]]) -> str:
        """
        Send a chat request to the LLM.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            
        Returns:
            The assistant's response text
            
        Raises:
            RuntimeError: If no API key is configured
            requests.RequestException: If the API request fails
        """
        if self.use_local:
            return self._call_local(messages)
        else:
            return self._call_openai(messages)
    
    def _call_openai(self, messages: List[Dict[str, str]]) -> str:
        """
        Call OpenAI API.
        
        Args:
            messages: Conversation messages
            
        Returns:
            Assistant response
        """
        if not self.api_key:
            raise RuntimeError(
                "OpenAI API key not configured. "
                "Set OPENAI_API_KEY in .env file."
            )
        
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        # Log the request
        prompt_text = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        log_request(self.logger, self.model_name, prompt_text)
        
        start_time = time.time()
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            latency_ms = (time.time() - start_time) * 1000
            log_response(self.logger, content, latency_ms)
            
            return content
            
        except requests.exceptions.HTTPError as e:
            log_error(self.logger, e, f"HTTP error calling OpenAI API: {e.response.status_code}")
            if e.response.status_code == 401:
                raise RuntimeError("Invalid OpenAI API key") from e
            elif e.response.status_code == 429:
                raise RuntimeError("Rate limit exceeded") from e
            raise
        except requests.exceptions.Timeout:
            error = TimeoutError("Request timed out")
            log_error(self.logger, error, "OpenAI API request timed out")
            raise
        except Exception as e:
            log_error(self.logger, e, "Unexpected error calling OpenAI API")
            raise
    
    def _call_local(self, messages: List[Dict[str, str]]) -> str:
        """
        Call local model via Ollama-compatible API.
        
        Args:
            messages: Conversation messages
            
        Returns:
            Assistant response
        """
        url = f"{self.local_url}/api/chat"
        
        # Convert messages to Ollama format
        ollama_messages = []
        for msg in messages:
            ollama_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        payload = {
            "model": self.local_model,
            "messages": ollama_messages,
            "stream": False
        }
        
        prompt_text = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        log_request(self.logger, self.local_model, prompt_text)
        
        start_time = time.time()
        
        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            
            data = response.json()
            content = data.get("message", {}).get("content", "")
            
            latency_ms = (time.time() - start_time) * 1000
            log_response(self.logger, content, latency_ms)
            
            return content
            
        except requests.exceptions.ConnectionError as e:
            log_error(self.logger, e, f"Cannot connect to local model at {self.local_url}")
            raise RuntimeError(
                f"Cannot connect to local model at {self.local_url}. "
                "Make sure Ollama is running."
            ) from e
        except Exception as e:
            log_error(self.logger, e, "Error calling local model")
            raise


# Global LLM client instance
llm_client = LLMClient()


def get_llm_client() -> LLMClient:
    """Get the global LLM client instance."""
    return llm_client


def chat(messages: List[Dict[str, str]]) -> str:
    """
    Convenience function to send a chat request.
    
    Args:
        messages: List of message dicts
        
    Returns:
        Assistant response
    """
    return llm_client.chat(messages)
