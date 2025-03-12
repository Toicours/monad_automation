"""
DEX swap tasks for Monad blockchain.
"""
from typing import List, Optional, Dict, Any, Union

from pydantic import BaseModel, Field, validator

from core.blockchain import MonadClient
from core.exceptions import TaskConfigurationError
from utils.helpers import validate_address, wei_to_ether, ether_to_wei
from base import BaseTask


class SwapParams(BaseModel):
    """Parameters for a token swap."""
    
    token_in: str = Field(..., description="Token to swap from (address or symbol)")
    token_out: str = Field(..., description="Token to swap to (address or symbol)")
    amount_in: Union[int, float] = Field(..., description="Amount to swap")
    min_amount_out: Optional[Union[int, float]] = Field(None, description="Minimum amount to receive")
    slippage: float = Field(0.5, description="Allowed slippage percentage")
    deadline_minutes: int = Field(20, description="Transaction deadline in minutes")
    path: Optional[List[str]] = Field(None, description="Custom swap path")
    
    @validator("token_in", "token_out")
    def validate_token(cls, v: str) -> str:
        """Validate token address."""
        # Allow common symbols as placeholders
        common_symbols = ["ETH", "WETH", "USDC", "USDT", "DAI", "WBTC"]
        if v in common_symbols:
            return v
        
        # Validate as address
        return validate_address(v)
    
    @validator("slippage")
    def validate_slippage(cls, v: float) -> float:
        """Validate slippage is within reasonable range."""
        if v < 0 or v > 100:
            raise ValueError("Slippage must be between 0 and 100")
        return v
    
    @validator("path")
    def validate_path(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate swap path addresses."""
        if v is None:
            return v
            
        return [validate_address(addr) for addr in v]


class SwapTask(BaseTask):
    """Task for swapping tokens on a DEX."""
    
    def __init__(
        self,
        token_in: str,
        token_out: str,
        amount_in: Union[int, float],
        min_amount_out: Optional[Union[int, float]] = None,
        slippage: float = 0.5,
        deadline_minutes: int = 20,
        path: Optional[List[str]] = None,
        router_address: Optional[str] = None,
        wallet_name: Optional[str] = None,
        task_id: Optional[str] = None,
    ):
        """
        Initialize swap task.
        
        Args:
            token_in: Token to swap from (address or symbol)
            token_out: Token to swap to (address or symbol)
            amount_in: Amount to swap
            min_amount_out: Minimum amount to receive (calculated from slippage if None)
            slippage: Allowed slippage percentage
            deadline_minutes: Transaction deadline in minutes
            path: Custom swap path
            router_address: DEX router address (uses configured default if None)
            wallet_name: Name of the wallet to use (uses active wallet if None)
            task_id: Optional unique identifier for the task
        """
        super().__init__(task_id)
        
        self.params = SwapParams(
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            min_amount_out=min_amount_out,
            slippage=slippage,
            deadline_minutes=deadline_minutes,
            path=path,
        )
        
        self.router_address = router_address
        self.wallet_name = wallet_name
    
    @property
    def task_name(self) -> str:
        """Get the task name."""
        return f"SwapTokens({self.params.token_in} → {self.params.token_out})"
    
    async def execute(self, client: MonadClient) -> Dict[str, Any]:
        """
        Execute the swap task.
        
        Args:
            client: Monad client instance
            
        Returns:
            Dict[str, Any]: Swap result data
        """
        from ...config import settings
        import time
        
        # Set router address
        router_address = self.router_address or settings.DEX_ROUTER_ADDRESS
        if not router_address:
            raise TaskConfigurationError("DEX router address not specified")
        
        # Validate and resolve tokens
        token_in, token_out = await self._resolve_tokens(client)
        
        # Use the specified wallet or the active wallet
        original_wallet = None
        if self.wallet_name and client.wallet.active_wallet_name != self.wallet_name:
            original_wallet = client.wallet.active_wallet_name
            client.wallet.set_active_wallet(self.wallet_name)
        
        try:
            # Get router contract 
            router_contract = self._get_router_contract(client, router_address)
            
            # Calculate swap amounts
            amount_in_wei = self._to_token_units(client, self.params.amount_in, token_in)
            
            # Set deadline
            deadline = int(time.time() + (self.params.deadline_minutes * 60))
            
            # Approve token spending if needed
            if token_in.lower() != "eth":
                await self._approve_token_if_needed(client, token_in, router_address, amount_in_wei)
            
            # Prepare swap parameters
            path = self.params.path or [token_in, token_out]
            
            # Get amount out estimation
            amounts_out = await router_contract.functions.getAmountsOut(
                amount_in_wei,
                path
            ).call()
            
            expected_amount_out = amounts_out[-1]
            
            # Calculate minimum amount out with slippage
            if self.params.min_amount_out is not None:
                min_amount_out_wei = self._to_token_units(
                    client, self.params.min_amount_out, token_out
                )
            else:
                slippage_factor = 1 - (self.params.slippage / 100)
                min_amount_out_wei = int(expected_amount_out * slippage_factor)
            
            # Execute swap
            if token_in.lower() == "eth":
                # Swap ETH for tokens
                swap_tx = router_contract.functions.swapExactETHForTokens(
                    min_amount_out_wei,
                    path,
                    client.wallet_address,
                    deadline
                )
                
                # Prepare transaction
                tx_params = await client.prepare_transaction(
                    to=router_address,
                    value=amount_in_wei,
                    data=swap_tx.build_transaction()["data"]
                )
            else:
                # Swap tokens for tokens or tokens for ETH
                if token_out.lower() == "eth":
                    swap_tx = router_contract.functions.swapExactTokensForETH(
                        amount_in_wei,
                        min_amount_out_wei,
                        path,
                        client.wallet_address,
                        deadline
                    )
                else:
                    swap_tx = router_contract.functions.swapExactTokensForTokens(
                        amount_in_wei,
                        min_amount_out_wei,
                        path,
                        client.wallet_address,
                        deadline
                    )
                
                # Prepare transaction
                tx_params = await client.prepare_transaction(
                    to=router_address,
                    data=swap_tx.build_transaction()["data"]
                )
            
            # Send transaction
            tx_hash = await client.send_transaction(tx_params)
            
            # Wait for receipt
            receipt = await client.wait_for_transaction_receipt(tx_hash)
            
            # Parse swap events
            swap_events = self._parse_swap_events(client, receipt, router_contract)
            
            # Return result
            return {
                "tx_hash": tx_hash,
                "token_in": token_in,
                "token_out": token_out,
                "amount_in": self.params.amount_in,
                "amount_in_wei": amount_in_wei,
                "amount_out_wei": expected_amount_out,
                "amount_out": self._from_token_units(client, expected_amount_out, token_out),
                "slippage": self.params.slippage,
                "min_amount_out_wei": min_amount_out_wei,
                "events": swap_events,
            }
        finally:
            # Restore original wallet if needed
            if original_wallet:
                client.wallet.set_active_wallet(original_wallet)
    
    async def _resolve_tokens(self, client: MonadClient) -> tuple:
        """
        Resolve token symbols to addresses.
        
        Args:
            client: Monad client instance
            
        Returns:
            tuple: (token_in_address, token_out_address)
        """
        # This is a simplified implementation
        # In a real implementation, you would use a token registry or on-chain lookup
        
        # Common token addresses - replace with actual addresses for your network
        token_map = {
            "eth": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",  # Common representation for native ETH
            "weth": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # Replace with actual WETH address
            "usdc": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # Replace with actual USDC address
            "usdt": "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # Replace with actual USDT address
            "dai": "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # Replace with actual DAI address
            "wbtc": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  # Replace with actual WBTC address
        }
        
        token_in = self.params.token_in.lower()
        token_out = self.params.token_out.lower()
        
        # Resolve token_in
        if token_in in token_map:
            token_in = token_map[token_in]
        
        # Resolve token_out
        if token_out in token_map:
            token_out = token_map[token_out]
        
        return token_in, token_out
    
    def _get_router_contract(self, client: MonadClient, router_address: str):
        """
        Get the DEX router contract.
        
        Args:
            client: Monad client instance
            router_address: Router contract address
            
        Returns:
            Contract: Router contract
        """
        # Minimal Uniswap V2 Router ABI - replace with full ABI in production
        router_abi = [
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"}
                ],
                "name": "getAmountsOut",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactETHForTokens",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactTokensForETH",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactTokensForTokens",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]
        
        return client.get_contract(router_address, router_abi)
    
    async def _approve_token_if_needed(self, client: MonadClient, token_address: str, spender_address: str, amount: int):
        """
        Approve token spending if needed.
        
        Args:
            client: Monad client instance
            token_address: Token address
            spender_address: Spender address
            amount: Amount to approve
        """
        # ERC20 allowance ABI
        allowance_abi = [
            {
                "constant": True,
                "inputs": [
                    {"name": "owner", "type": "address"},
                    {"name": "spender", "type": "address"}
                ],
                "name": "allowance",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function"
            }
        ]
        
        # Get token contract
        token_contract = client.get_contract(token_address, allowance_abi)
        
        # Check current allowance
        current_allowance = await token_contract.functions.allowance(
            client.wallet_address, spender_address
        ).call()
        
        # If allowance is insufficient, approve
        if current_allowance < amount:
            # Approve an unlimited amount to save gas on future swaps
            await client.wallet.approve_token(token_address, spender_address, "unlimited")
    
    def _to_token_units(self, client: MonadClient, amount: Union[int, float], token_address: str) -> int:
        """
        Convert token amount to token units (wei).
        
        Args:
            client: Monad client instance
            amount: Amount in token units
            token_address: Token address
            
        Returns:
            int: Amount in wei
        """
        # Special case for ETH
        if token_address.lower() == "eth" or token_address.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee":
            return client.w3.to_wei(amount, "ether")
        
        # For other tokens, we need to get the decimals
        decimals_abi = [
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function"
            }
        ]
        
        token_contract = client.get_contract(token_address, decimals_abi)
        decimals = token_contract.functions.decimals().call()
        
        # Convert to wei equivalent
        return int(amount * (10 ** decimals))
    
    def _from_token_units(self, client: MonadClient, amount: int, token_address: str) -> float:
        """
        Convert token units (wei) to token amount.
        
        Args:
            client: Monad client instance
            amount: Amount in token units
            token_address: Token address
            
        Returns:
            float: Amount in token
        """
        # Special case for ETH
        if token_address.lower() == "eth" or token_address.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee":
            return client.w3.from_wei(amount, "ether")
        
        # For other tokens, we need to get the decimals
        decimals_abi = [
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function"
            }
        ]
        
        token_contract = client.get_contract(token_address, decimals_abi)
        decimals = token_contract.functions.decimals().call()
        
        # Convert from wei equivalent
        return amount / (10 ** decimals)
    
    def _parse_swap_events(self, client: MonadClient, receipt, router_contract):
        """
        Parse swap events from transaction receipt.
        
        Args:
            client: Monad client instance
            receipt: Transaction receipt
            router_contract: Router contract
            
        Returns:
            list: Parsed events
        """
        # This is a simplified implementation
        # In a real implementation, you would parse the Swap event logs
        return []
    
    def validate(self) -> None:
        """
        Validate that the task is properly configured.
        
        Raises:
            TaskConfigurationError: If the task is not properly configured
        """
        try:
            # Validate swap parameters
            self.params
        except Exception as e:
            raise TaskConfigurationError(f"Invalid swap parameters: {e}")