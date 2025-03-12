"""
Helper utilities for Monad automation.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from eth_utils import to_checksum_address, is_address
from web3 import Web3

from .logger import logger
from ..core.exceptions import ValidationError


def load_abi(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """
    Load contract ABI from a JSON file.
    
    Args:
        path: Path to the ABI JSON file
        
    Returns:
        List[Dict[str, Any]]: Contract ABI
    """
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load ABI from {path}: {e}")
        raise ValidationError(f"Failed to load ABI: {e}")


def load_abi_for_contract(contract_name: str, abi_dir: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
    """
    Load contract ABI from a standard directory structure.
    
    Args:
        contract_name: Name of the contract
        abi_dir: Directory containing ABI files (defaults to ./abis)
        
    Returns:
        List[Dict[str, Any]]: Contract ABI
    """
    abi_dir = abi_dir or Path("./abis")
    
    # Try different file patterns
    potential_paths = [
        Path(abi_dir) / f"{contract_name}.json",
        Path(abi_dir) / f"{contract_name.lower()}.json",
        Path(abi_dir) / f"{contract_name}_abi.json",
        Path(abi_dir) / contract_name / "abi.json",
    ]
    
    for path in potential_paths:
        if path.exists():
            return load_abi(path)
    
    raise ValidationError(f"Could not find ABI for contract {contract_name} in {abi_dir}")


def validate_address(address: str, name: str = "address") -> str:
    """
    Validate and format an Ethereum address.
    
    Args:
        address: Ethereum address to validate
        name: Name of the address (for error messages)
        
    Returns:
        str: Checksum address
        
    Raises:
        ValidationError: If the address is invalid
    """
    try:
        if not is_address(address):
            raise ValidationError(f"Invalid {name}: {address}")
        return to_checksum_address(address)
    except Exception as e:
        raise ValidationError(f"Invalid {name}: {address} - {e}")


def wei_to_ether(wei_value: int) -> float:
    """
    Convert wei to ether.
    
    Args:
        wei_value: Value in wei
        
    Returns:
        float: Value in ether
    """
    return Web3.from_wei(wei_value, "ether")


def ether_to_wei(ether_value: Union[int, float]) -> int:
    """
    Convert ether to wei.
    
    Args:
        ether_value: Value in ether
        
    Returns:
        int: Value in wei
    """
    return Web3.to_wei(ether_value, "ether")


def format_wei_to_gwei(wei_value: int) -> float:
    """
    Format wei value to gwei for display.
    
    Args:
        wei_value: Value in wei
        
    Returns:
        float: Value in gwei
    """
    return Web3.from_wei(wei_value, "gwei")


def format_transaction_data(tx_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format transaction data for display.
    
    Args:
        tx_data: Raw transaction data
        
    Returns:
        Dict[str, Any]: Formatted transaction data
    """
    result = dict(tx_data)
    
    # Format values
    if "value" in result:
        result["value_ether"] = wei_to_ether(result["value"])
    
    if "gasPrice" in result:
        result["gasPrice_gwei"] = format_wei_to_gwei(result["gasPrice"])
    
    return result


def load_contract_addresses(path: Optional[Union[str, Path]] = None) -> Dict[str, str]:
    """
    Load contract addresses from a JSON file.
    
    Args:
        path: Path to the addresses JSON file (defaults to ./addresses.json)
        
    Returns:
        Dict[str, str]: Contract addresses
    """
    path = path or Path("./addresses.json")
    
    try:
        with open(path, "r") as f:
            addresses = json.load(f)
            
        # Validate and format addresses
        return {
            key: validate_address(value, key)
            for key, value in addresses.items()
        }
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to load contract addresses from {path}: {e}")
        return {}