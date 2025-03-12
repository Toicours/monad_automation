"""
Base task definitions for Monad automation.
"""
import abc
import time
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator

from ..core.blockchain import MonadClient
from ..core.exceptions import TaskConfigurationError, TaskExecutionError


class TaskResult(BaseModel):
    """Result of a task execution."""
    
    task_id: str = Field(..., description="Unique identifier for the task")
    task_name: str = Field(..., description="Name of the task")
    status: str = Field("success", description="Status of the task execution")
    tx_hash: Optional[str] = Field(None, description="Transaction hash if applicable")
    result_data: Dict[str, Any] = Field(default_factory=dict, description="Additional result data")
    error: Optional[str] = Field(None, description="Error message if task failed")
    execution_time: float = Field(..., description="Execution time in seconds")
    
    @validator("status")
    def validate_status(cls, v: str) -> str:
        """Validate that status is a valid value."""
        valid_statuses = ["success", "failed", "pending"]
        if v not in valid_statuses:
            raise ValueError(f"Status must be one of {valid_statuses}")
        return v

    def is_success(self) -> bool:
        """Check if the task execution was successful."""
        return self.status == "success"
    
    def __str__(self) -> str:
        """String representation of the task result."""
        if self.is_success():
            result = f"Task '{self.task_name}' completed successfully"
            if self.tx_hash:
                result += f" (tx: {self.tx_hash})"
        else:
            result = f"Task '{self.task_name}' failed: {self.error}"
        
        return result


class BaseTask(abc.ABC):
    """
    Base class for all tasks in the Monad automation framework.
    """
    
    def __init__(self, task_id: Optional[str] = None):
        """
        Initialize the task.
        
        Args:
            task_id: Optional unique identifier for the task
        """
        self.task_id = task_id or self._generate_task_id()
    
    @staticmethod
    def _generate_task_id() -> str:
        """Generate a unique task ID."""
        import uuid
        return str(uuid.uuid4())
    
    @property
    def task_name(self) -> str:
        """
        Get the task name.
        
        By default, this is the class name.
        """
        return self.__class__.__name__
    
    @abc.abstractmethod
    async def execute(self, client: MonadClient) -> Any:
        """
        Execute the task.
        
        Args:
            client: Monad client instance
            
        Returns:
            Any: Task-specific result
        """
        raise NotImplementedError("Subclasses must implement execute()")
    
    async def run(self, client: MonadClient) -> TaskResult:
        """
        Run the task with timing and error handling.
        
        Args:
            client: Monad client instance
            
        Returns:
            TaskResult: Result of the task execution
        """
        start_time = time.time()
        
        try:
            # Execute the task
            result = await self.execute(client)
            
            # Create a successful task result
            execution_time = time.time() - start_time
            
            task_result = TaskResult(
                task_id=self.task_id,
                task_name=self.task_name,
                status="success",
                execution_time=execution_time,
            )
            
            # Handle different types of results
            if isinstance(result, dict):
                task_result.result_data = result
                if "tx_hash" in result:
                    task_result.tx_hash = result["tx_hash"]
            elif isinstance(result, str) and result.startswith("0x"):
                # Assume it's a transaction hash
                task_result.tx_hash = result
            elif result is not None:
                # Store any other result type in result_data
                task_result.result_data = {"value": result}
            
            return task_result
            
        except Exception as e:
            # Create a failed task result
            execution_time = time.time() - start_time
            
            return TaskResult(
                task_id=self.task_id,
                task_name=self.task_name,
                status="failed",
                error=str(e),
                execution_time=execution_time,
            )
    
    def validate(self) -> None:
        """
        Validate that the task is properly configured.
        
        Raises:
            TaskConfigurationError: If the task is not properly configured
        """
        # Base implementation does no validation
        pass
    
    async def estimate_gas(self, client: MonadClient) -> int:
        """
        Estimate the gas required to execute the task.
        
        Args:
            client: Monad client instance
            
        Returns:
            int: Estimated gas
        """
        # Default implementation returns None, indicating that gas
        # should be estimated at execution time
        return None
    
    def __str__(self) -> str:
        """String representation of the task."""
        return f"{self.task_name}(id={self.task_id})"


class MultiTask(BaseTask):
    """
    A task that executes multiple subtasks.
    """
    
    def __init__(self, subtasks: List[BaseTask], task_id: Optional[str] = None):
        """
        Initialize the multi-task.
        
        Args:
            subtasks: List of subtasks to execute
            task_id: Optional unique identifier for the task
        """
        super().__init__(task_id)
        self.subtasks = subtasks
    
    @property
    def task_name(self) -> str:
        """Get the task name."""
        return f"MultiTask({len(self.subtasks)} subtasks)"
    
    async def execute(self, client: MonadClient) -> Dict[str, TaskResult]:
        """
        Execute all subtasks.
        
        Args:
            client: Monad client instance
            
        Returns:
            Dict[str, TaskResult]: Dictionary of subtask results
        """
        results = {}
        
        for subtask in self.subtasks:
            # Run the subtask
            result = await subtask.run(client)
            results[subtask.task_id] = result
            
            # Stop execution if a subtask fails
            if not result.is_success():
                break
        
        return {"subtask_results": results}
    
    def validate(self) -> None:
        """
        Validate that all subtasks are properly configured.
        
        Raises:
            TaskConfigurationError: If any subtask is not properly configured
        """
        for subtask in self.subtasks:
            try:
                subtask.validate()
            except TaskConfigurationError as e:
                raise TaskConfigurationError(
                    f"Validation failed for subtask {subtask}: {e}"
                )


class SequentialTask(MultiTask):
    """
    A task that executes multiple subtasks in sequence.
    """
    
    @property
    def task_name(self) -> str:
        """Get the task name."""
        return f"SequentialTask({len(self.subtasks)} subtasks)"


class ParallelTask(MultiTask):
    """
    A task that executes multiple subtasks in parallel.
    """
    
    @property
    def task_name(self) -> str:
        """Get the task name."""
        return f"ParallelTask({len(self.subtasks)} subtasks)"
    
    async def execute(self, client: MonadClient) -> Dict[str, TaskResult]:
        """
        Execute all subtasks in parallel.
        
        Args:
            client: Monad client instance
            
        Returns:
            Dict[str, TaskResult]: Dictionary of subtask results
        """
        import asyncio
        
        # Create tasks
        tasks = [subtask.run(client) for subtask in self.subtasks]
        
        # Run tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        subtask_results = {}
        for i, result in enumerate(results):
            subtask = self.subtasks[i]
            
            if isinstance(result, Exception):
                # Create a failed task result for exceptions
                subtask_results[subtask.task_id] = TaskResult(
                    task_id=subtask.task_id,
                    task_name=subtask.task_name,
                    status="failed",
                    error=str(result),
                    execution_time=0.0,
                )
            else:
                subtask_results[subtask.task_id] = result
        
        return {"subtask_results": subtask_results}