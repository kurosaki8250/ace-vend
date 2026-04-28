"""
Memory system for Project Aether
Stores and manages conversation history
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from config.models import Message, Conversation
from utils.logger import get_logger


class Memory:
    """
    Simple conversation memory manager.
    
    Stores conversation history and provides retrieval methods.
    """
    
    def __init__(self, max_history: int = 50):
        """
        Initialize memory.
        
        Args:
            max_history: Maximum number of messages to retain per conversation
        """
        self.max_history = max_history
        self.logger = get_logger("aether.memory")
        
        # Store conversations by ID
        self.conversations: Dict[str, Conversation] = {}
        
        # Current active conversation
        self.current_conversation_id: Optional[str] = None
        
        self.logger.debug(f"Memory initialized with max_history={max_history}")
    
    def create_conversation(self) -> str:
        """
        Create a new conversation session.
        
        Returns:
            Conversation ID
        """
        conv_id = str(uuid.uuid4())
        conversation = Conversation(id=conv_id)
        self.conversations[conv_id] = conversation
        self.current_conversation_id = conv_id
        
        self.logger.debug(f"Created new conversation: {conv_id}")
        return conv_id
    
    def get_current_conversation(self) -> Optional[Conversation]:
        """Get the current active conversation."""
        if not self.current_conversation_id:
            return None
        return self.conversations.get(self.current_conversation_id)
    
    def add_message(self, role: str, content: str) -> Optional[Message]:
        """
        Add a message to the current conversation.
        
        Args:
            role: Message role ('user', 'assistant', or 'system')
            content: Message content
            
        Returns:
            The created Message object, or None if no active conversation
        """
        conversation = self.get_current_conversation()
        if not conversation:
            # Auto-create a conversation
            self.create_conversation()
            conversation = self.get_current_conversation()
        
        message = conversation.add_message(role, content)
        
        # Trim history if needed
        self._trim_history(conversation)
        
        self.logger.debug(f"Added {role} message to conversation")
        return message
    
    def _trim_history(self, conversation: Conversation):
        """Trim conversation history to max length."""
        if len(conversation.messages) > self.max_history:
            # Keep system messages and recent history
            system_messages = [
                m for m in conversation.messages if m.role == "system"
            ]
            other_messages = [
                m for m in conversation.messages if m.role != "system"
            ]
            
            # Keep most recent messages
            trimmed = other_messages[-(self.max_history - len(system_messages)):]
            conversation.messages = system_messages + trimmed
            
            self.logger.debug(f"Trimmed conversation history to {len(conversation.messages)} messages")
    
    def get_history(self) -> List[Dict[str, str]]:
        """
        Get conversation history as list of dicts.
        
        Returns:
            List of {role, content} dicts
        """
        conversation = self.get_current_conversation()
        if not conversation:
            return []
        
        return conversation.get_messages()
    
    def get_messages(self, limit: Optional[int] = None) -> List[Message]:
        """
        Get message objects from current conversation.
        
        Args:
            limit: Maximum number of messages to return (from most recent)
            
        Returns:
            List of Message objects
        """
        conversation = self.get_current_conversation()
        if not conversation:
            return []
        
        messages = conversation.messages
        if limit:
            messages = messages[-limit:]
        
        return messages
    
    def clear(self):
        """Clear the current conversation."""
        conversation = self.get_current_conversation()
        if conversation:
            conversation.clear()
            self.logger.debug("Cleared current conversation")
    
    def clear_all(self):
        """Clear all conversations."""
        self.conversations.clear()
        self.current_conversation_id = None
        self.logger.debug("Cleared all conversations")
    
    def switch_conversation(self, conv_id: str) -> bool:
        """
        Switch to a different conversation.
        
        Args:
            conv_id: Conversation ID to switch to
            
        Returns:
            True if successful, False if conversation not found
        """
        if conv_id in self.conversations:
            self.current_conversation_id = conv_id
            self.logger.debug(f"Switched to conversation: {conv_id}")
            return True
        
        self.logger.warning(f"Conversation not found: {conv_id}")
        return False
    
    def delete_conversation(self, conv_id: str) -> bool:
        """
        Delete a conversation.
        
        Args:
            conv_id: Conversation ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        if conv_id in self.conversations:
            del self.conversations[conv_id]
            
            # If deleting current, clear current reference
            if self.current_conversation_id == conv_id:
                self.current_conversation_id = None
            
            self.logger.debug(f"Deleted conversation: {conv_id}")
            return True
        
        return False
    
    def get_stats(self) -> Dict:
        """Get memory statistics."""
        total_messages = sum(
            len(conv.messages) for conv in self.conversations.values()
        )
        
        return {
            "total_conversations": len(self.conversations),
            "total_messages": total_messages,
            "current_conversation": self.current_conversation_id,
            "max_history_per_conversation": self.max_history
        }


# Global memory instance
memory = Memory()


def get_memory() -> Memory:
    """Get the global memory instance."""
    return memory
