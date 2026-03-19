"""Tests for src/strategy/arbitrage.py"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.dex.price_feed import Opportunity, PoolPrice
from src.strategy.arbitrage import ArbitrageStrategy, TradeResult


# ── Helpers ───────────────────────────────────────────────────────────────────

TOKEN = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
WALLET = "0xAbCdEf0000000000000000000000000000000001"


def _make_config():
    with patch.dict(
        "os.environ",
        {
            "RPC_URL": "http://localhost:8545",
            "PRIVATE_KEY": "0x" + "a" * 64,
            "MIN_PROFIT_ETH": "0.001",
            "MAX_TRADE_ETH": "0.1",
            "SLIPPAGE_TOLERANCE": "0.005",
            "MAX_GAS_PRICE_GWEI": "50",
        },
    ):
        from src.config import Config
        return Config()


def _make_opportunity(buy_price: Decimal, sell_price: Decimal) -> Opportunity:
    buy_pool = PoolPrice(
        token_in=TOKEN, token_out=WETH, price=buy_price,
        dex="v2", fee=None, pool_address="0x1111111111111111111111111111111111111111"
    )
    sell_pool = PoolPrice(
        token_in=TOKEN, token_out=WETH, price=sell_price,
        dex="v3", fee=3000, pool_address="0x2222222222222222222222222222222222222222"
    )
    spread_pct = (sell_price - buy_price) / buy_price * Decimal(100)
    return Opportunity(
        token=TOKEN,
        quote_token=WETH,
        buy_pool=buy_pool,
        sell_pool=sell_pool,
        gross_profit_pct=spread_pct,
    )


def _make_strategy(config=None) -> ArbitrageStrategy:
    cfg = config or _make_config()
    w3 = MagicMock()
    w3.eth.gas_price = 20 * 10**9  # 20 Gwei
    v2 = MagicMock()
    v3 = MagicMock()
    return ArbitrageStrategy(cfg, w3, v2, v3, WALLET)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestIsProfitable:
    def test_highly_profitable(self):
        strat = _make_strategy()
        opp = _make_opportunity(Decimal("100"), Decimal("110"))  # 10 %
        gas_price = 20 * 10**9
        assert strat._is_profitable(opp, gas_price)

    def test_unprofitable_small_spread(self):
        strat = _make_strategy()
        # Tiny spread – gas will eat all profit
        opp = _make_opportunity(Decimal("1000"), Decimal("1000.001"))
        gas_price = 100 * 10**9  # expensive gas
        assert not strat._is_profitable(opp, gas_price)


class TestExecute:
    def test_skips_unprofitable(self):
        strat = _make_strategy()
        opp = _make_opportunity(Decimal("1000"), Decimal("1000.001"))
        strat.w3.eth.gas_price = 200 * 10**9  # extreme gas

        result = strat.execute(opp)
        assert not result.success
        assert result.error is not None
        assert strat.stats.trades_failed == 1
        assert strat.stats.trades_succeeded == 0

    def test_executes_profitable_trade(self):
        strat = _make_strategy()
        opp = _make_opportunity(Decimal("100"), Decimal("115"))  # 15 %

        # Mock buy/sell legs
        strat.v2.approve_token.return_value = "0xapprove"
        strat.v2.swap_exact_tokens_for_tokens.return_value = "0xbuy"
        strat.v3.approve_token.return_value = "0xapprove2"
        strat.v3.exact_input_single.return_value = "0xsell"

        result = strat.execute(opp)
        assert result.success
        assert result.buy_tx_hash == "0xbuy"
        assert result.sell_tx_hash == "0xsell"
        assert strat.stats.trades_succeeded == 1

    def test_handles_buy_failure(self):
        strat = _make_strategy()
        opp = _make_opportunity(Decimal("100"), Decimal("115"))

        strat.v2.approve_token.side_effect = Exception("network error")

        result = strat.execute(opp)
        assert not result.success
        assert "Buy leg" in (result.error or "")

    def test_handles_sell_failure(self):
        strat = _make_strategy()
        opp = _make_opportunity(Decimal("100"), Decimal("115"))

        strat.v2.approve_token.return_value = "0xapprove"
        strat.v2.swap_exact_tokens_for_tokens.return_value = "0xbuy"
        strat.v3.exact_input_single.side_effect = Exception("revert")

        result = strat.execute(opp)
        assert not result.success
        assert "Sell leg" in (result.error or "")


class TestEvaluateOpportunities:
    def test_only_executes_once_per_token(self):
        strat = _make_strategy()

        opp1 = _make_opportunity(Decimal("100"), Decimal("115"))
        opp2 = _make_opportunity(Decimal("100"), Decimal("112"))
        opp2.token = TOKEN  # same token

        strat.v2.approve_token.return_value = "0xa"
        strat.v2.swap_exact_tokens_for_tokens.return_value = "0xbuy"
        strat.v3.approve_token.return_value = "0xa"
        strat.v3.exact_input_single.return_value = "0xsell"

        results = strat.evaluate_opportunities([opp1, opp2])
        # Only one trade for the same token
        executed = [r for r in results if r.success]
        assert len(executed) == 1

    def test_returns_empty_for_no_opportunities(self):
        strat = _make_strategy()
        results = strat.evaluate_opportunities([])
        assert results == []
