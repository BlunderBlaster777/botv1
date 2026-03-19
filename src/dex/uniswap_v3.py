"""Uniswap V3 pool interface.

Provides read access (price queries via the on-chain Quoter contract) and
write access (swap execution via the SwapRouter) for Uniswap V3 pools.
"""

import logging
from decimal import Decimal
from typing import Optional

from web3 import Web3
from web3.contract import Contract

from src.utils.helpers import checksum, deadline

logger = logging.getLogger(__name__)

# ── Fee tiers available on V3 ─────────────────────────────────────────────────
FEE_TIERS = (100, 500, 3000, 10000)  # 0.01 %, 0.05 %, 0.30 %, 1.00 %

# ── Minimal ABIs ──────────────────────────────────────────────────────────────

_FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]

_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {
                "internalType": "uint16",
                "name": "observationCardinalityNext",
                "type": "uint16",
            },
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function",
    },
]

_QUOTER_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
        ],
        "name": "quoteExactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

_ROUTER_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {
                        "internalType": "uint256",
                        "name": "amountOutMinimum",
                        "type": "uint256",
                    },
                    {
                        "internalType": "uint160",
                        "name": "sqrtPriceLimitX96",
                        "type": "uint160",
                    },
                ],
                "internalType": "struct ISwapRouter.ExactInputSingleParams",
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "exactInputSingle",
        "outputs": [
            {"internalType": "uint256", "name": "amountOut", "type": "uint256"}
        ],
        "stateMutability": "payable",
        "type": "function",
    }
]

_ERC20_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def _sqrt_price_x96_to_price(
    sqrt_price_x96: int,
    decimals0: int,
    decimals1: int,
    token0_is_token_in: bool,
) -> Decimal:
    """Convert Uniswap V3 ``sqrtPriceX96`` to a human-readable price.

    The formula is::

        price_token1_per_token0 = (sqrtPriceX96 / 2^96)^2
                                  * (10^decimals0 / 10^decimals1)

    Parameters
    ----------
    sqrt_price_x96:
        The value returned from the pool's ``slot0()`` call.
    decimals0:
        Decimals of ``token0`` in the pool.
    decimals1:
        Decimals of ``token1`` in the pool.
    token0_is_token_in:
        When ``True``, return *token1 per token0*;
        when ``False``, return the reciprocal (*token0 per token1*).
    """
    q96 = Decimal(2**96)
    sqrt_price = Decimal(sqrt_price_x96) / q96
    price_token1_per_token0 = sqrt_price**2 * Decimal(10**decimals0) / Decimal(10**decimals1)
    if token0_is_token_in:
        return price_token1_per_token0
    return Decimal(1) / price_token1_per_token0 if price_token1_per_token0 != 0 else Decimal(0)


