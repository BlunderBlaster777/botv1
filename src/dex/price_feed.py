"""Price feed – scans Uniswap pools and identifies price discrepancies.

For each watched token the scanner queries the spot price from all available
Uniswap V2 and V3 pools, then reports which pools offer the token below or
above a calculated reference price.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from src.config import Config
from src.dex.uniswap_v2 import UniswapV2Client
from src.dex.uniswap_v3 import FEE_TIERS, UniswapV3Client

logger = logging.getLogger(__name__)


@dataclass
class PoolPrice:
    """Price observation for a single token in a single pool."""

    token_in: str
    token_out: str
    price: Decimal          # token_out per token_in
    dex: str                # "v2" or "v3"
    fee: Optional[int]      # None for V2; fee tier int for V3
    pool_address: Optional[str]


@dataclass
class Opportunity:
    """A buy-low / sell-high arbitrage opportunity.

    The bot should:
    1. Buy *token* using *quote_token* in *buy_pool* at *buy_price*.
    2. Sell the acquired *token* back to *quote_token* in *sell_pool* at
       *sell_price*.

    *gross_profit_pct* is the percentage price spread before gas / fees.
    """

    token: str
    quote_token: str
    buy_pool: PoolPrice
    sell_pool: PoolPrice
    gross_profit_pct: Decimal


class PriceFeed:
    """Scans all known pools and surfaces arbitrage opportunities."""

    def __init__(
        self,
        config: Config,
        v2_client: UniswapV2Client,
        v3_client: UniswapV3Client,
    ) -> None:
        self.config = config
        self.v2 = v2_client
        self.v3 = v3_client

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _v2_price(self, token_in: str, token_out: str) -> Optional[PoolPrice]:
        """Return a :class:`PoolPrice` for the V2 pair, or ``None``."""
        price = self.v2.get_price(token_in, token_out)
        if price is None:
            return None
        pair_addr = self.v2.get_pair_address(token_in, token_out)
        return PoolPrice(
            token_in=token_in,
            token_out=token_out,
            price=price,
            dex="v2",
            fee=None,
            pool_address=pair_addr,
        )

    def _v3_prices(self, token_in: str, token_out: str) -> List[PoolPrice]:
        """Return :class:`PoolPrice` entries for every V3 fee tier."""
        results: List[PoolPrice] = []
        for fee in FEE_TIERS:
            price = self.v3.get_spot_price(token_in, token_out, fee)
            if price is None or price == 0:
                continue
            pool_addr = self.v3.get_pool_address(token_in, token_out, fee)
            results.append(
                PoolPrice(
                    token_in=token_in,
                    token_out=token_out,
                    price=price,
                    dex="v3",
                    fee=fee,
                    pool_address=pool_addr,
                )
            )
        return results

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch_all_prices(
        self, token: str, quote_token: str
    ) -> List[PoolPrice]:
        """Fetch prices for *token*/*quote_token* from all V2 and V3 pools.

        Returns a list of :class:`PoolPrice` objects (may be empty).
        """
        prices: List[PoolPrice] = []

        v2 = self._v2_price(token, quote_token)
        if v2 is not None:
            prices.append(v2)
            logger.debug("V2 price %s→%s: %s", token[:8], quote_token[:8], v2.price)

        v3_list = self._v3_prices(token, quote_token)
        prices.extend(v3_list)
        for p in v3_list:
            logger.debug(
                "V3 price %s→%s (fee=%s): %s", token[:8], quote_token[:8], p.fee, p.price
            )

        return prices

    def find_opportunities(
        self, token: str, quote_token: str
    ) -> List[Opportunity]:
        """Identify buy-low / sell-high opportunities for *token*/*quote_token*.

        For every pair of pools (A, B) where price_A < price_B, the bot can:
        - Buy *token* cheaply in pool A (pay *quote_token*, receive *token*)
        - Sell *token* expensively in pool B (pay *token*, receive *quote_token*)

        Opportunities are sorted by descending *gross_profit_pct*.
        """
        prices = self.fetch_all_prices(token, quote_token)
        if len(prices) < 2:
            return []

        opportunities: List[Opportunity] = []
        for i, pool_a in enumerate(prices):
            for pool_b in prices[i + 1 :]:
                if pool_a.price == pool_b.price:
                    continue

                buy_pool, sell_pool = (
                    (pool_a, pool_b) if pool_a.price < pool_b.price else (pool_b, pool_a)
                )
                spread = sell_pool.price - buy_pool.price
                pct = spread / buy_pool.price * Decimal(100)

                opportunities.append(
                    Opportunity(
                        token=token,
                        quote_token=quote_token,
                        buy_pool=buy_pool,
                        sell_pool=sell_pool,
                        gross_profit_pct=pct,
                    )
                )

        opportunities.sort(key=lambda o: o.gross_profit_pct, reverse=True)
        return opportunities

    def scan_all_tokens(self) -> Dict[str, List[Opportunity]]:
        """Scan all watched-token / WETH pairs and return opportunities keyed by token.

        Only tokens listed in :attr:`Config.watched_tokens` are checked
        (each paired against WETH).
        """
        weth = self.config.weth_address
        result: Dict[str, List[Opportunity]] = {}
        for token in self.config.watched_tokens:
            if token.lower() == weth.lower():
                continue
            opps = self.find_opportunities(token, weth)
            if opps:
                result[token] = opps
                logger.info(
                    "Token %s: %d opportunity(ies), best spread=%.4f%%",
                    token[:10],
                    len(opps),
                    opps[0].gross_profit_pct,
                )
        return result
