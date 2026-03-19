"""Configuration management for the Liquidity Sniper Bot.

Reads all settings from environment variables (loaded from a ``.env`` file
when present via *python-dotenv*).  A single :class:`Config` instance is
created at module-import time and shared across the application.
"""

import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List

from dotenv import load_dotenv

load_dotenv()


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


@dataclass
class Config:
    """Centralised, validated configuration object."""

    # ── Network ──────────────────────────────────────────────────────────────
    rpc_url: str = field(default_factory=lambda: _require("RPC_URL"))

    # ── Wallet ────────────────────────────────────────────────────────────────
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
    watched_tokens: List[str] = field(
        default_factory=lambda: [
            t.strip()
            for t in _optional(
                "WATCHED_TOKENS",
                # WETH, USDC, DAI – sensible defaults on mainnet
                "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2,"
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48,"
                "0x6B175474E89094C44Da98b954EedeAC495271d0F",
            ).split(",")
            if t.strip()
        ]
    )

    # ── Uniswap contract addresses ────────────────────────────────────────────
    uniswap_v2_factory: str = field(
        default_factory=lambda: _optional(
            "UNISWAP_V2_FACTORY", "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
        )
    )
    uniswap_v2_router: str = field(
        default_factory=lambda: _optional(
            "UNISWAP_V2_ROUTER", "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
        )
    )
    uniswap_v3_factory: str = field(
        default_factory=lambda: _optional(
            "UNISWAP_V3_FACTORY", "0x1F98431c8aD98523631AE4a59f267346ea31F984"
        )
    )
    uniswap_v3_quoter: str = field(
        default_factory=lambda: _optional(
            "UNISWAP_V3_QUOTER", "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"
        )
    )
    uniswap_v3_router: str = field(
        default_factory=lambda: _optional(
            "UNISWAP_V3_ROUTER", "0xE592427A0AEce92De3Edee1F18E0157C05861564"
        )
    )
    weth_address: str = field(
        default_factory=lambda: _optional(
            "WETH_ADDRESS", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
        )
    )

    def __post_init__(self) -> None:
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