class UniswapV3Client:
    """High-level client for a Uniswap V3 deployment."""

    def __init__(
        self,
        web3: Web3,
        factory_address: str,
        quoter_address: str,
        router_address: str,
    ) -> None:
        self.w3 = web3
        self.factory: Contract = web3.eth.contract(
            address=checksum(factory_address), abi=_FACTORY_ABI
        )
        self.quoter: Contract = web3.eth.contract(
            address=checksum(quoter_address), abi=_QUOTER_ABI
        )
        self.router: Contract = web3.eth.contract(
            address=checksum(router_address), abi=_ROUTER_ABI
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _pool_contract(self, pool_address: str) -> Contract:
        return self.w3.eth.contract(address=checksum(pool_address), abi=_POOL_ABI)

    def _erc20(self, token_address: str) -> Contract:
        return self.w3.eth.contract(address=checksum(token_address), abi=_ERC20_ABI)

    def _token_decimals(self, token_address: str) -> int:
        return self._erc20(token_address).functions.decimals().call()

    # ── Read methods ──────────────────────────────────────────────────────────

    def get_pool_address(
        self, token_a: str, token_b: str, fee: int
    ) -> Optional[str]:
        """Return the pool address for *token_a*/*token_b* at *fee*, or ``None``."""
        null = "0x0000000000000000000000000000000000000000"
        addr = self.factory.functions.getPool(
            checksum(token_a), checksum(token_b), fee
        ).call()
        return addr if addr != null else None

    def get_best_pool(
        self, token_a: str, token_b: str
    ) -> Optional[tuple]:
        """Return ``(pool_address, fee)`` for the most liquid pool, or ``None``.

        Iterates over all standard fee tiers and picks the pool with the
        highest active liquidity.
        """
        best_pool = None
        best_liquidity = -1
        best_fee = None

        for fee in FEE_TIERS:
            pool_addr = self.get_pool_address(token_a, token_b, fee)
            if pool_addr is None:
                continue
            try:
                liquidity = self._pool_contract(pool_addr).functions.liquidity().call()
                if liquidity > best_liquidity:
                    best_liquidity = liquidity
                    best_pool = pool_addr
                    best_fee = fee
            except Exception as exc:  # noqa: BLE001
                logger.debug("Could not fetch liquidity for pool %s: %s", pool_addr, exc)

        return (best_pool, best_fee) if best_pool is not None else None

    def get_spot_price(
        self,
        token_in: str,
        token_out: str,
        fee: int,
        decimals_in: Optional[int] = None,
        decimals_out: Optional[int] = None,
    ) -> Optional[Decimal]:
        """Return the spot price of *token_out* per unit of *token_in* from slot0.

        This is a gas-free read; it does *not* account for price impact.
        Returns ``None`` if the pool does not exist.
        """
        pool_addr = self.get_pool_address(token_in, token_out, fee)
        if pool_addr is None:
            return None

        pool = self._pool_contract(pool_addr)
        slot0 = pool.functions.slot0().call()
        sqrt_price_x96 = slot0[0]
        if sqrt_price_x96 == 0:
            return None

        token0 = pool.functions.token0().call()
        token1 = pool.functions.token1().call()

        # Decimals must be ordered to match the pool's token0 / token1 layout.
        token0_is_in = checksum(token0) == checksum(token_in)
        if token0_is_in:
            dec0 = decimals_in if decimals_in is not None else self._token_decimals(token_in)
            dec1 = decimals_out if decimals_out is not None else self._token_decimals(token_out)
        else:
            dec0 = decimals_out if decimals_out is not None else self._token_decimals(token1)
            dec1 = decimals_in if decimals_in is not None else self._token_decimals(token_in)

        return _sqrt_price_x96_to_price(sqrt_price_x96, dec0, dec1, token0_is_in)

    def quote_exact_input_single(
        self,
        token_in: str,
        token_out: str,
        fee: int,
        amount_in_wei: int,
    ) -> Optional[int]:
        """Use the on-chain Quoter to simulate a single-hop swap.

        Returns the expected output amount in wei, or ``None`` on failure.
        Note: this is a ``call()`` that triggers a state-change simulation;
        it must **not** be sent as a transaction.
        """
        try:
            return self.quoter.functions.quoteExactInputSingle(
                checksum(token_in),
                checksum(token_out),
                fee,
                amount_in_wei,
                0,  # sqrtPriceLimitX96 = 0 means no limit
            ).call()
        except Exception as exc:  # noqa: BLE001
            logger.debug("quoteExactInputSingle failed: %s", exc)
            return None

    # ── Write methods ─────────────────────────────────────────────────────────

    def approve_token(
        self,
        token_address: str,
        spender: str,
        amount_wei: int,
        sender: str,
        private_key: str,
        gas_price_wei: int,
    ) -> str:
        """Approve *spender* to spend *amount_wei* of *token_address*.

        Returns the transaction hash.
        """
        token = self._erc20(token_address)
        nonce = self.w3.eth.get_transaction_count(checksum(sender))
        tx = token.functions.approve(checksum(spender), amount_wei).build_transaction(
            {
                "from": checksum(sender),
                "nonce": nonce,
                "gasPrice": gas_price_wei,
            }
        )
        signed = self.w3.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()

    def exact_input_single(
        self,
        token_in: str,
        token_out: str,
        fee: int,
        amount_in_wei: int,
        amount_out_minimum: int,
        recipient: str,
        sender: str,
        private_key: str,
        gas_price_wei: int,
        deadline_ts: Optional[int] = None,
    ) -> str:
        """Execute a single-hop exact-input swap via the V3 router.

        Returns the transaction hash.
        """
        ts = deadline_ts or deadline()
        nonce = self.w3.eth.get_transaction_count(checksum(sender))
        params = (
            checksum(token_in),
            checksum(token_out),
            fee,
            checksum(recipient),
            ts,
            amount_in_wei,
            amount_out_minimum,
            0,  # sqrtPriceLimitX96
        )
        tx = self.router.functions.exactInputSingle(params).build_transaction(
            {
                "from": checksum(sender),
                "nonce": nonce,
                "gasPrice": gas_price_wei,
            }
        )
        signed = self.w3.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info("V3 swap submitted: %s", tx_hash.hex())
        return tx_hash.hex()
