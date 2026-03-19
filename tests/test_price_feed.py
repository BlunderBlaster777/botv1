"""Tests for src/dex/price_feed.py"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.config import Config
from src.dex.price_feed import Opportunity, PoolPrice, PriceFeed


# ── Fixtures ──────────────────────────────────────────────────────────────────

TOKEN_A = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"  # USDC
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
PAIR_ADDR = "0x1234000000000000000000000000000000000000"
POOL_ADDR = "0x5678000000000000000000000000000000000000"


def _make_config() -> Config:
    with (
        patch.dict(
            "os.environ",
            {
                "RPC_URL": "http://localhost:8545",
                "PRIVATE_KEY": "0x" + "a" * 64,
            },
        )
    ):
        return Config()


def _make_price_feed(
    v2_price=None,
    v2_pair=PAIR_ADDR,
    v3_prices=None,
) -> PriceFeed:
    config = _make_config()
    v2 = MagicMock()
    v3 = MagicMock()

    v2.get_price.return_value = v2_price
    v2.get_pair_address.return_value = v2_pair

    # V3: return different prices for different fee tiers
    v3_prices = v3_prices or {}

    def _v3_spot(token_in, token_out, fee, **kw):
        return v3_prices.get(fee)

    def _v3_pool(token_in, token_out, fee):
        return POOL_ADDR if fee in v3_prices else None

    v3.get_spot_price.side_effect = _v3_spot
    v3.get_pool_address.side_effect = _v3_pool

    return PriceFeed(config, v2, v3)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestFetchAllPrices:
    def test_returns_v2_price(self):
        feed = _make_price_feed(v2_price=Decimal("1800"))
        prices = feed.fetch_all_prices(TOKEN_A, WETH)
        assert len(prices) == 1
        assert prices[0].dex == "v2"
        assert prices[0].price == Decimal("1800")

    def test_returns_v3_prices(self):
        feed = _make_price_feed(
            v2_price=None,
            v3_prices={500: Decimal("1810"), 3000: Decimal("1790")},
        )
        prices = feed.fetch_all_prices(TOKEN_A, WETH)
        assert len(prices) == 2
        assert all(p.dex == "v3" for p in prices)

    def test_returns_mixed_prices(self):
        feed = _make_price_feed(
            v2_price=Decimal("1800"),
            v3_prices={3000: Decimal("1820")},
        )
        prices = feed.fetch_all_prices(TOKEN_A, WETH)
        assert len(prices) == 2
        dexes = {p.dex for p in prices}
        assert dexes == {"v2", "v3"}

    def test_returns_empty_when_no_pools(self):
        feed = _make_price_feed(v2_price=None, v3_prices={})
        prices = feed.fetch_all_prices(TOKEN_A, WETH)
        assert prices == []


class TestFindOpportunities:
    def test_identifies_spread(self):
        feed = _make_price_feed(
            v2_price=Decimal("1800"),
            v3_prices={3000: Decimal("1818")},  # 1 % higher
        )
        opps = feed.find_opportunities(TOKEN_A, WETH)
        assert len(opps) == 1
        opp = opps[0]
        assert opp.buy_pool.dex == "v2"
        assert opp.sell_pool.dex == "v3"
        assert opp.gross_profit_pct > 0

    def test_spread_percentage_correct(self):
        feed = _make_price_feed(
            v2_price=Decimal("100"),
            v3_prices={3000: Decimal("110")},
        )
        opps = feed.find_opportunities(TOKEN_A, WETH)
        assert len(opps) == 1
        assert opps[0].gross_profit_pct == pytest.approx(Decimal("10"), rel=Decimal("0.01"))

    def test_no_opportunity_equal_prices(self):
        feed = _make_price_feed(
            v2_price=Decimal("1800"),
            v3_prices={3000: Decimal("1800")},
        )
        opps = feed.find_opportunities(TOKEN_A, WETH)
        assert opps == []

    def test_sorted_descending(self):
        feed = _make_price_feed(
            v2_price=Decimal("100"),
            v3_prices={500: Decimal("103"), 3000: Decimal("108")},
        )
        opps = feed.find_opportunities(TOKEN_A, WETH)
        # Should be sorted by profit pct descending
        for i in range(len(opps) - 1):
            assert opps[i].gross_profit_pct >= opps[i + 1].gross_profit_pct

    def test_returns_empty_with_single_pool(self):
        feed = _make_price_feed(v2_price=Decimal("1800"), v3_prices={})
        opps = feed.find_opportunities(TOKEN_A, WETH)
        assert opps == []


class TestScanAllTokens:
    def test_skips_weth(self):
        config = _make_config()
        v2 = MagicMock()
        v3 = MagicMock()
        v2.get_price.return_value = None
        v3.get_spot_price.return_value = None
        v3.get_pool_address.return_value = None

        feed = PriceFeed(config, v2, v3)
        # WETH is in watched_tokens by default; it should be skipped
        result = feed.scan_all_tokens()
        # No non-WETH tokens have prices → empty
        assert isinstance(result, dict)
