"""
Core blockchain interaction module for Monad.
"""
import time
import os
from typing import Dict, Optional, Union, Any, Tuple, List

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress, HexStr
from web3 import Web3
from web3.contract import Contract
from web3.middleware import construct_sign_and_send_raw_middleware, geth_poa_middleware
from web3.types import TxParams, Wei, TxReceipt

from config import settings
from core.exceptions import (
    TransactionError,
    ContractError,
    BlockchainConnectionError,
    InsufficientFundsError,
    ConfigurationError,
)


class MonadClient:
    """Client for interacting with the Monad blockchain."""

    def __init__(
        self,
        rpc_url: str,
        chain_id: int,
    ):
        """
        Initialize the Monad client.

        Args:
            rpc_url: The RPC endpoint URL
            chain_id: The blockchain chain ID
        """
        self.rpc_url = rpc_url
        self.chain_id = chain_id
        
        # Initialize Web3 connection
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": settings.REQUEST_TIMEOUT}))
        
        # Add middleware for POA chains if needed
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Initialize account and wallet address (will be set by wallet manager)
        self.account = None
        self.wallet_address = None
            
        # Initialize wallet manager (circular reference, set later)
        self.wallet = None
        
        # Validate connection
        if not self.is_connected():
            raise BlockchainConnectionError(f"Failed to connect to Monad blockchain at {rpc_url}")

    @classmethod
    def from_env(cls, network_name: Optional[str] = None) -> "MonadClient":
        """
        Create a MonadClient instance from environment variables.

        Args:
            network_name: Name of the network to use (defaults to DEFAULT_NETWORK in settings)
            
        Returns:
            MonadClient: Configured client instance
        """
        from .wallet import WalletManager  # Import here to avoid circular import
        
        # Get network configuration
        network_name = network_name or settings.DEFAULT_NETWORK
        if network_name not in settings.networks:
            raise ConfigurationError(f"Network {network_name} not found in settings")
            
        network = settings.networks[network_name]
        
        # Create client
        client = cls(
            rpc_url=network.rpc_url,
            chain_id=network.chain_id,
        )
        
        # Set network name
        client.network_name = network_name
        
        # Create wallet manager
        wallet_manager = WalletManager(client)
        client.wallet = wallet_manager
        
        # Load existing wallets
        wallet_manager.load_wallets()
        
        # Add default wallet if specified in environment
        default_wallet_name = os.getenv("DEFAULT_WALLET_NAME")
        default_private_key = os.getenv("DEFAULT_PRIVATE_KEY")
        
        if default_wallet_name and default_private_key:
            try:
                # Add wallet if it doesn't already exist
                if default_wallet_name not in wallet_manager.wallets:
                    wallet_manager.add_wallet_from_private_key(
                        name=default_wallet_name,
                        private_key=default_private_key
                    )
                
                # Set as active wallet
                wallet_manager.set_active_wallet(default_wallet_name)
            except Exception as e:
                print(f"Error setting up default wallet: {e}")
        
        return client

    def set_account(self, account: LocalAccount) -> None:
        """
        Set the account for the client.
        
        Args:
            account: eth_account.LocalAccount instance
        """
        self.account = account
        
        # Update middleware for signing transactions
        # Remove existing middleware first to avoid duplicates
        self.w3.middleware_onion.remove('sign_and_send_raw')
        
        # Add new middleware
        self.w3.middleware_onion.add(
            construct_sign_and_send_raw_middleware(account),
            name='sign_and_send_raw'
        )

    def is_connected(self) -> bool:
        """
        Check if the client is connected to the blockchain.

        Returns:
            bool: True if connected, False otherwise
        """
        try:
            return self.w3.is_connected()
        except Exception:
            return False

    def get_contract(self, address: str, abi: List[Dict[str, Any]]) -> Contract:
        """
        Get a contract instance.

        Args:
            address: Contract address
            abi: Contract ABI

        Returns:
            Contract: Web3 contract instance
        """
        try:
            address = self.w3.to_checksum_address(address)
            return self.w3.eth.contract(address=address, abi=abi)
        except Exception as e:
            raise ContractError(f"Failed to create contract instance: {e}")

    async def get_gas_price(self) -> int:
        """
        Get current gas price with multiplier applied.

        Returns:
            int: Gas price in wei
        """
        try:
            gas_price = self.w3.eth.gas_price
            return int(gas_price * settings.AUTO_GAS_MULTIPLIER)
        except Exception as e:
            # Fall back to default if gas price estimation fails
            return settings.GAS_PRICE

    async def estimate_gas(self, tx_params: TxParams) -> int:
        """
        Estimate gas for a transaction.

        Args:
            tx_params: Transaction parameters

        Returns:
            int: Estimated gas
        """
        try:
            gas = self.w3.eth.estimate_gas(tx_params)
            return int(gas * settings.AUTO_GAS_MULTIPLIER)
        except Exception as e:
            # Use default gas limit if estimation fails
            return settings.GAS_LIMIT

    async def prepare_transaction(
        self,
        to: str,
        value: int = 0,
        data: Optional[HexStr] = None,
        gas_limit: Optional[int] = None,
        gas_price: Optional[int] = None,
        nonce: Optional[int] = None,
    ) -> TxParams:
        """
        Prepare a transaction with all necessary parameters.

        Args:
            to: Recipient address
            value: Amount in wei
            data: Transaction data
            gas_limit: Gas limit (estimated if None)
            gas_price: Gas price (estimated if None)
            nonce: Transaction nonce (auto-increment if None)

        Returns:
            TxParams: Complete transaction parameters
        """
        if not self.wallet_address:
            raise ValueError("No active wallet set")

        # Create base transaction
        tx = {
            "from": self.wallet_address,
            "to": self.w3.to_checksum_address(to),
            "value": value,
            "chainId": self.chain_id,
        }

        # Add transaction data if provided
        if data:
            tx["data"] = data

        # Set or estimate gas price
        if gas_price is None:
            tx["gasPrice"] = await self.get_gas_price()
        else:
            tx["gasPrice"] = gas_price

        # Set or estimate gas limit
        if gas_limit is None:
            tx["gas"] = await self.estimate_gas(tx)
        else:
            tx["gas"] = gas_limit

        # Set or get nonce
        if nonce is None:
            tx["nonce"] = self.w3.eth.get_transaction_count(self.wallet_address)
        else:
            tx["nonce"] = nonce

        return tx

    async def send_transaction(self, tx_params: TxParams) -> HexStr:
        """
        Send a transaction to the network.

        Args:
            tx_params: Transaction parameters

        Returns:
            HexStr: Transaction hash
        """
        if not self.account:
            raise ValueError("No active wallet with private key set")

        try:
            # Check sufficient balance
            balance = self.w3.eth.get_balance(self.wallet_address)
            required = tx_params.get("value", 0) + (tx_params.get("gas", 0) * tx_params.get("gasPrice", 0))
            
            if balance < required:
                raise InsufficientFundsError(
                    f"Insufficient funds: have {balance} wei, need {required} wei"
                )

            # Send the transaction
            tx_hash = self.w3.eth.send_transaction(tx_params)
            return tx_hash.hex()
            
        except InsufficientFundsError:
            raise
        except Exception as e:
            raise TransactionError(f"Failed to send transaction: {e}")

    async def wait_for_transaction_receipt(
        self, tx_hash: HexStr, timeout: Optional[int] = None, poll_interval: float = 0.1
    ) -> TxReceipt:
        """
        Wait for a transaction receipt.

        Args:
            tx_hash: Transaction hash
            timeout: Timeout in seconds
            poll_interval: Polling interval in seconds

        Returns:
            TxReceipt: Transaction receipt
        """
        timeout = timeout or settings.TX_CONFIRMATION_TIMEOUT
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    if receipt.status == 1:
                        return receipt
                    else:
                        raise TransactionError(
                            f"Transaction {tx_hash} failed: {receipt}"
                        )
            except TransactionError:
                raise
            except Exception:
                # Transaction not yet mined, continue waiting
                pass
                
            time.sleep(poll_interval)
            
        raise TransactionError(f"Transaction {tx_hash} timed out after {timeout} seconds")

    def decode_contract_function_input(self, contract: Contract, transaction_input: str) -> Tuple[Any, Dict[str, Any]]:
        """
        Decode the input data of a contract function call.

        Args:
            contract: Web3 contract instance
            transaction_input: Input data from transaction

        Returns:
            Tuple containing the function object and decoded parameters
        """
        try:
            return contract.decode_function_input(transaction_input)
        except Exception as e:
            raise ContractError(f"Failed to decode contract function input: {e}")

    def get_eth_balance(self, address: Optional[str] = None) -> float:
        """
        Get ETH balance for an address.

        Args:
            address: Address to check (defaults to active wallet address)

        Returns:
            float: Balance in ETH
        """
        address = address or self.wallet_address
        if not address:
            raise ValueError("No address provided and no active wallet set")
            
        try:
            balance_wei = self.w3.eth.get_balance(address)
            return self.w3.from_wei(balance_wei, "ether")
        except Exception as e:
            raise BlockchainConnectionError(f"Failed to get balance: {e}")
            
    def get_transaction_count(self, address: Optional[str] = None) -> int:
        """
        Get the transaction count (nonce) for an address.
        
        Args:
            address: Address to check (defaults to active wallet address)
            
        Returns:
            int: Transaction count
        """
        address = address or self.wallet_address
        if not address:
            raise ValueError("No address provided and no active wallet set")
            
        try:
            return self.w3.eth.get_transaction_count(address)
        except Exception as e:
            raise BlockchainConnectionError(f"Failed to get transaction count: {e}")