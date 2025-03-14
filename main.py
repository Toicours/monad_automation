#!/usr/bin/env python
"""
Main entry point for Monad Automation CLI.
"""
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

import click
from dotenv import load_dotenv

from config.settings import settings, NetworkConfig
from core.blockchain import MonadClient
from core.exceptions import MonadError
from tasks.base import BaseTask, TaskResult
from utils.logger import logger, setup_logger

# Load environment variables
load_dotenv()


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.option("--log-file", type=str, help="Log file path")
def cli(debug: bool, log_file: Optional[str]):
    """Monad Blockchain Automation Framework."""
    # Configure logging
    log_level = "DEBUG" if debug else settings.LOG_LEVEL
    setup_logger(log_level=log_level, log_file=log_file)
    
    logger.info("Starting Monad Automation CLI")


@cli.command()
@click.option("--rpc", type=str, help="RPC endpoint URL")
@click.option("--network", type=str, help="Network to use")
def info(rpc: Optional[str], network: Optional[str] = None):
    """Display network and configuration information."""
    try:
        # Initialize client
        client = _get_client(rpc, network)
        
        # Check connection
        connected = client.is_connected()
        
        # Get network info
        if hasattr(client, 'network_name') and hasattr(settings, 'networks'):
            network_info = settings.networks.get(client.network_name, NetworkConfig(
                name="Custom", rpc_url=client.rpc_url, chain_id=client.chain_id
            ))
            click.echo(f"Network: {network_info.name} (chain ID: {network_info.chain_id})")
        
        click.echo(f"RPC URL: {client.rpc_url}")
        click.echo(f"Chain ID: {client.chain_id}")
        click.echo(f"Connected: {connected}")
        
        if connected:
            # Get network info
            block_number = client.w3.eth.block_number
            gas_price = client.w3.eth.gas_price
            
            click.echo(f"Current block: {block_number}")
            click.echo(f"Gas price: {client.w3.from_wei(gas_price, 'gwei')} gwei")
        
        # List wallets
        wallets = client.wallet.list_wallets()
        
        if wallets:
            click.echo("\nWallets:")
            for wallet in wallets:
                active_marker = " (active)" if wallet["is_active"] else ""
                key_status = "with private key" if wallet["has_private_key"] else "address only"
                click.echo(f"  {wallet['name']}: {wallet['address']} [{key_status}]{active_marker}")
        else:
            click.echo("\nNo wallets configured")
            
    except Exception as e:
        logger.error(f"Error: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("networks")
def list_networks():
    """List available networks."""
    if hasattr(settings, 'networks'):
        networks = settings.networks
        
        click.echo("Available networks:")
        for net_key, network in networks.items():
            active_marker = " (active)" if net_key == settings.DEFAULT_NETWORK else ""
            testnet_marker = " [testnet]" if network.is_testnet else ""
            click.echo(f"  {net_key}: {network.name}{testnet_marker}{active_marker}")
            click.echo(f"    RPC: {network.rpc_url}")
            click.echo(f"    Chain ID: {network.chain_id}")
    else:
        click.echo("No networks configured")
        
@cli.command("set-network")
@click.argument("network_name", type=str)
def set_network(network_name: str):
    """Set the active network."""
    if not hasattr(settings, 'networks') or network_name not in settings.networks:
        click.echo(f"Error: Network '{network_name}' not found", err=True)
        if hasattr(settings, 'networks'):
            click.echo("Available networks:")
            for net_key in settings.networks.keys():
                click.echo(f"  - {net_key}")
        sys.exit(1)
    
    # We can't actually modify settings at runtime, but we can:
    # 1. Create a temporary .env.network file
    # 2. Tell the user to update their .env file
    
    env_path = Path(".env.network")
    with open(env_path, "w") as f:
        f.write(f"DEFAULT_NETWORK={network_name}\n")
    
    click.echo(f"Created temporary network configuration in {env_path}")
    click.echo(f"To permanently set '{network_name}' as your default network,")
    click.echo(f"add 'DEFAULT_NETWORK={network_name}' to your .env file")


@cli.group()
def wallets():
    """Manage wallets."""
    pass


@wallets.command("list")
def wallet_list():
    """List available wallets."""
    try:
        # Initialize client
        client = _get_client()
        
        # List wallets
        wallets = client.wallet.list_wallets()
        
        if wallets:
            click.echo("Available wallets:")
            for wallet in wallets:
                active_marker = " (active)" if wallet["is_active"] else ""
                key_status = "with private key" if wallet["has_private_key"] else "address only"
                click.echo(f"  {wallet['name']}: {wallet['address']} [{key_status}]{active_marker}")
        else:
            click.echo("No wallets configured")
            
    except Exception as e:
        logger.error(f"Error: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@wallets.command("add")
@click.argument("name", type=str)
@click.option("--private-key", type=str, help="Wallet private key")
@click.option("--address", type=str, help="Wallet address (for watch-only)")
def wallet_add(name: str, private_key: Optional[str], address: Optional[str]):
    """Add a new wallet."""
    try:
        # Initialize client
        client = _get_client()
        
        if private_key:
            # Add wallet with private key
            wallet = client.wallet.add_wallet_from_private_key(name, private_key)
            click.echo(f"Added wallet '{name}' with address {wallet.address}")
        elif address:
            # Add watch-only wallet
            from core.wallet import Wallet
            wallet = Wallet(name=name, address=address)
            client.wallet.add_wallet(wallet)
            click.echo(f"Added watch-only wallet '{name}' with address {wallet.address}")
        else:
            click.echo("Error: Either --private-key or --address must be specified", err=True)
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@wallets.command("remove")
@click.argument("name", type=str)
@click.option("--force", is_flag=True, help="Force removal without confirmation")
def wallet_remove(name: str, force: bool):
    """Remove a wallet."""
    try:
        # Initialize client
        client = _get_client()
        
        # Check if wallet exists
        if name not in [w["name"] for w in client.wallet.list_wallets()]:
            click.echo(f"Error: Wallet '{name}' not found", err=True)
            sys.exit(1)
        
        # Confirm removal
        if not force and not click.confirm(f"Are you sure you want to remove wallet '{name}'?"):
            click.echo("Operation cancelled")
            return
        
        # Remove wallet
        client.wallet.remove_wallet(name)
        click.echo(f"Removed wallet '{name}'")
            
    except Exception as e:
        logger.error(f"Error: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@wallets.command("set-active")
@click.argument("name", type=str)
def wallet_set_active(name: str):
    """Set the active wallet."""
    try:
        # Initialize client
        client = _get_client()
        
        # Check if wallet exists
        if name not in [w["name"] for w in client.wallet.list_wallets()]:
            click.echo(f"Error: Wallet '{name}' not found", err=True)
            sys.exit(1)
        
        # Set active wallet
        client.wallet.set_active_wallet(name)
        click.echo(f"Set '{name}' as the active wallet")
            
    except Exception as e:
        logger.error(f"Error: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@wallets.command("balance")
@click.argument("name", type=str, required=False)
@click.option("--token", type=str, help="Token address to check balance for")
def wallet_balance(name: Optional[str], token: Optional[str]):
    """Check wallet balance."""
    try:
        # Initialize client
        client = _get_client()
        
        # Determine wallet to check
        if name:
            # Check if wallet exists
            if name not in [w["name"] for w in client.wallet.list_wallets()]:
                click.echo(f"Error: Wallet '{name}' not found", err=True)
                sys.exit(1)
        else:
            # Use active wallet
            if not client.wallet.active_wallet:
                click.echo("Error: No active wallet set", err=True)
                sys.exit(1)
            name = client.wallet.active_wallet.name
        
        # Get balance
        balance = asyncio.run(client.wallet.get_balance(token, name))
        
        # Display result
        token_symbol = token or "ETH"
        click.echo(f"Balance of wallet '{name}': {balance} {token_symbol}")
            
    except Exception as e:
        logger.error(f"Error: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@wallets.command("generate")
@click.argument("name", type=str)
def wallet_generate(name: str):
    """Generate a new wallet with secure randomness."""
    try:
        # Initialize client
        client = _get_client()
        
        # Generate wallet
        wallet = client.wallet.generate_wallet(name)
        
        click.echo(f"Generated new wallet '{name}'")
        click.echo(f"Address: {wallet.address}")
        click.echo(f"Private Key: {wallet._private_key}")
        click.echo("\nWARNING: Store this private key securely and never share it!")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.group()
def dex():
    """DEX operations."""
    pass


@dex.command("swap")
@click.argument("token_in", type=str)
@click.argument("token_out", type=str)
@click.argument("amount", type=float)
@click.option("--wallet", type=str, help="Wallet to use (defaults to active wallet)")
@click.option("--slippage", type=float, default=0.5, help="Allowed slippage percentage")
@click.option("--min-out", type=float, help="Minimum amount to receive")
@click.option("--router", type=str, help="DEX router address")
def swap(
    token_in: str,
    token_out: str,
    amount: float,
    wallet: Optional[str],
    slippage: float,
    min_out: Optional[float],
    router: Optional[str]
):
    """Swap tokens on DEX."""
    try:
        # Initialize client
        client = _get_client()
        
        # Create swap task
        from tasks.dex.swap import SwapTask
        task = SwapTask(
            token_in=token_in,
            token_out=token_out,
            amount_in=amount,
            min_amount_out=min_out,
            slippage=slippage,
            router_address=router,
            wallet_name=wallet
        )
        
        # Execute task
        click.echo(f"Swapping {amount} {token_in} to {token_out}...")
        result = asyncio.run(task.run(client))
        
        # Display result
        if result.is_success():
            tx_hash = result.tx_hash
            result_data = result.result_data
            
            click.echo(f"Swap successful!")
            click.echo(f"Transaction hash: {tx_hash}")
            click.echo(f"Amount in: {result_data['amount_in']} {result_data['token_in']}")
            click.echo(f"Amount out: {result_data['amount_out']} {result_data['token_out']}")
        else:
            click.echo(f"Swap failed: {result.error}", err=True)
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _get_client(rpc_url: Optional[str] = None, network_name: Optional[str] = None) -> MonadClient:
    """
    Get a Monad client instance.
    
    Args:
        rpc_url: RPC endpoint URL (defaults to settings)
        network_name: Network to use (defaults to settings.DEFAULT_NETWORK)
        
    Returns:
        MonadClient: Initialized client
    """
    try:
        if rpc_url:
            # Use custom RPC URL with default chain ID if network not specified
            chain_id = settings.MONAD_CHAIN_ID
            if network_name and hasattr(settings, 'networks') and network_name in settings.networks:
                chain_id = settings.networks[network_name].chain_id
                
            return MonadClient(
                rpc_url=rpc_url,
                chain_id=chain_id
            )
        else:
            # Use network settings
            return MonadClient.from_env(network_name)
    except Exception as e:
        logger.error(f"Failed to initialize Monad client: {e}")
        raise


if __name__ == "__main__":
    cli()