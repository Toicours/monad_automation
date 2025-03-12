"""
Wallet management module for Monad blockchain interaction.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Union, Any, Tuple

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress, HexStr
from web3 import Web3
from web3.contract import Contract
from web3.types import TxParams, Wei, TxReceipt

from ..config import settings
from .exceptions import InsufficientFundsError, WalletError

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .blockchain import MonadClient

class Wallet:
    """Individual wallet for blockchain interactions."""
    
    def __init__(
        self, 
        name: str,
        address: str,
        private_key: Optional[str] = None,
        account: Optional[LocalAccount] = None
    ):
        """
        Initialize a wallet.
        
        Args:
            name: Wallet name/identifier
            address: Wallet address
            private_key: Private key (optional if account is provided)
            account: eth_account.LocalAccount instance (optional if private_key is provided)
        """
        self.name = name
        self.address = Web3.to_checksum_address(address)
        self._private_key = private_key
        
        if account:
            self.account = account
        elif private_key:
            self.account = Account.from_key(private_key)
        else:
            self.account = None
            
    @classmethod
    def from_private_key(cls, name: str, private_key: str) -> "Wallet":
        """
        Create a wallet from a private key.
        
        Args:
            name: Wallet name/identifier
            private_key: Private key
            
        Returns:
            Wallet: Configured wallet instance
        """
        if not private_key.startswith("0x"):
            private_key = f"0x{private_key}"
            
        account = Account.from_key(private_key)
        
        return cls(
            name=name,
            address=account.address,
            private_key=private_key,
            account=account
        )
    
    @classmethod
    def from_mnemonic(cls, name: str, mnemonic: str, path: str = "m/44'/60'/0'/0/0") -> "Wallet":
        """
        Create a wallet from a mnemonic phrase.
        
        Args:
            name: Wallet name/identifier
            mnemonic: BIP39 mnemonic phrase
            path: Derivation path
            
        Returns:
            Wallet: Configured wallet instance
        """
        account = Account.from_mnemonic(mnemonic, account_path=path)
        
        return cls(
            name=name,
            address=account.address,
            private_key=account.key.hex(),
            account=account
        )
        
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert wallet to a dictionary for serialization.
        
        Returns:
            Dict[str, Any]: Wallet details
        """
        return {
            "name": self.name,
            "address": self.address,
            "private_key": self._private_key if self._private_key else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Wallet":
        """
        Create a wallet from a dictionary.
        
        Args:
            data: Dictionary with wallet details
            
        Returns:
            Wallet: Configured wallet instance
        """
        if data.get("private_key"):
            return cls.from_private_key(
                name=data["name"],
                private_key=data["private_key"]
            )
        else:
            return cls(
                name=data["name"],
                address=data["address"]
            )
    
    def has_private_key(self) -> bool:
        """
        Check if wallet has a private key.
        
        Returns:
            bool: True if wallet has a private key
        """
        return self._private_key is not None
    
    def __str__(self) -> str:
        return f"Wallet({self.name}: {self.address})"


class WalletManager:
    """Manager for multiple blockchain wallets."""

    def __init__(self, client: "MonadClient"):
        """
        Initialize the wallet manager.

        Args:
            client: Initialized MonadClient instance
        """
        self.client = client
        self.wallets: Dict[str, Wallet] = {}
        self.active_wallet_name: Optional[str] = None
        
        # Load wallet directory if specified
        self.wallet_directory = os.getenv("WALLET_DIRECTORY", "wallets")
        
        # Initialize wallet directory if it doesn't exist
        if self.wallet_directory:
            os.makedirs(self.wallet_directory, exist_ok=True)
    
    @property
    def active_wallet(self) -> Optional[Wallet]:
        """Get the currently active wallet."""
        if not self.active_wallet_name:
            return None
        return self.wallets.get(self.active_wallet_name)
    
    def load_wallets(self) -> None:
        """Load wallets from the wallet directory."""
        if not self.wallet_directory or not os.path.exists(self.wallet_directory):
            return
            
        wallet_files = Path(self.wallet_directory).glob("*.wallet")
        for wallet_file in wallet_files:
            try:
                with open(wallet_file, "r") as f:
                    wallet_data = json.load(f)
                    wallet = Wallet.from_dict(wallet_data)
                    self.add_wallet(wallet)
            except Exception as e:
                print(f"Error loading wallet {wallet_file}: {e}")
    
    def save_wallet(self, wallet_name: str) -> None:
        """
        Save a wallet to the wallet directory.
        
        Args:
            wallet_name: Name of the wallet to save
        """
        if not self.wallet_directory:
            return
            
        wallet = self.wallets.get(wallet_name)
        if not wallet:
            raise WalletError(f"Wallet not found: {wallet_name}")
            
        wallet_path = Path(self.wallet_directory) / f"{wallet_name}.wallet"
        
        with open(wallet_path, "w") as f:
            json.dump(wallet.to_dict(), f, indent=2)
    
    def add_wallet(self, wallet: Wallet) -> None:
        """
        Add a wallet to the manager.
        
        Args:
            wallet: Wallet to add
        """
        self.wallets[wallet.name] = wallet
        
        # Set as active if it's the first wallet
        if len(self.wallets) == 1:
            self.set_active_wallet(wallet.name)
            
        # Save wallet to file
        self.save_wallet(wallet.name)
    
    def add_wallet_from_private_key(self, name: str, private_key: str) -> Wallet:
        """
        Add a wallet from a private key.
        
        Args:
            name: Wallet name/identifier
            private_key: Private key
            
        Returns:
            Wallet: The added wallet
        """
        wallet = Wallet.from_private_key(name, private_key)
        self.add_wallet(wallet)
        return wallet
    
    def add_wallet_from_mnemonic(self, name: str, mnemonic: str, path: str = "m/44'/60'/0'/0/0") -> Wallet:
        """
        Add a wallet from a mnemonic phrase.
        
        Args:
            name: Wallet name/identifier
            mnemonic: BIP39 mnemonic phrase
            path: Derivation path
            
        Returns:
            Wallet: The added wallet
        """
        wallet = Wallet.from_mnemonic(name, mnemonic, path)
        self.add_wallet(wallet)
        return wallet
    
    def remove_wallet(self, name: str) -> None:
        """
        Remove a wallet from the manager.
        
        Args:
            name: Name of the wallet to remove
        """
        if name not in self.wallets:
            raise WalletError(f"Wallet not found: {name}")
            
        # If we're removing the active wallet, clear the active wallet
        if self.active_wallet_name == name:
            self.active_wallet_name = None
            
        # Remove from memory
        del self.wallets[name]
        
        # Remove wallet file if it exists
        if self.wallet_directory:
            wallet_path = Path(self.wallet_directory) / f"{name}.wallet"
            if wallet_path.exists():
                wallet_path.unlink()
    
    def set_active_wallet(self, name: str) -> None:
        """
        Set the active wallet.
        
        Args:
            name: Name of the wallet to set as active
        """
        if name not in self.wallets:
            raise WalletError(f"Wallet not found: {name}")
            
        self.active_wallet_name = name
        
        # If wallet has a private key, update the client's account
        active_wallet = self.active_wallet
        if active_wallet and active_wallet.has_private_key():
            self.client.set_account(active_wallet.account)
            
        # Always update the client's wallet address
        self.client.wallet_address = active_wallet.address
    
    def list_wallets(self) -> List[Dict[str, Any]]:
        """
        List all available wallets.
        
        Returns:
            List[Dict[str, Any]]: List of wallet details
        """
        return [
            {
                "name": name,
                "address": wallet.address,
                "has_private_key": wallet.has_private_key(),
                "is_active": name == self.active_wallet_name
            }
            for name, wallet in self.wallets.items()
        ]
    
    def get_wallet(self, name: str) -> Wallet:
        """
        Get a wallet by name.
        
        Args:
            name: Wallet name/identifier
            
        Returns:
            Wallet: The requested wallet
        """
        if name not in self.wallets:
            raise WalletError(f"Wallet not found: {name}")
            
        return self.wallets[name]

    async def get_balance(self, token_address: Optional[str] = None, wallet_name: Optional[str] = None) -> Union[float, int]:
        """
        Get wallet balance for a token.

        Args:
            token_address: Token contract address (None for native ETH)
            wallet_name: Name of the wallet to check (defaults to active wallet)

        Returns:
            Union[float, int]: Balance in token units
        """
        wallet = self._get_wallet_for_operation(wallet_name)

        if token_address is None:
            # Native token (ETH) balance
            return self.client.get_eth_balance(wallet.address)
        else:
            # ERC20 token balance
            return await self._get_erc20_balance(token_address, wallet.address)

    async def _get_erc20_balance(self, token_address: str, wallet_address: str) -> float:
        """
        Get ERC20 token balance.

        Args:
            token_address: Token contract address
            wallet_address: Address to check balance for

        Returns:
            float: Token balance in token units
        """
        # ERC20 standard ABI for balanceOf function
        abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function",
            },
        ]

        try:
            token_contract = self.client.get_contract(token_address, abi)
            balance = token_contract.functions.balanceOf(wallet_address).call()
            
            # Get token decimals for human-readable format
            decimals = token_contract.functions.decimals().call()
            
            return balance / (10 ** decimals)
        except Exception as e:
            raise WalletError(f"Failed to get token balance: {e}")

    async def transfer(
        self,
        to_address: str,
        amount: Union[int, float],
        token_address: Optional[str] = None,
        gas_limit: Optional[int] = None,
        gas_price: Optional[int] = None,
        wallet_name: Optional[str] = None,
    ) -> str:
        """
        Transfer tokens to another address.

        Args:
            to_address: Recipient address
            amount: Amount to transfer
            token_address: Token contract address (None for native ETH)
            gas_limit: Gas limit
            gas_price: Gas price
            wallet_name: Name of the wallet to use (defaults to active wallet)

        Returns:
            str: Transaction hash
        """
        wallet = self._get_wallet_for_operation(wallet_name)
        
        # Temporarily set the active wallet if needed
        original_active = self.active_wallet_name
        if wallet.name != original_active:
            self.set_active_wallet(wallet.name)
        
        try:
            if token_address is None:
                # Native token (ETH) transfer
                result = await self._transfer_eth(to_address, amount, gas_limit, gas_price)
            else:
                # ERC20 token transfer
                result = await self._transfer_erc20(token_address, to_address, amount, gas_limit, gas_price)
                
            return result
        finally:
            # Restore the original active wallet if we changed it
            if wallet.name != original_active and original_active is not None:
                self.set_active_wallet(original_active)

    async def _transfer_eth(
        self, to_address: str, amount: Union[int, float], gas_limit: Optional[int], gas_price: Optional[int]
    ) -> str:
        """
        Transfer native ETH to another address.

        Args:
            to_address: Recipient address
            amount: Amount to transfer in ETH
            gas_limit: Optional gas limit
            gas_price: Optional gas price

        Returns:
            str: Transaction hash
        """
        # Convert ETH to Wei
        amount_wei = self.client.w3.to_wei(amount, "ether")
        
        # Check balance
        balance = self.client.w3.eth.get_balance(self.client.wallet_address)
        if balance < amount_wei:
            raise InsufficientFundsError(
                f"Insufficient ETH balance: have {self.client.w3.from_wei(balance, 'ether')} ETH, need {amount} ETH"
            )
        
        # Prepare and send transaction
        tx_params = await self.client.prepare_transaction(
            to=to_address,
            value=amount_wei,
            gas_limit=gas_limit,
            gas_price=gas_price
        )
        
        return await self.client.send_transaction(tx_params)

    async def _transfer_erc20(
        self, token_address: str, to_address: str, amount: Union[int, float], gas_limit: Optional[int], gas_price: Optional[int]
    ) -> str:
        """
        Transfer ERC20 tokens to another address.

        Args:
            token_address: Token contract address
            to_address: Recipient address
            amount: Amount to transfer in token units
            gas_limit: Optional gas limit
            gas_price: Optional gas price

        Returns:
            str: Transaction hash
        """
        # ERC20 standard ABI for transfer function
        abi = [
            {
                "constant": False,
                "inputs": [
                    {"name": "_to", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            }
        ]
        
        try:
            # Get token contract
            token_contract = self.client.get_contract(token_address, abi)
            
            # Get token decimals
            decimals = token_contract.functions.decimals().call()
            
            # Convert amount to token units
            amount_in_units = int(amount * (10 ** decimals))
            
            # Check token balance
            balance = token_contract.functions.balanceOf(self.client.wallet_address).call()
            if balance < amount_in_units:
                raise InsufficientFundsError(
                    f"Insufficient token balance: have {balance / (10 ** decimals)}, need {amount}"
                )
            
            # Encode the transfer function call
            transfer_function = token_contract.functions.transfer(
                self.client.w3.to_checksum_address(to_address),
                amount_in_units
            )
            
            # Build the transaction
            tx_params = await self.client.prepare_transaction(
                to=token_address,
                data=transfer_function.build_transaction()["data"],
                gas_limit=gas_limit,
                gas_price=gas_price
            )
            
            # Send the transaction
            return await self.client.send_transaction(tx_params)
            
        except InsufficientFundsError:
            raise
        except Exception as e:
            raise WalletError(f"Failed to transfer tokens: {e}")

    async def approve_token(
        self, 
        token_address: str, 
        spender_address: str, 
        amount: Union[int, float, str] = "unlimited",
        wallet_name: Optional[str] = None
    ) -> str:
        """
        Approve a spender to use tokens.

        Args:
            token_address: Token contract address
            spender_address: Address to approve as spender
            amount: Amount to approve (use "unlimited" for maximum)
            wallet_name: Name of the wallet to use (defaults to active wallet)

        Returns:
            str: Transaction hash
        """
        wallet = self._get_wallet_for_operation(wallet_name)
        
        # Temporarily set the active wallet if needed
        original_active = self.active_wallet_name
        if wallet.name != original_active:
            self.set_active_wallet(wallet.name)
        
        try:
            # ERC20 standard ABI for approve function
            abi = [
                {
                    "constant": False,
                    "inputs": [
                        {"name": "_spender", "type": "address"},
                        {"name": "_value", "type": "uint256"}
                    ],
                    "name": "approve",
                    "outputs": [{"name": "", "type": "bool"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "decimals",
                    "outputs": [{"name": "", "type": "uint8"}],
                    "type": "function"
                }
            ]
            
            # Get token contract
            token_contract = self.client.get_contract(token_address, abi)
            
            # Get token decimals
            decimals = token_contract.functions.decimals().call()
            
            # Determine approval amount
            if amount == "unlimited":
                # Max uint256 value
                amount_in_units = 2**256 - 1
            else:
                # Convert amount to token units
                amount_in_units = int(float(amount) * (10 ** decimals))
            
            # Encode the approve function call
            approve_function = token_contract.functions.approve(
                self.client.w3.to_checksum_address(spender_address),
                amount_in_units
            )
            
            # Build the transaction
            tx_params = await self.client.prepare_transaction(
                to=token_address,
                data=approve_function.build_transaction()["data"],
            )
            
            # Send the transaction
            return await self.client.send_transaction(tx_params)
            
        except Exception as e:
            raise WalletError(f"Failed to approve tokens: {e}")
        finally:
            # Restore the original active wallet if we changed it
            if wallet.name != original_active and original_active is not None:
                self.set_active_wallet(original_active)
    
    def _get_wallet_for_operation(self, wallet_name: Optional[str] = None) -> Wallet:
        """
        Get the wallet to use for an operation.
        
        Args:
            wallet_name: Name of the wallet to use (defaults to active wallet)
            
        Returns:
            Wallet: The wallet to use
        """
        # Use specified wallet or fall back to active wallet
        if wallet_name:
            wallet = self.get_wallet(wallet_name)
        else:
            wallet = self.active_wallet
            
        if not wallet:
            raise WalletError("No wallet specified and no active wallet set")
            
        if not wallet.has_private_key():
            raise WalletError(f"Wallet {wallet.name} does not have a private key for signing transactions")
            
        return wallet