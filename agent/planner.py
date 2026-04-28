"""
Planner module for Project Aether
Handles task planning and decomposition
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from utils.logger import get_logger


@dataclass
class Task:
    """Represents a single task."""
    id: str
    description: str
    status: str = "pending"  # pending, in_progress, completed, failed
    result: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)


class Planner:
    """
    Task planner for breaking down complex requests.
    
    Note: This is a foundational implementation ready for extension.
    Currently provides basic task tracking.
    """
    
    def __init__(self):
        """Initialize the planner."""
        self.logger = get_logger("aether.planner")
        self.tasks: Dict[str, Task] = {}
        self.current_plan: List[str] = []
    
    def create_task(self, description: str, dependencies: Optional[List[str]] = None) -> str:
        """
        Create a new task.
        
        Args:
            description: Task description
            dependencies: List of task IDs this task depends on
            
        Returns:
            Task ID
        """
        import uuid
        task_id = str(uuid.uuid4())[:8]
        
        task = Task(
            id=task_id,
            description=description,
            dependencies=dependencies or []
        )
        
        self.tasks[task_id] = task
        self.current_plan.append(task_id)
        
        self.logger.debug(f"Created task {task_id}: {description}")
        return task_id
    
    def start_task(self, task_id: str) -> bool:
        """Mark a task as in progress."""
        if task_id not in self.tasks:
            return False
        
        self.tasks[task_id].status = "in_progress"
        self.logger.debug(f"Started task {task_id}")
        return True
    
    def complete_task(self, task_id: str, result: str) -> bool:
        """Mark a task as completed with a result."""
        if task_id not in self.tasks:
            return False
        
        self.tasks[task_id].status = "completed"
        self.tasks[task_id].result = result
        self.logger.debug(f"Completed task {task_id}")
        return True
    
    def fail_task(self, task_id: str, error: str) -> bool:
        """Mark a task as failed."""
        if task_id not in self.tasks:
            return False
        
        self.tasks[task_id].status = "failed"
        self.tasks[task_id].result = f"Error: {error}"
        self.logger.warning(f"Failed task {task_id}: {error}")
        return True
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return self.tasks.get(task_id)
    
    def get_pending_tasks(self) -> List[Task]:
        """Get all pending tasks."""
        return [t for t in self.tasks.values() if t.status == "pending"]
    
    def can_execute(self, task_id: str) -> bool:
        """Check if a task's dependencies are satisfied."""
        task = self.get_task(task_id)
        if not task:
            return False
        
        for dep_id in task.dependencies:
            dep_task = self.get_task(dep_id)
            if not dep_task or dep_task.status != "completed":
                return False
        
        return True
    
    def get_plan_status(self) -> Dict:
        """Get current plan status."""
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks.values() if t.status == "completed")
        failed = sum(1 for t in self.tasks.values() if t.status == "failed")
        pending = total - completed - failed
        
        return {
            "total_tasks": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "progress_percent": (completed / total * 100) if total > 0 else 0
        }
    
    def clear(self):
        """Clear all tasks and plans."""
        self.tasks.clear()
        self.current_plan.clear()
        self.logger.debug("Cleared planner")


# Global planner instance
planner = Planner()


def get_planner() -> Planner:
    """Get the global planner instance."""
    return planner
