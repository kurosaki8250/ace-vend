"""
Tests for Project Aether LLM module
"""

import pytest


class TestLLMClient:
    """Test cases for LLM client."""
    
    def test_llm_client_creation(self):
        """Test creating LLM client instance."""
        from agent.llm import LLMClient
        
        client = LLMClient()
        assert client is not None
    
    def test_llm_has_settings(self):
        """Test that LLM client has settings loaded."""
        from agent.llm import LLMClient
        
        client = LLMClient()
        assert hasattr(client, 'settings')
        assert client.settings is not None
    
    def test_llm_model_name_default(self):
        """Test default model name."""
        from agent.llm import LLMClient
        
        client = LLMClient()
        # Should have a model name configured (default or from env)
        assert client.model_name is not None
        assert len(client.model_name) > 0
    
    def test_chat_method_signature(self):
        """Test chat method accepts correct parameters."""
        from agent.llm import LLMClient
        
        client = LLMClient()
        messages = [{"role": "user", "content": "Hello"}]
        
        # Method should exist and be callable
        assert callable(client.chat)
        
        # Without API key, should raise RuntimeError
        if not client.api_key and not client.use_local:
            with pytest.raises(RuntimeError):
                client.chat(messages)


class TestLocalModelConfig:
    """Test local model configuration."""
    
    def test_local_model_settings_exist(self):
        """Test that local model settings are available."""
        from config.settings import get_settings
        
        settings = get_settings()
        assert hasattr(settings, 'USE_LOCAL_MODEL')
        assert hasattr(settings, 'LOCAL_MODEL_URL')
        assert hasattr(settings, 'LOCAL_MODEL_NAME')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
