# Monad Blockchain Automation Framework

A modular Python framework for automating tasks on the Monad blockchain network.

## Features

- **Modular Architecture**: Easily add new task types without changing existing code
- **Robust Error Handling**: Graceful recovery from network issues and transaction failures
- **Configuration Management**: Centralized settings with environment variable support
- **Transaction Management**: Efficient gas estimation and transaction confirmation
- **Extensible Task System**: Base classes for implementing custom blockchain operations

## Project Structure

```
monad_automation/
├── config/         # Configuration settings and environment loading
├── core/           # Core blockchain interaction components
├── tasks/          # Task implementation modules (DEX, NFT, etc.)
├── utils/          # Utility functions and helpers
└── tests/          # Test suite
```

## Installation

1. Clone the repository:

   ```
   git clone https://github.com/yourusername/monad-automation.git
   cd monad-automation
   ```

2. Create and activate a virtual environment:

   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the package in development mode:

   ```
   pip install -e ".[dev]"
   ```

4. Copy and configure environment variables:
   ```
   cp .env.example .env
   ```
   Edit `.env` with your specific configuration values.

## Usage

### Basic Usage

```python
from monad_automation.core.blockchain import MonadClient
from monad_automation.tasks.dex.swap import SwapTask

# Initialize the client
client = MonadClient.from_env()

# Create a task
swap_task = SwapTask(
    token_in="0x...",  # Token address to swap from
    token_out="0x...",  # Token address to swap to
    amount="1.0",      # Amount to swap
)

# Execute the task
result = swap_task.execute(client)
print(f"Swap completed. Transaction hash: {result.tx_hash}")
```

### Adding a New Task Type

1. Create a new module in the appropriate subdirectory under `tasks/`
2. Implement your task class extending the `BaseTask` class
3. Implement the required methods

Example:

```python
from monad_automation.tasks.base import BaseTask
from monad_automation.core.blockchain import MonadClient

class MyNewTask(BaseTask):
    def __init__(self, param1, param2):
        self.param1 = param1
        self.param2 = param2

    async def execute(self, client: MonadClient):
        # Implement your task logic here
        # Use client to interact with the blockchain
        pass
```

## Configuration

The framework uses a combination of environment variables and configuration files for settings.

Required environment variables:

- `MONAD_RPC_URL`: RPC endpoint for Monad
- `PRIVATE_KEY`: Your wallet's private key for signing transactions
- `WALLET_ADDRESS`: Your wallet address

Additional configuration can be set in `.env` file. See `.env.example` for all available options.

## Multiple Wallet Support

The framework includes robust multi-wallet management:

- **Add multiple wallets**: Add any number of wallets by name
- **Switch between wallets**: Easily change active wallet for operations
- **Watch-only wallets**: Track balances for addresses without private keys
- **Per-task wallet selection**: Specify which wallet to use for specific tasks
- **Secure storage**: Private keys are stored securely and never exposed

### Wallet CLI Commands

```bash
# List all wallets
python main.py wallets list

# Add a new wallet with private key
python main.py wallets add wallet_name --private-key 0x123...

# Add a watch-only wallet (address only)
python main.py wallets add watch_only --address 0xabc...

# Set active wallet
python main.py wallets set-active wallet_name

# Check wallet balance
python main.py wallets balance wallet_name
```

### Code Style

This project uses Black, isort, and flake8 for code formatting and linting:

```
black .
isort .
flake8
```

## Development

### Running Tests

```
pytest
```

Or with coverage:

```
pytest --cov=monad_automation
```

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
