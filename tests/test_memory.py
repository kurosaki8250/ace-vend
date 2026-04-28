"""
Tests for Project Aether Memory module
"""

import pytest


class TestMemoryBasic:
    """Basic memory tests."""
    
    def test_memory_init(self):
        """Test memory initialization."""
        from agent.memory import Memory
        
        memory = Memory()
        assert memory is not None
        assert memory.max_history == 50
    
    def test_memory_custom_max_history(self):
        """Test memory with custom max history."""
        from agent.memory import Memory
        
        memory = Memory(max_history=10)
        assert memory.max_history == 10


class TestConversationManagement:
    """Test conversation management features."""
    
    def test_create_conversation(self):
        """Test creating a new conversation."""
        from agent.memory import Memory
        
        memory = Memory()
        conv_id = memory.create_conversation()
        
        assert conv_id is not None
        assert len(conv_id) > 0
        assert memory.current_conversation_id == conv_id
    
    def test_get_current_conversation(self):
        """Test getting current conversation."""
        from agent.memory import Memory
        
        memory = Memory()
        memory.create_conversation()
        
        conv = memory.get_current_conversation()
        assert conv is not None
        assert len(conv.messages) == 0
    
    def test_switch_conversation(self):
        """Test switching between conversations."""
        from agent.memory import Memory
        
        memory = Memory()
        conv1 = memory.create_conversation()
        conv2 = memory.create_conversation()
        
        # Switch to first conversation
        result = memory.switch_conversation(conv1)
        assert result is True
        assert memory.current_conversation_id == conv1
        
        # Try invalid conversation
        result = memory.switch_conversation("invalid-id")
        assert result is False


class TestMessageOperations:
    """Test message operations."""
    
    def test_add_user_message(self):
        """Test adding user message."""
        from agent.memory import Memory
        
        memory = Memory()
        memory.create_conversation()
        
        msg = memory.add_message("user", "Hello")
        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "Hello"
    
    def test_add_assistant_message(self):
        """Test adding assistant message."""
        from agent.memory import Memory
        
        memory = Memory()
        memory.create_conversation()
        
        msg = memory.add_message("assistant", "Hi there!")
        assert msg.role == "assistant"
    
    def test_add_system_message(self):
        """Test adding system message."""
        from agent.memory import Memory
        
        memory = Memory()
        memory.create_conversation()
        
        msg = memory.add_message("system", "You are helpful.")
        assert msg.role == "system"


class TestHistoryRetrieval:
    """Test history retrieval."""
    
    def test_get_empty_history(self):
        """Test getting empty history."""
        from agent.memory import Memory
        
        memory = Memory()
        memory.create_conversation()
        
        history = memory.get_history()
        assert history == []
    
    def test_get_history_with_messages(self):
        """Test getting history with messages."""
        from agent.memory import Memory
        
        memory = Memory()
        memory.create_conversation()
        
        memory.add_message("user", "Hello")
        memory.add_message("assistant", "Hi!")
        
        history = memory.get_history()
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
    
    def test_get_messages_with_limit(self):
        """Test getting messages with limit."""
        from agent.memory import Memory
        
        memory = Memory()
        memory.create_conversation()
        
        for i in range(5):
            memory.add_message("user", f"Message {i}")
        
        messages = memory.get_messages(limit=2)
        assert len(messages) == 2


class TestClearOperations:
    """Test clear operations."""
    
    def test_clear_current_conversation(self):
        """Test clearing current conversation."""
        from agent.memory import Memory
        
        memory = Memory()
        memory.create_conversation()
        
        memory.add_message("user", "Hello")
        memory.clear()
        
        history = memory.get_history()
        assert len(history) == 0
    
    def test_clear_all_conversations(self):
        """Test clearing all conversations."""
        from agent.memory import Memory
        
        memory = Memory()
        memory.create_conversation()
        memory.create_conversation()
        
        memory.clear_all()
        
        assert len(memory.conversations) == 0
        assert memory.current_conversation_id is None


class TestMemoryStats:
    """Test memory statistics."""
    
    def test_get_stats(self):
        """Test getting memory stats."""
        from agent.memory import Memory
        
        memory = Memory()
        memory.create_conversation()
        memory.add_message("user", "Hello")
        
        stats = memory.get_stats()
        
        assert "total_conversations" in stats
        assert "total_messages" in stats
        assert stats["total_conversations"] >= 1
        assert stats["total_messages"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
