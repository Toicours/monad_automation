"""
Task package for Monad Automation.
"""
from .base import (
    BaseTask,
    TaskResult,
    MultiTask,
    SequentialTask,
    ParallelTask,
)

__all__ = [
    "BaseTask",
    "TaskResult",
    "MultiTask",
    "SequentialTask",
    "ParallelTask",
]