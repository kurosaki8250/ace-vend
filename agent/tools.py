"""
Tools system for Project Aether
Provides callable tools that the agent can use
"""

import subprocess
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from config.models import ToolResult
from utils.logger import get_logger


class Tool:
    """Represents a callable tool."""
    
    def __init__(
        self,
        name: str,
        description: str,
        func: Callable[..., Any]
    ):
        """
        Initialize a tool.
        
        Args:
            name: Tool name
            description: What the tool does
            func: The function to call
        """
        self.name = name
        self.description = description
        self.func = func
    
    def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool.
        
        Args:
            **kwargs: Arguments to pass to the function
            
        Returns:
            ToolResult with success/failure info
        """
        try:
            result = self.func(**kwargs)
            return ToolResult(
                tool_name=self.name,
                success=True,
                result=result
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e)
            )


class ToolRegistry:
    """Registry of available tools."""
    
    def __init__(self):
        """Initialize the tool registry."""
        self.logger = get_logger("aether.tools")
        self.tools: Dict[str, Tool] = {}
        
        # Register built-in tools
        self._register_builtin_tools()
    
    def _register_builtin_tools(self):
        """Register built-in tools."""
        self.register_tool(Tool(
            name="get_current_time",
            description="Get the current date and time",
            func=self._get_current_time
        ))
        
        self.register_tool(Tool(
            name="calculate",
            description="Evaluate a mathematical expression",
            func=self._calculate
        ))
        
        self.register_tool(Tool(
            name="search_web",
            description="Search the web (simulated)",
            func=self._search_web
        ))
    
    def register_tool(self, tool: Tool):
        """
        Register a tool.
        
        Args:
            tool: Tool to register
        """
        self.tools[tool.name] = tool
        self.logger.debug(f"Registered tool: {tool.name}")
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self.tools.get(name)
    
    def list_tools(self) -> List[Dict[str, str]]:
        """List all available tools."""
        return [
            {"name": t.name, "description": t.description}
            for t in self.tools.values()
        ]
    
    def execute_tool(self, name: str, **kwargs) -> Optional[ToolResult]:
        """
        Execute a tool by name.
        
        Args:
            name: Tool name
            **kwargs: Arguments for the tool
            
        Returns:
            ToolResult or None if tool not found
        """
        tool = self.get_tool(name)
        if not tool:
            self.logger.warning(f"Tool not found: {name}")
            return None
        
        self.logger.debug(f"Executing tool: {name}")
        return tool.execute(**kwargs)
    
    # Built-in tool implementations
    
    @staticmethod
    def _get_current_time() -> str:
        """Get current date and time."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    @staticmethod
    def _calculate(expression: str) -> str:
        """
        Evaluate a mathematical expression safely.
        
        Args:
            expression: Math expression like "2 + 2"
            
        Returns:
            Result as string
        """
        try:
            # Only allow safe characters
            allowed_chars = set("0123456789+-*/.() ")
            if not all(c in allowed_chars for c in expression):
                return "Error: Invalid characters in expression"
            
            result = eval(expression, {"__builtins__": {}}, {})
            return str(result)
        except Exception as e:
            return f"Error: {str(e)}"
    
    @staticmethod
    def _search_web(query: str) -> str:
        """
        Simulated web search.
        
        In a real implementation, this would call a search API.
        
        Args:
            query: Search query
            
        Returns:
            Simulated search results
        """
        return (
            f"Web search is simulated in this demo. "
            f"Query was: '{query}'. "
            f"In production, integrate with Google/Bing API."
        )


# Global tool registry
tool_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry."""
    return tool_registry


def execute_tool(name: str, **kwargs) -> Optional[ToolResult]:
    """Convenience function to execute a tool."""
    return tool_registry.execute_tool(name, **kwargs)


def list_available_tools() -> List[Dict[str, str]]:
    """List all available tools."""
    return tool_registry.list_tools()
