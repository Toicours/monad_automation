"""
Exceptions for the Monad automation framework.
"""


class MonadError(Exception):
    """Base exception for all Monad automation errors."""
    pass


class BlockchainConnectionError(MonadError):
    """Error connecting to the blockchain."""
    pass


class TransactionError(MonadError):
    """Error when sending or processing a transaction."""
    pass


class ContractError(MonadError):
    """Error when interacting with a contract."""
    pass


class InsufficientFundsError(TransactionError):
    """Error when the wallet has insufficient funds."""
    pass


class WalletError(MonadError):
    """Error related to wallet operations."""
    pass


class TaskError(MonadError):
    """Base exception for task-related errors."""
    pass


class TaskExecutionError(TaskError):
    """Error during task execution."""
    pass


class TaskConfigurationError(TaskError):
    """Error in task configuration."""
    pass


class TaskNotFoundError(TaskError):
    """Error when a requested task is not found."""
    pass


class ValidationError(MonadError):
    """Error during data validation."""
    pass


class ConfigurationError(MonadError):
    """Error in configuration settings."""
    pass