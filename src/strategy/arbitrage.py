"""Arbitrage strategy – evaluates opportunities and executes trades.

Given a list of :class:`~src.dex.price_feed.Opportunity` objects the
:class:`ArbitrageStrategy` decides whether an opportunity is worth
executing (net profit after gas exceeds *min_profit_eth*) and, if so,
performs the two-leg trade:

1. **Buy leg** – swap *quote_token* → *token* in the cheaper pool.
2. **Sell leg** – swap *token* → *quote_token* in the more expensive pool.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Tuple

from web3 import Web3

from src.config import Config
from src.dex.price_feed import Opportunity, PoolPrice
from src.dex.uniswap_v2 import UniswapV2Client
from src.dex.uniswap_v3 import UniswapV3Client
from src.utils.helpers import (
    checksum,
    estimate_gas_cost_eth,
    from_wei,
    min_amount_out,
    to_wei,
)

logger = logging.getLogger(__name__)

# Estimated gas usage for each swap type (conservative upper bounds)
_GAS_V2_SWAP = 150_000
_GAS_V3_SWAP = 180_000


@dataclass
class TradeResult:
    """Outcome of an attempted two-leg arbitrage trade."""

    opportunity: Opportunity
    buy_tx_hash: Optional[str] = None
    sell_tx_hash: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    estimated_profit_eth: Decimal = Decimal(0)
    actual_gas_cost_eth: Decimal = Decimal(0)


@dataclass
class ArbitrageStats:
    """Running statistics for the current bot session."""

    trades_attempted: int = 0
    trades_succeeded: int = 0
    trades_failed: int = 0
    total_profit_eth: Decimal = field(default_factory=Decimal)
    total_gas_cost_eth: Decimal = field(default_factory=Decimal)

    @property
    def net_profit_eth(self) -> Decimal:
        return self.total_profit_eth - self.total_gas_cost_eth


class ArbitrageStrategy:
    """Evaluates arbitrage opportunities and executes profitable trades."""

    def __init__(
        self,
        config: Config,
        web3: Web3,
        v2_client: UniswapV2Client,
        v3_client: UniswapV3Client,
        wallet_address: str,
    ) -> None:
        self.config = config
        self.w3 = web3
        self.v2 = v2_client
        self.v3 = v3_client
        self.wallet = checksum(wallet_address)
        self.stats = ArbitrageStats()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _current_gas_price_wei(self) -> int:
        """Return the current network gas price in wei, capped by config."""
        network_price = self.w3.eth.gas_price
        max_price = self.config.max_gas_price_gwei * 10**9
        return min(network_price, max_price)

    def _gas_for_pool(self, pool: PoolPrice) -> int:
        return _GAS_V3_SWAP if pool.dex == "v3" else _GAS_V2_SWAP

    def _estimate_net_profit(
        self,
        opportunity: Opportunity,
        amount_in_eth: Decimal,
        gas_price_wei: int,
    ) -> Tuple[Decimal, Decimal]:
        """Return ``(gross_profit_eth, gas_cost_eth)`` for the given opportunity.

        *gross_profit_eth* is a rough estimate based on the spot price spread.
        """
        spread_fraction = opportunity.gross_profit_pct / Decimal(100)
        gross = amount_in_eth * spread_fraction

        total_gas = self._gas_for_pool(opportunity.buy_pool) + self._gas_for_pool(
            opportunity.sell_pool
        )
        gas_cost = estimate_gas_cost_eth(total_gas, gas_price_wei)
        return gross, gas_cost

    def _is_profitable(self, opportunity: Opportunity, gas_price_wei: int) -> bool:
        """Return ``True`` if the opportunity passes the minimum-profit threshold."""
        gross, gas_cost = self._estimate_net_profit(
            opportunity, self.config.max_trade_eth, gas_price_wei
        )
        net = gross - gas_cost
        logger.debug(
            "Opportunity spread=%.4f%%, gross=%.6f ETH, gas=%.6f ETH, net=%.6f ETH",
            opportunity.gross_profit_pct,
            gross,
            gas_cost,
            net,
        )
        return net >= self.config.min_profit_eth

    # ── Buy / sell helpers ────────────────────────────────────────────────────

    def _execute_buy(
        self,
        pool: PoolPrice,
        amount_in_wei: int,
        gas_price_wei: int,
    ) -> Optional[str]:
        """Execute the buy leg: swap *quote_token* → *token* in *pool*.

        Returns the transaction hash, or ``None`` on failure.
        """
        slippage = self.config.slippage_tolerance
        amount_out_min = min_amount_out(amount_in_wei, pool.price, slippage)

        try:
            if pool.dex == "v2":
                # Approve router to spend quote_token before swapping quote_token → token
                self.v2.approve_token(
                    token_address=pool.token_out,
                    spender=self.v2.router.address,
                    amount_wei=amount_in_wei,
                    sender=self.wallet,
                    private_key=self.config.private_key,
                    gas_price_wei=gas_price_wei,
                )
                return self.v2.swap_exact_tokens_for_tokens(
                    amount_in_wei=amount_in_wei,
                    amount_out_min_wei=amount_out_min,
                    path=[pool.token_out, pool.token_in],
                    recipient=self.wallet,
                    sender=self.wallet,
                    private_key=self.config.private_key,
                    gas_price_wei=gas_price_wei,
                )
            # V3
            assert pool.fee is not None
            self.v3.approve_token(
                token_address=pool.token_out,
                spender=self.v3.router.address,
                amount_wei=amount_in_wei,
                sender=self.wallet,
                private_key=self.config.private_key,
                gas_price_wei=gas_price_wei,
            )
            return self.v3.exact_input_single(
                token_in=pool.token_out,
                token_out=pool.token_in,
                fee=pool.fee,
                amount_in_wei=amount_in_wei,
                amount_out_minimum=amount_out_min,
                recipient=self.wallet,
                sender=self.wallet,
                private_key=self.config.private_key,
                gas_price_wei=gas_price_wei,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Buy leg failed: %s", exc)
            return None

    def _execute_sell(
        self,
        pool: PoolPrice,
        amount_in_wei: int,
        gas_price_wei: int,
    ) -> Optional[str]:
        """Execute the sell leg: swap *token* → *quote_token* in *pool*.

        Returns the transaction hash, or ``None`` on failure.
        """
        slippage = self.config.slippage_tolerance
        sell_price = Decimal(1) / pool.price if pool.price != 0 else Decimal(0)
        amount_out_min = min_amount_out(amount_in_wei, sell_price, slippage)

        try:
            if pool.dex == "v2":
                self.v2.approve_token(
                    token_address=pool.token_in,
                    spender=self.v2.router.address,
                    amount_wei=amount_in_wei,
                    sender=self.wallet,
                    private_key=self.config.private_key,
                    gas_price_wei=gas_price_wei,
                )
                return self.v2.swap_exact_tokens_for_tokens(
                    amount_in_wei=amount_in_wei,
                    amount_out_min_wei=amount_out_min,
                    path=[pool.token_in, pool.token_out],
                    recipient=self.wallet,
                    sender=self.wallet,
                    private_key=self.config.private_key,
                    gas_price_wei=gas_price_wei,
                )
            # V3
            assert pool.fee is not None
            self.v3.approve_token(
                token_address=pool.token_in,
                spender=self.v3.router.address,
                amount_wei=amount_in_wei,
                sender=self.wallet,
                private_key=self.config.private_key,
                gas_price_wei=gas_price_wei,
            )
            return self.v3.exact_input_single(
                token_in=pool.token_in,
                token_out=pool.token_out,
                fee=pool.fee,
                amount_in_wei=amount_in_wei,
                amount_out_minimum=amount_out_min,
                recipient=self.wallet,
                sender=self.wallet,
                private_key=self.config.private_key,
                gas_price_wei=gas_price_wei,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Sell leg failed: %s", exc)
            return None

    # ── Public API ────────────────────────────────────────────────────────────

    def execute(self, opportunity: Opportunity) -> TradeResult:
        """Attempt to execute a two-leg arbitrage trade.

        1. Evaluates profitability (including gas estimate).
        2. Executes buy leg (quote_token → token in cheap pool).
        3. Executes sell leg (token → quote_token in expensive pool).

        Returns a :class:`TradeResult` with full details.
        """
        result = TradeResult(opportunity=opportunity)
        self.stats.trades_attempted += 1

        gas_price_wei = self._current_gas_price_wei()

        if not self._is_profitable(opportunity, gas_price_wei):
            result.error = "Below minimum profit threshold"
            logger.info(
                "Skipping opportunity – spread=%.4f%% below profit threshold",
                opportunity.gross_profit_pct,
            )
            self.stats.trades_failed += 1
            return result

        amount_in_wei = to_wei(self.config.max_trade_eth)
        gross, gas_cost = self._estimate_net_profit(
            opportunity,
            self.config.max_trade_eth,
            gas_price_wei,
        )
        result.estimated_profit_eth = gross - gas_cost
        result.actual_gas_cost_eth = gas_cost

        logger.info(
            "Executing arbitrage: %s spread=%.4f%% est_profit=%.6f ETH",
            opportunity.token[:10],
            opportunity.gross_profit_pct,
            result.estimated_profit_eth,
        )

        # ── Leg 1: Buy token in the cheaper pool ──────────────────────────────
        buy_hash = self._execute_buy(
            opportunity.buy_pool, amount_in_wei, gas_price_wei
        )
        if buy_hash is None:
            result.error = "Buy leg failed"
            self.stats.trades_failed += 1
            return result
        result.buy_tx_hash = buy_hash
        logger.info("Buy leg confirmed: %s", buy_hash)

        # ── Leg 2: Sell token in the more expensive pool ──────────────────────
        sell_hash = self._execute_sell(
            opportunity.sell_pool, amount_in_wei, gas_price_wei
        )
        if sell_hash is None:
            result.error = "Sell leg failed (buy already sent – manual recovery needed)"
            self.stats.trades_failed += 1
            return result
        result.sell_tx_hash = sell_hash
        result.success = True
        logger.info("Sell leg confirmed: %s", sell_hash)

        self.stats.trades_succeeded += 1
        self.stats.total_profit_eth += gross
        self.stats.total_gas_cost_eth += gas_cost
        return result

    def evaluate_opportunities(self, opportunities: List[Opportunity]) -> List[TradeResult]:
        """Evaluate and optionally execute a ranked list of opportunities.

        Returns one :class:`TradeResult` per executed trade.
        Only the first (most profitable) viable opportunity per token is
        executed to avoid double-spending.
        """
        executed_tokens: set = set()
        results: List[TradeResult] = []

        for opp in opportunities:
            if opp.token in executed_tokens:
                continue
            result = self.execute(opp)
            results.append(result)
            if result.success:
                executed_tokens.add(opp.token)

        return results
