"""
Configuration settings module for Monad Automation.
Loads environment variables and provides defaults.
"""
import os
from pathlib import Path
from typing import Optional, Dict, Any, Union

from dotenv import load_dotenv
from pydantic import BaseSettings, Field, validator, BaseModel

# Load .env file if it exists
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class NetworkConfig(BaseModel):
    """Configuration for a blockchain network."""
    name: str
    rpc_url: str
    chain_id: int
    explorer_url: Optional[str] = None
    symbol: str = "ETH"
    is_testnet: bool = False


class MonadSettings(BaseSettings):
    """Settings for Monad blockchain interaction."""

    # Network settings
    MONAD_RPC_URL: str = Field(..., description="Monad RPC endpoint URL")
    MONAD_CHAIN_ID: int = Field(2442, description="Monad chain ID")

    # Network configurations
    NETWORKS: Dict[str, Dict[str, Any]] = Field(
        default_factory=lambda: {
            "monad_mainnet": {
                "name": "Monad Mainnet",
                "rpc_url": "https://rpc.mainnet.monad.xyz/",
                "chain_id": 2440,
                "explorer_url": "https://explorer.monad.xyz",
                "symbol": "MONAD",
                "is_testnet": False
            },
            "monad_testnet": {
                "name": "Monad Testnet",
                "rpc_url": "https://rpc.testnet.monad.xyz/",
                "chain_id": 2442,
                "explorer_url": "https://explorer.testnet.monad.xyz",
                "symbol": "MONAD",
                "is_testnet": True
            }
        }
    )
    DEFAULT_NETWORK: str = Field("monad_testnet", description="Default network to use")

    # Wallet settings
    PRIVATE_KEY: str = Field(..., description="Private key for transaction signing")
    WALLET_ADDRESS: str = Field(..., description="Wallet address")

    # Gas settings
    GAS_LIMIT: int = Field(3000000, description="Default gas limit for transactions")
    GAS_PRICE: int = Field(10000000000, description="Default gas price in wei (10 gwei)")
    AUTO_GAS_MULTIPLIER: float = Field(1.1, description="Multiplier for auto gas estimation")

    # Contract addresses
    DEX_ROUTER_ADDRESS: Optional[str] = Field(None, description="DEX router contract address")
    NFT_MARKETPLACE_ADDRESS: Optional[str] = Field(None, description="NFT marketplace contract address")

    # API Keys
    ETHERSCAN_API_KEY: Optional[str] = Field(None, description="Etherscan API key")

    # Timeout settings
    REQUEST_TIMEOUT: int = Field(30, description="Timeout for RPC requests in seconds")
    TX_CONFIRMATION_TIMEOUT: int = Field(300, description="Timeout for transaction confirmations in seconds")
    TX_CONFIRMATION_BLOCKS: int = Field(2, description="Number of blocks to wait for confirmation")

    # Logging
    LOG_LEVEL: str = Field("INFO", description="Logging level")
    LOG_FILE: Optional[str] = Field(None, description="Log file path")

    # Retry settings
    MAX_RETRIES: int = Field(3, description="Maximum number of retries for operations")
    RETRY_DELAY: float = Field(1.0, description="Delay between retries in seconds")
    RETRY_BACKOFF: float = Field(2.0, description="Backoff multiplier for retries")

    @validator("PRIVATE_KEY")
    def validate_private_key(cls, v: str) -> str:
        """Validate that private key is properly formatted."""
        if v and not v.startswith("0x"):
            return f"0x{v}"
        return v
        
    @property
    def networks(self) -> Dict[str, NetworkConfig]:
        """Get all networks as NetworkConfig objects."""
        return {
            key: NetworkConfig(**value)
            for key, value in self.NETWORKS.items()
        }
    
    @property
    def active_network(self) -> NetworkConfig:
        """Get the active network configuration."""
        return self.networks[self.DEFAULT_NETWORK]
    
    def __init__(self, *args, **kwargs):
        """Initialize settings with environment variable overrides for networks."""
        super().__init__(*args, **kwargs)
        
        # Look for network overrides in environment variables
        for net_key, net_config in self.NETWORKS.items():
            prefix = f"NETWORKS_{net_key.upper()}_"
            
            for key in net_config.keys():
                env_key = f"{prefix}{key.upper()}"
                if env_key in os.environ:
                    self.NETWORKS[net_key][key] = os.environ[env_key]
                    
        # Individual RPC and chain ID settings still override the default network
        if hasattr(self, "MONAD_RPC_URL") and self.MONAD_RPC_URL:
            self.NETWORKS[self.DEFAULT_NETWORK]["rpc_url"] = self.MONAD_RPC_URL
            
        if hasattr(self, "MONAD_CHAIN_ID") and self.MONAD_CHAIN_ID:
            self.NETWORKS[self.DEFAULT_NETWORK]["chain_id"] = self.MONAD_CHAIN_ID

    class Config:
        env_file = ".env"
        case_sensitive = True


def get_settings() -> MonadSettings:
    """Get application settings instance."""
    return MonadSettings()


# Export settings instance
settings = get_settings()


def get_contract_addresses() -> Dict[str, str]:
    """Get a dictionary of all configured contract addresses."""
    addresses = {}
    for key, value in settings.dict().items():
        if key.endswith("_ADDRESS") and value:
            # Convert from SNAKE_CASE_ADDRESS to camelCase
            parts = key.replace("_ADDRESS", "").lower().split("_")
            name = parts[0] + "".join(p.capitalize() for p in parts[1:])
            addresses[name] = value
    return addresses