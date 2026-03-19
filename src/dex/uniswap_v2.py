"""Uniswap V2 pool interface.

Provides read access (price queries) and write access (swap execution)
for Uniswap V2-compatible pools via their on-chain contracts.
"""

import logging
from decimal import Decimal
from typing import Optional, Tuple

from web3 import Web3
from web3.contract import Contract

from src.utils.helpers import checksum, deadline, min_amount_out, to_wei

logger = logging.getLogger(__name__)

# ── Minimal ABIs ──────────────────────────────────────────────────────────────

_FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
        ],
        "name": "getPair",
        "outputs": [{"internalType": "address", "name": "pair", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]

_PAIR_ABI = [
    {
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"},
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
]

_ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
        ],
        "name": "swapExactETHForTokens",
        "outputs": [
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
        ],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
        ],
        "name": "swapExactTokensForETH",
        "outputs": [
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
        ],
        "name": "getAmountsOut",
        "outputs": [
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
        ],
        "stateMutability": "view",
        "type": "function",
    },
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
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
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


class UniswapV2Client:
    """High-level client for a Uniswap V2 deployment."""

    def __init__(
        self,
        web3: Web3,
        factory_address: str,
        router_address: str,
    ) -> None:
        self.w3 = web3
        self.factory: Contract = web3.eth.contract(
            address=checksum(factory_address), abi=_FACTORY_ABI
        )
        self.router: Contract = web3.eth.contract(
            address=checksum(router_address), abi=_ROUTER_ABI
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _pair_contract(self, pair_address: str) -> Contract:
        return self.w3.eth.contract(address=checksum(pair_address), abi=_PAIR_ABI)

    def _erc20(self, token_address: str) -> Contract:
        return self.w3.eth.contract(address=checksum(token_address), abi=_ERC20_ABI)

    def _token_decimals(self, token_address: str) -> int:
        return self._erc20(token_address).functions.decimals().call()

    # ── Read methods ──────────────────────────────────────────────────────────

    def get_pair_address(self, token_a: str, token_b: str) -> Optional[str]:
        """Return the pair contract address for *token_a*/*token_b*, or ``None``."""
        addr = self.factory.functions.getPair(
            checksum(token_a), checksum(token_b)
        ).call()
        null = "0x0000000000000000000000000000000000000000"
        return addr if addr != null else None

    def get_reserves(
        self, token_a: str, token_b: str
    ) -> Optional[Tuple[int, int]]:
        """Return ``(reserve_a, reserve_b)`` for the *token_a*/*token_b* pair.

        Returns ``None`` if the pair does not exist.
        """
        pair_address = self.get_pair_address(token_a, token_b)
        if pair_address is None:
            return None

        pair = self._pair_contract(pair_address)
        reserve0, reserve1, _ = pair.functions.getReserves().call()
        token0 = pair.functions.token0().call()

        # Ensure reserves are ordered to match (token_a, token_b)
        if checksum(token0) == checksum(token_a):
            return reserve0, reserve1
        return reserve1, reserve0

    def get_price(
        self,
        token_in: str,
        token_out: str,
        decimals_in: Optional[int] = None,
        decimals_out: Optional[int] = None,
    ) -> Optional[Decimal]:
        """Return the spot price of *token_out* in units of *token_in*.

        i.e. *how many token_out do you receive for 1 token_in*.
        Returns ``None`` if the pair does not exist or has no liquidity.
        """
        reserves = self.get_reserves(token_in, token_out)
        if reserves is None or reserves[0] == 0:
            return None

        dec_in = decimals_in if decimals_in is not None else self._token_decimals(token_in)
        dec_out = decimals_out if decimals_out is not None else self._token_decimals(token_out)

        reserve_in, reserve_out = reserves
        # Price = (reserve_out / 10^dec_out) / (reserve_in / 10^dec_in)
        price = (Decimal(reserve_out) / Decimal(10**dec_out)) / (
            Decimal(reserve_in) / Decimal(10**dec_in)
        )
        return price

    def get_amounts_out(self, amount_in_wei: int, path: list) -> Optional[list]:
        """Call the router's ``getAmountsOut`` for a given *path*.

        Returns the list of output amounts, or ``None`` on failure.
        """
        try:
            return self.router.functions.getAmountsOut(
                amount_in_wei, [checksum(a) for a in path]
            ).call()
        except Exception as exc:  # noqa: BLE001
            logger.debug("getAmountsOut failed: %s", exc)
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
        """Approve *spender* to spend up to *amount_wei* of *token_address*.

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

    def swap_exact_tokens_for_tokens(
        self,
        amount_in_wei: int,
        amount_out_min_wei: int,
        path: list,
        recipient: str,
        sender: str,
        private_key: str,
        gas_price_wei: int,
        deadline_ts: Optional[int] = None,
    ) -> str:
        """Execute a token→token swap via the V2 router.

        Returns the transaction hash.
        """
        ts = deadline_ts or deadline()
        nonce = self.w3.eth.get_transaction_count(checksum(sender))
        tx = self.router.functions.swapExactTokensForTokens(
            amount_in_wei,
            amount_out_min_wei,
            [checksum(a) for a in path],
            checksum(recipient),
            ts,
        ).build_transaction(
            {
                "from": checksum(sender),
                "nonce": nonce,
                "gasPrice": gas_price_wei,
            }
        )
        signed = self.w3.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info("V2 swap submitted: %s", tx_hash.hex())
        return tx_hash.hex()

    def swap_exact_eth_for_tokens(
        self,
        amount_eth_wei: int,
        amount_out_min_wei: int,
        path: list,
        recipient: str,
        sender: str,
        private_key: str,
        gas_price_wei: int,
        deadline_ts: Optional[int] = None,
    ) -> str:
        """Execute an ETH→token swap via the V2 router.

        Returns the transaction hash.
        """
        ts = deadline_ts or deadline()
        nonce = self.w3.eth.get_transaction_count(checksum(sender))
        tx = self.router.functions.swapExactETHForTokens(
            amount_out_min_wei,
            [checksum(a) for a in path],
            checksum(recipient),
            ts,
        ).build_transaction(
            {
                "from": checksum(sender),
                "value": amount_eth_wei,
                "nonce": nonce,
                "gasPrice": gas_price_wei,
            }
        )
        signed = self.w3.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info("V2 ETH→token swap submitted: %s", tx_hash.hex())
        return tx_hash.hex()

    def swap_exact_tokens_for_eth(
        self,
        amount_in_wei: int,
        amount_out_min_wei: int,
        path: list,
        recipient: str,
        sender: str,
        private_key: str,
        gas_price_wei: int,
        deadline_ts: Optional[int] = None,
    ) -> str:
        """Execute a token→ETH swap via the V2 router.

        Returns the transaction hash.
        """
        ts = deadline_ts or deadline()
        nonce = self.w3.eth.get_transaction_count(checksum(sender))
        tx = self.router.functions.swapExactTokensForETH(
            amount_in_wei,
            amount_out_min_wei,
            [checksum(a) for a in path],
            checksum(recipient),
            ts,
        ).build_transaction(
            {
                "from": checksum(sender),
                "nonce": nonce,
                "gasPrice": gas_price_wei,
            }
        )
        signed = self.w3.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info("V2 token→ETH swap submitted: %s", tx_hash.hex())
        return tx_hash.hex()
