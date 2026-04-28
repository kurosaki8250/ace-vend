"""
Tests for Project Aether Agent module
"""

import pytest


class TestAgent:
    """Test cases for the Agent class."""
    
    def test_agent_initialization(self):
        """Test that agent initializes correctly."""
        from agent.agent import get_agent
        
        agent = get_agent()
        assert agent is not None
        assert hasattr(agent, 'chat')
        assert hasattr(agent, 'clear_conversation')
    
    def test_agent_chat_method_exists(self):
        """Test that chat method exists and is callable."""
        from agent.agent import Agent
        
        agent = Agent()
        assert callable(agent.chat)
    
    def test_agent_response_not_empty(self):
        """Test that agent returns a response (may be error if no API key)."""
        from agent.agent import chat
        
        # This will work if API key is configured, otherwise return error message
        response = chat("Hello")
        assert isinstance(response, str)
        assert len(response) > 0


class TestMemory:
    """Test cases for the Memory class."""
    
    def test_memory_creation(self):
        """Test memory initialization."""
        from agent.memory import Memory
        
        memory = Memory()
        assert memory is not None
    
    def test_add_message(self):
        """Test adding messages to memory."""
        from agent.memory import Memory
        
        memory = Memory()
        memory.create_conversation()
        
        message = memory.add_message("user", "Hello")
        assert message is not None
        assert message.content == "Hello"
        assert message.role == "user"
    
    def test_get_history(self):
        """Test retrieving conversation history."""
        from agent.memory import Memory
        
        memory = Memory()
        memory.create_conversation()
        
        memory.add_message("user", "Hello")
        memory.add_message("assistant", "Hi there!")
        
        history = memory.get_history()
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
    
    def test_clear_conversation(self):
        """Test clearing conversation."""
        from agent.memory import Memory
        
        memory = Memory()
        memory.create_conversation()
        
        memory.add_message("user", "Hello")
        memory.clear()
        
        history = memory.get_history()
        assert len(history) == 0


class TestLLM:
    """Test cases for the LLM client."""
    
    def test_llm_client_initialization(self):
        """Test LLM client initializes."""
        from agent.llm import LLMClient
        
        client = LLMClient()
        assert client is not None
    
    def test_llm_chat_method_exists(self):
        """Test that chat method exists."""
        from agent.llm import LLMClient
        
        client = LLMClient()
        assert hasattr(client, 'chat')
        assert callable(client.chat)
    
    def test_llm_without_api_key_raises_error(self):
        """Test that calling LLM without API key raises appropriate error."""
        from agent.llm import LLMClient
        from config.settings import Settings
        
        # Create settings without API key
        import os
        original_key = os.environ.get("OPENAI_API_KEY", "")
        os.environ["OPENAI_API_KEY"] = ""
        
        try:
            client = LLMClient()
            # Should raise RuntimeError when no API key
            with pytest.raises(RuntimeError):
                client.chat([{"role": "user", "content": "Hello"}])
        finally:
            if original_key:
                os.environ["OPENAI_API_KEY"] = original_key


class TestTools:
    """Test cases for the Tools system."""
    
    def test_tool_registry_initialization(self):
        """Test tool registry initializes with built-in tools."""
        from agent.tools import ToolRegistry
        
        registry = ToolRegistry()
        assert len(registry.tools) > 0
    
    def test_calculate_tool(self):
        """Test the calculate tool."""
        from agent.tools import execute_tool
        
        result = execute_tool("calculate", expression="2 + 2")
        assert result is not None
        assert result.success is True
        assert result.result == "4"
    
    def test_time_tool(self):
        """Test the get_current_time tool."""
        from agent.tools import execute_tool
        from datetime import datetime
        
        result = execute_tool("get_current_time")
        assert result is not None
        assert result.success is True
        # Verify it's a valid datetime string
        datetime.strptime(result.result, "%Y-%m-%d %H:%M:%S")
    
    def test_list_tools(self):
        """Test listing available tools."""
        from agent.tools import list_available_tools
        
        tools = list_available_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        
        # Check structure
        for tool in tools:
            assert "name" in tool
            assert "description" in tool


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
