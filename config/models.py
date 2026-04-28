"""
Data models for Project Aether
Pydantic-style data classes for type safety
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Message:
    """Represents a single message in a conversation."""
    role: str  # 'user', 'assistant', or 'system'
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary format for API calls."""
        return {
            "role": self.role,
            "content": self.content
        }


@dataclass
class Conversation:
    """Represents a conversation session."""
    id: str
    messages: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def add_message(self, role: str, content: str) -> Message:
        """Add a message to the conversation."""
        message = Message(role=role, content=content)
        self.messages.append(message)
        self.updated_at = datetime.now()
        return message
    
    def get_messages(self) -> List[Dict[str, str]]:
        """Get all messages as list of dicts."""
        return [msg.to_dict() for msg in self.messages]
    
    def clear(self):
        """Clear all messages."""
        self.messages = []
        self.updated_at = datetime.now()


@dataclass
class LLMResponse:
    """Represents an LLM response with metadata."""
    content: str
    model: str
    tokens_used: int = 0
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    
    def __str__(self) -> str:
        return self.content


@dataclass
class ToolResult:
    """Represents the result of a tool execution."""
    tool_name: str
    success: bool
    result: Any = None
    error: Optional[str] = None


@dataclass
class AgentState:
    """Represents the current state of an agent."""
    is_active: bool = True
    current_task: Optional[str] = None
    completed_tasks: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def mark_task_complete(self, task: str):
        """Mark a task as complete."""
        self.completed_tasks.append(task)
        self.current_task = None
    
    def add_error(self, error: str):
        """Record an error."""
        self.errors.append(error)
    
    def reset(self):
        """Reset agent state."""
        self.is_active = True
        self.current_task = None
        self.completed_tasks = []
        self.errors = []


@dataclass
class PromptTemplate:
    """Represents a prompt template."""
    name: str
    content: str
    variables: List[str] = field(default_factory=list)
    
    def render(self, **kwargs) -> str:
        """Render the template with provided variables."""
        try:
            return self.content.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing variable: {e}")
