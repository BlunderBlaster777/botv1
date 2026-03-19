"""Liquidity Sniper Bot – main entry point.

Usage::

    python -m src.bot

The bot polls all configured token pools at a fixed interval, identifies
price discrepancies between Uniswap V2 and V3 pools, and executes
arbitrage trades when the expected net profit exceeds the configured
minimum.
"""

import logging
import signal
import sys
import time
import types
from itertools import chain
from typing import List, Optional

from web3 import Web3

from src.config import Config
from src.dex.price_feed import Opportunity, PriceFeed
from src.dex.uniswap_v2 import UniswapV2Client
from src.dex.uniswap_v3 import UniswapV3Client
from src.strategy.arbitrage import ArbitrageStats, ArbitrageStrategy
from src.utils.helpers import setup_logging

logger = logging.getLogger("sniper")


def build_web3(config: Config) -> Web3:
    """Return a connected :class:`Web3` instance."""
    w3 = Web3(Web3.HTTPProvider(config.rpc_url))
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to RPC endpoint: {config.rpc_url}")
    logger.info("Connected to chain ID %s", w3.eth.chain_id)
    return w3


def build_clients(
    config: Config, w3: Web3
) -> tuple:
    """Instantiate and return ``(v2_client, v3_client)``."""
    v2 = UniswapV2Client(w3, config.uniswap_v2_factory, config.uniswap_v2_router)
    v3 = UniswapV3Client(
        w3, config.uniswap_v3_factory, config.uniswap_v3_quoter, config.uniswap_v3_router
    )
    return v2, v3


def log_stats(stats: ArbitrageStats) -> None:
    logger.info(
        "Session stats – attempted=%d succeeded=%d failed=%d "
        "net_profit=%.6f ETH gas_spent=%.6f ETH",
        stats.trades_attempted,
        stats.trades_succeeded,
        stats.trades_failed,
        stats.net_profit_eth,
        stats.total_gas_cost_eth,
    )


def run_once(
    price_feed: PriceFeed,
    strategy: ArbitrageStrategy,
) -> None:
    """Perform a single scan-and-execute cycle."""
    logger.debug("Starting scan cycle …")
    opps_by_token = price_feed.scan_all_tokens()

    all_opps: List[Opportunity] = list(chain.from_iterable(opps_by_token.values()))
    if not all_opps:
        logger.debug("No opportunities found this cycle.")
        return

    # Sort globally by descending profit potential
    all_opps.sort(key=lambda o: o.gross_profit_pct, reverse=True)
    logger.info("Found %d total opportunity(ies) across %d token(s).",
                len(all_opps), len(opps_by_token))

    results = strategy.evaluate_opportunities(all_opps)
    for result in results:
        if result.success:
            logger.info(
                "✅ Trade succeeded – token=%s buy=%s sell=%s profit≈%.6f ETH",
                result.opportunity.token[:10],
                result.buy_tx_hash,
                result.sell_tx_hash,
                result.estimated_profit_eth,
            )
        elif result.error:
            logger.debug("⚠️  Trade skipped/failed: %s", result.error)


def main() -> None:
    """Entry point for the Liquidity Sniper Bot."""
    setup_logging()
    logger.info("🚀 Liquidity Sniper Bot starting …")

    config = Config()
    w3 = build_web3(config)
    v2, v3 = build_clients(config, w3)

    wallet = w3.eth.account.from_key(config.private_key)
    logger.info("Wallet: %s", wallet.address)

    price_feed = PriceFeed(config, v2, v3)
    strategy = ArbitrageStrategy(config, w3, v2, v3, wallet.address)

    running = True

    def _stop(signum: int, frame: Optional[types.FrameType]) -> None:
        nonlocal running
        logger.info("Shutdown signal received.")
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    logger.info(
        "Monitoring %d token(s) every %ds. Min profit: %.4f ETH.",
        len(config.watched_tokens),
        config.poll_interval_seconds,
        config.min_profit_eth,
    )

    while running:
        try:
            run_once(price_feed, strategy)
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error in scan cycle: %s", exc, exc_info=True)
        time.sleep(config.poll_interval_seconds)

    log_stats(strategy.stats)
    logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
