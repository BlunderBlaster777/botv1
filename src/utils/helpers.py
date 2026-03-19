"""Miscellaneous helper utilities."""

import logging
import sys
from decimal import Decimal
from typing import Optional

from web3 import Web3


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure root logger and return a named logger for the bot."""
    fmt = "%(asctime)s [%(levelname)s] %(name)s – %(message)s"
    logging.basicConfig(stream=sys.stdout, level=level, format=fmt)
    return logging.getLogger("sniper")


def to_wei(amount_eth: Decimal, decimals: int = 18) -> int:
    """Convert a human-readable token amount to its integer *wei* representation."""
    return int(amount_eth * Decimal(10**decimals))


def from_wei(amount_wei: int, decimals: int = 18) -> Decimal:
    """Convert an integer *wei* amount to a human-readable decimal value."""
    return Decimal(amount_wei) / Decimal(10**decimals)


def deadline(seconds_from_now: int = 300) -> int:
    """Return a Unix timestamp *seconds_from_now* in the future.

    Used as the ``deadline`` parameter for Uniswap router calls.
    """
    import time

    return int(time.time()) + seconds_from_now


def checksum(address: str) -> str:
    """Return the EIP-55 checksummed form of *address*."""
    return Web3.to_checksum_address(address)


def min_amount_out(amount_in_wei: int, price: Decimal, slippage: Decimal) -> int:
    """Compute the minimum acceptable output amount accounting for slippage.

    Parameters
    ----------
    amount_in_wei:
        Input amount (integer, in the token's smallest unit).
    price:
        Expected exchange rate: output tokens per input token.
    slippage:
        Fractional slippage tolerance, e.g. ``Decimal("0.005")`` for 0.5 %.

    Returns
    -------
    int
        Minimum output amount (integer, in the output token's smallest unit).
    """
    expected_out = Decimal(amount_in_wei) * price
    return int(expected_out * (1 - slippage))


def estimate_gas_cost_eth(gas_used: int, gas_price_wei: int) -> Decimal:
    """Return the gas cost in ETH for *gas_used* units at *gas_price_wei*."""
    return from_wei(gas_used * gas_price_wei)


def profit_after_gas(
    gross_profit_eth: Decimal,
    gas_used: int,
    gas_price_wei: int,
) -> Decimal:
    """Return the net profit in ETH after subtracting gas costs."""
    return gross_profit_eth - estimate_gas_cost_eth(gas_used, gas_price_wei)


def is_valid_address(address: Optional[str]) -> bool:
    """Return ``True`` if *address* is a valid Ethereum address string."""
    if not address:
        return False
    try:
        Web3.to_checksum_address(address)
        return True
    except (ValueError, TypeError):
        return False
