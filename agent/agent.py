"""
Agent module for Project Aether
Main agent class that orchestrates LLM, memory, and tools
"""

import os
from pathlib import Path
from typing import List, Optional

from agent.llm import chat as llm_chat
from agent.memory import get_memory
from agent.tools import get_tool_registry
from config.models import Message
from utils.logger import get_logger
from utils.helpers import sanitize_input


class Agent:
    """
    Main AI Agent class.
    
    Orchestrates conversation flow:
    1. Load system prompt
    2. Append user input with conversation history
    3. Call LLM
    4. Store response in memory
    5. Return response
    """
    
    def __init__(self):
        """Initialize the agent."""
        self.logger = get_logger("aether.agent")
        self.memory = get_memory()
        self.tool_registry = get_tool_registry()
        
        # Load system prompt
        self.system_prompt = self._load_system_prompt()
        
        # Add system prompt to memory
        if self.system_prompt:
            self.memory.add_message("system", self.system_prompt)
        
        self.logger.info("Agent initialized")
    
    def _load_system_prompt(self) -> str:
        """
        Load system prompt from file.
        
        Tries optimized_prompt.txt first, falls back to base_prompt.txt.
        
        Returns:
            System prompt text
        """
        prompts_dir = Path(__file__).parent.parent / "prompts"
        
        # Try optimized prompt first
        optimized_path = prompts_dir / "optimized_prompt.txt"
        if optimized_path.exists():
            self.logger.debug(f"Loading optimized prompt from {optimized_path}")
            return optimized_path.read_text().strip()
        
        # Fall back to base prompt
        base_path = prompts_dir / "base_prompt.txt"
        if base_path.exists():
            self.logger.debug(f"Loading base prompt from {base_path}")
            return base_path.read_text().strip()
        
        # Default fallback
        self.logger.warning("No prompt files found, using default")
        return "You are a helpful AI assistant."
    
    def chat(self, user_input: str) -> str:
        """
        Process user input and return AI response.
        
        Args:
            user_input: User's message
            
        Returns:
            AI response text
        """
        # Sanitize input
        user_input = sanitize_input(user_input)
        
        if not user_input:
            return "Please provide a valid message."
        
        try:
            # Store user message in memory
            self.memory.add_message("user", user_input)
            
            # Get conversation history
            messages = self.memory.get_history()
            
            self.logger.debug(f"Sending {len(messages)} messages to LLM")
            
            # Call LLM
            response_text = llm_chat(messages)
            
            # Store assistant response in memory
            self.memory.add_message("assistant", response_text)
            
            self.logger.info(f"Successfully processed user message")
            
            return response_text
            
        except Exception as e:
            self.logger.error(f"Error in chat: {e}")
            return f"I encountered an error: {str(e)}"
    
    def clear_conversation(self):
        """Clear the current conversation history."""
        self.memory.clear()
        # Re-add system prompt
        if self.system_prompt:
            self.memory.add_message("system", self.system_prompt)
        self.logger.info("Conversation cleared")
    
    def get_conversation_history(self) -> List[dict]:
        """Get the current conversation history."""
        return self.memory.get_history()
    
    def get_available_tools(self) -> List[dict]:
        """Get list of available tools."""
        return self.tool_registry.list_tools()
    
    def execute_tool(self, tool_name: str, **kwargs):
        """Execute a tool by name."""
        return self.tool_registry.execute_tool(tool_name, **kwargs)


# Global agent instance
agent = Agent()


def get_agent() -> Agent:
    """Get the global agent instance."""
    return agent


def chat(user_input: str) -> str:
    """Convenience function to chat with the agent."""
    return agent.chat(user_input)
