"""
Wallet management module for Monad blockchain interaction.
"""

import json
import os
import secrets
import base64
import os

from pathlib import Path
from typing import Dict, List, Optional, Union, Any, Tuple

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress, HexStr
from web3 import Web3
from web3.contract import Contract
from web3.types import TxParams, Wei, TxReceipt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


from config import settings
from core.exceptions import InsufficientFundsError, WalletError

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from blockchain import MonadClient

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
        
    def to_dict(self, encrypt=False, password=None) -> Dict[str, Any]:
        """
        Convert wallet to a dictionary for serialization.
        
        Args:
            encrypt: Whether to encrypt the private key
            password: Password for encryption (required if encrypt=True)
            
        Returns:
            Dict[str, Any]: Wallet details
        """
        data = {
            "name": self.name,
            "address": self.address,
        }
        
        if self._private_key:
            if encrypt and password:
                # Generate a salt
                salt = os.urandom(16)
                
                # Generate encryption key from password
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=salt,
                    iterations=100000,
                )
                key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
                
                # Encrypt the private key
                f = Fernet(key)
                encrypted_key = f.encrypt(self._private_key.encode()).decode()
                
                # Store encrypted key and salt
                data["private_key_encrypted"] = encrypted_key
                data["salt"] = base64.b64encode(salt).decode()
            else:
                # Store unencrypted
                data["private_key"] = self._private_key
                
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], password: Optional[str] = None) -> "Wallet":
        """
        Create a wallet from a dictionary.
        
        Args:
            data: Dictionary with wallet details
            password: Password for decryption (if needed)
            
        Returns:
            Wallet: Configured wallet instance
        """
        # Check if we have an encrypted private key
        if "private_key_encrypted" in data and password:
            try:
                # Get the salt
                salt = base64.b64decode(data["salt"])
                
                # Recreate the key
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=salt,
                    iterations=100000,
                )
                key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
                
                # Decrypt the private key
                f = Fernet(key)
                private_key = f.decrypt(data["private_key_encrypted"].encode()).decode()
                
                return cls.from_private_key(
                    name=data["name"],
                    private_key=private_key
                )
            except Exception as e:
                raise ValueError(f"Failed to decrypt wallet: {e}")
                
        elif "private_key" in data:
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
        self.password = None  # New field for wallet encryption
        
        # Load wallet directory if specified
        self.wallet_directory = os.getenv("WALLET_DIRECTORY", "wallets")
        
        # Initialize wallet directory if it doesn't exist
        if self.wallet_directory:
            os.makedirs(self.wallet_directory, exist_ok=True)
    
    # New method for encryption
    def set_encryption_password(self, password: str) -> None:
        """
        Set the password for wallet encryption/decryption.
        
        Args:
            password: The password to use
        """
        self.password = password
    
    @property
    def active_wallet(self) -> Optional[Wallet]:
        """Get the currently active wallet."""
        if not self.active_wallet_name:
            return None
        return self.wallets.get(self.active_wallet_name)
    
    # Modified method to support encryption
    def load_wallets(self, password: Optional[str] = None) -> None:
        """
        Load wallets from the wallet directory.
        
        Args:
            password: Password for decrypting wallets (if needed)
        """
        if not self.wallet_directory or not os.path.exists(self.wallet_directory):
            return
        
        decrypt_password = password or self.password
            
        wallet_files = Path(self.wallet_directory).glob("*.wallet")
        for wallet_file in wallet_files:
            try:
                with open(wallet_file, "r") as f:
                    wallet_data = json.load(f)
                    
                wallet = Wallet.from_dict(wallet_data, decrypt_password)
                self.add_wallet(wallet, save=False)  # Don't re-save
            except Exception as e:
                print(f"Error loading wallet {wallet_file}: {e}")
    
    # Modified method to support encryption
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
        
        # Encrypt if password is set
        wallet_data = wallet.to_dict(encrypt=bool(self.password), password=self.password)
        
        with open(wallet_path, "w") as f:
            json.dump(wallet_data, f, indent=2)
        
        # Set restrictive file permissions
        try:
            os.chmod(wallet_path, 0o600)  # Only owner can read/write
        except Exception:
            pass  # May not work on Windows
    
    # Modified method to support save flag
    def add_wallet(self, wallet: Wallet, save: bool = True) -> None:
        """
        Add a wallet to the manager.
        
        Args:
            wallet: Wallet to add
            save: Whether to save the wallet to disk
        """
        self.wallets[wallet.name] = wallet
        
        # Set as active if it's the first wallet
        if len(self.wallets) == 1:
            self.set_active_wallet(wallet.name)
            
        # Save wallet to file if requested
        if save:
            self.save_wallet(wallet.name)
    
    # Keep existing method
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
    
    # Keep existing method
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
    
    # Keep existing method
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
    
    # Keep existing method
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
    
    # Keep existing method
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
    
    # Keep existing method
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

    # New method for wallet generation
    def generate_wallet(self, name: str) -> Wallet:
        """
        Generate a new wallet with secure randomness.
        
        Args:
            name: Name for the new wallet
            
        Returns:
            Wallet: The generated wallet
        """
        # Generate random bytes for the private key with strong entropy
        import secrets
        private_key = "0x" + secrets.token_hex(32)
        
        # Create and add the wallet
        wallet = Wallet.from_private_key(name=name, private_key=private_key)
        self.add_wallet(wallet)
        return wallet
