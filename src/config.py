"""Configuration management for the Liquidity Sniper Bot.

Reads all settings from environment variables (loaded from a ``.env`` file
when present via *python-dotenv*).  A single :class:`Config` instance is
created at module-import time and shared across the application.

Supported networks (set via the ``NETWORK`` environment variable):

* ``ethereum``  – Ethereum mainnet (default)
* ``polygon``   – Polygon PoS (MATIC)
* ``base``      – Base (Coinbase L2)
* ``arbitrum``  – Arbitrum One

Each network ships with sensible contract-address and token defaults that are
automatically applied unless you override them in your ``.env`` file.
"""

import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Per-network defaults
# ---------------------------------------------------------------------------
# Each entry contains the V2-style DEX addresses (factory + router), the
# Uniswap V3 addresses (factory / quoter / router), the native wrapped-token
# address (WETH / WMATIC / …), and a short list of popular tokens to watch.
# ---------------------------------------------------------------------------

NETWORK_DEFAULTS: Dict[str, Dict[str, str]] = {
    "ethereum": {
        # Uniswap V2 – Ethereum mainnet
        "UNISWAP_V2_FACTORY": "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
        "UNISWAP_V2_ROUTER":  "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
        # Uniswap V3 – Ethereum mainnet
        "UNISWAP_V3_FACTORY": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "UNISWAP_V3_QUOTER":  "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
        "UNISWAP_V3_ROUTER":  "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        # Wrapped native token
        "WETH_ADDRESS": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        # Popular tokens: WETH, USDC, DAI
        "WATCHED_TOKENS": (
            "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2,"
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48,"
            "0x6B175474E89094C44Da98b954EedeAC495271d0F"
        ),
        # Recommended minimum wallet balance (in native token)
        "MIN_WALLET_BALANCE": "1.0",
        "NATIVE_SYMBOL": "ETH",
    },
    "polygon": {
        # QuickSwap V2 – Polygon PoS (Uniswap V2 fork)
        "UNISWAP_V2_FACTORY": "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32",
        "UNISWAP_V2_ROUTER":  "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
        # Uniswap V3 – Polygon PoS
        "UNISWAP_V3_FACTORY": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "UNISWAP_V3_QUOTER":  "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
        "UNISWAP_V3_ROUTER":  "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        # Wrapped native token (WMATIC)
        "WETH_ADDRESS": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
        # Popular tokens: WMATIC, USDC (PoS), USDT (PoS)
        "WATCHED_TOKENS": (
            "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270,"
            "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174,"
            "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
        ),
        "MIN_WALLET_BALANCE": "500.0",
        "NATIVE_SYMBOL": "MATIC",
    },
    "base": {
        # BaseSwap V2 – Base (Uniswap V2 fork)
        "UNISWAP_V2_FACTORY": "0xFDa619b6d20975be80A10332cD39b9a4b0FAa8BB",
        "UNISWAP_V2_ROUTER":  "0x327Df1E6de05895d2ab08513aaDD9313Fe505d86",
        # Uniswap V3 – Base
        "UNISWAP_V3_FACTORY": "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
        "UNISWAP_V3_QUOTER":  "0x3d4e44Eb1374240CE5F1B136cf668e6E9Bdfb8E0",
        "UNISWAP_V3_ROUTER":  "0x2626664c2603336E57B271c5C0b26F421741e481",
        # Wrapped native token (WETH on Base)
        "WETH_ADDRESS": "0x4200000000000000000000000000000000000006",
        # Popular tokens: WETH, USDbC (bridged USDC), DAI
        "WATCHED_TOKENS": (
            "0x4200000000000000000000000000000000000006,"
            "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA,"
            "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb"
        ),
        "MIN_WALLET_BALANCE": "0.5",
        "NATIVE_SYMBOL": "ETH",
    },
    "arbitrum": {
        # SushiSwap V2 – Arbitrum One (Uniswap V2 fork)
        "UNISWAP_V2_FACTORY": "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
        "UNISWAP_V2_ROUTER":  "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
        # Uniswap V3 – Arbitrum One
        "UNISWAP_V3_FACTORY": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "UNISWAP_V3_QUOTER":  "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
        "UNISWAP_V3_ROUTER":  "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        # Wrapped native token (WETH on Arbitrum)
        "WETH_ADDRESS": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        # Popular tokens: WETH, USDC (native), USDT
        "WATCHED_TOKENS": (
            "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1,"
            "0xaf88d065e77c8cC2239327C5EDb3A432268e5831,"
            "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9"
        ),
        "MIN_WALLET_BALANCE": "0.5",
        "NATIVE_SYMBOL": "ETH",
    },
}

SUPPORTED_NETWORKS = tuple(NETWORK_DEFAULTS.keys())


def _require(key: str) -> str:
    """Return *key* from the environment; raise if absent or empty."""
    value = os.getenv(key, "").strip()
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            "Copy .env.example to .env and fill in your values."
        )
    return value


def _optional(key: str, default: str) -> str:
    return os.getenv(key, default).strip() or default


def _network_default(network: str, key: str, fallback: str = "") -> str:
    """Return the network-specific default for *key*, or *fallback*."""
    return NETWORK_DEFAULTS.get(network, {}).get(key, fallback)


@dataclass
class Config:
    """Centralised, validated configuration object."""

    # ── Network selection ─────────────────────────────────────────────────────
    network: str = field(
        default_factory=lambda: _optional("NETWORK", "ethereum").lower()
    )

    # ── RPC / wallet ──────────────────────────────────────────────────────────
    rpc_url: str = field(default_factory=lambda: _require("RPC_URL"))
    private_key: str = field(default_factory=lambda: _require("PRIVATE_KEY"))

    # ── Strategy ─────────────────────────────────────────────────────────────
    min_profit_eth: Decimal = field(
        default_factory=lambda: Decimal(_optional("MIN_PROFIT_ETH", "0.005"))
    )
    max_trade_eth: Decimal = field(
        default_factory=lambda: Decimal(_optional("MAX_TRADE_ETH", "0.1"))
    )
    slippage_tolerance: Decimal = field(
        default_factory=lambda: Decimal(_optional("SLIPPAGE_TOLERANCE", "0.005"))
    )
    max_gas_price_gwei: int = field(
        default_factory=lambda: int(_optional("MAX_GAS_PRICE_GWEI", "100"))
    )
    poll_interval_seconds: int = field(
        default_factory=lambda: int(_optional("POLL_INTERVAL_SECONDS", "5"))
    )

    # ── Tokens ────────────────────────────────────────────────────────────────
    watched_tokens: List[str] = field(default_factory=list)

    # ── DEX contract addresses ────────────────────────────────────────────────
    uniswap_v2_factory: str = field(default="")
    uniswap_v2_router: str = field(default="")
    uniswap_v3_factory: str = field(default="")
    uniswap_v3_quoter: str = field(default="")
    uniswap_v3_router: str = field(default="")
    weth_address: str = field(default="")

    def __post_init__(self) -> None:
        # ── Validate network ──────────────────────────────────────────────────
        if self.network not in SUPPORTED_NETWORKS:
            raise ValueError(
                f"NETWORK '{self.network}' is not supported. "
                f"Choose one of: {', '.join(SUPPORTED_NETWORKS)}"
            )

        net = self.network

        # ── Resolve address fields from network defaults when not set ─────────
        if not self.uniswap_v2_factory:
            self.uniswap_v2_factory = _optional(
                "UNISWAP_V2_FACTORY", _network_default(net, "UNISWAP_V2_FACTORY")
            )
        if not self.uniswap_v2_router:
            self.uniswap_v2_router = _optional(
                "UNISWAP_V2_ROUTER", _network_default(net, "UNISWAP_V2_ROUTER")
            )
        if not self.uniswap_v3_factory:
            self.uniswap_v3_factory = _optional(
                "UNISWAP_V3_FACTORY", _network_default(net, "UNISWAP_V3_FACTORY")
            )
        if not self.uniswap_v3_quoter:
            self.uniswap_v3_quoter = _optional(
                "UNISWAP_V3_QUOTER", _network_default(net, "UNISWAP_V3_QUOTER")
            )
        if not self.uniswap_v3_router:
            self.uniswap_v3_router = _optional(
                "UNISWAP_V3_ROUTER", _network_default(net, "UNISWAP_V3_ROUTER")
            )
        if not self.weth_address:
            self.weth_address = _optional(
                "WETH_ADDRESS", _network_default(net, "WETH_ADDRESS")
            )

        # ── Resolve watched tokens from network defaults when not set ─────────
        if not self.watched_tokens:
            raw = _optional(
                "WATCHED_TOKENS", _network_default(net, "WATCHED_TOKENS")
            )
            self.watched_tokens = [t.strip() for t in raw.split(",") if t.strip()]

        # ── Strategy parameter validation ─────────────────────────────────────
        if self.min_profit_eth < 0:
            raise ValueError("MIN_PROFIT_ETH must be non-negative")
        if self.max_trade_eth <= 0:
            raise ValueError("MAX_TRADE_ETH must be positive")
        if not (0 < self.slippage_tolerance < 1):
            raise ValueError("SLIPPAGE_TOLERANCE must be between 0 and 1 exclusive")
        if self.max_gas_price_gwei <= 0:
            raise ValueError("MAX_GAS_PRICE_GWEI must be positive")
        if self.poll_interval_seconds <= 0:
            raise ValueError("POLL_INTERVAL_SECONDS must be positive")

    @property
    def native_symbol(self) -> str:
        """Return the ticker of the network's native token (e.g. ETH, MATIC)."""
        return NETWORK_DEFAULTS.get(self.network, {}).get("NATIVE_SYMBOL", "ETH")

    @property
    def min_recommended_balance(self) -> Decimal:
        """Return the recommended minimum wallet balance in native tokens."""
        raw = NETWORK_DEFAULTS.get(self.network, {}).get("MIN_WALLET_BALANCE", "1.0")
        return Decimal(raw)
