"""Tests for src/utils/helpers.py"""

from decimal import Decimal

import pytest

from src.utils.helpers import (
    estimate_gas_cost_eth,
    from_wei,
    is_valid_address,
    min_amount_out,
    profit_after_gas,
    to_wei,
)


class TestToWei:
    def test_one_ether(self):
        assert to_wei(Decimal("1")) == 10**18

    def test_fractional(self):
        assert to_wei(Decimal("0.5")) == 5 * 10**17

    def test_custom_decimals(self):
        # USDC has 6 decimals
        assert to_wei(Decimal("1"), decimals=6) == 10**6


class TestFromWei:
    def test_one_ether(self):
        assert from_wei(10**18) == Decimal("1")

    def test_fractional(self):
        assert from_wei(5 * 10**17) == Decimal("0.5")

    def test_custom_decimals(self):
        assert from_wei(10**6, decimals=6) == Decimal("1")


class TestMinAmountOut:
    def test_no_slippage(self):
        # price = 2 tokens out per token in, 0 slippage → expect exactly 2 * amount_in
        result = min_amount_out(10**18, Decimal("2"), Decimal("0"))
        assert result == 2 * 10**18

    def test_with_slippage(self):
        # price = 1, slippage = 0.01 (1 %)
        result = min_amount_out(10**18, Decimal("1"), Decimal("0.01"))
        expected = int(Decimal("10") ** 18 * Decimal("0.99"))
        assert result == expected

    def test_zero_amount(self):
        assert min_amount_out(0, Decimal("2"), Decimal("0.005")) == 0


class TestEstimateGasCostEth:
    def test_basic(self):
        gas_used = 150_000
        gas_price_wei = 20 * 10**9  # 20 Gwei
        cost = estimate_gas_cost_eth(gas_used, gas_price_wei)
        # 150_000 * 20e9 = 3e15 wei = 0.003 ETH
        assert cost == Decimal("0.003")

    def test_zero_gas(self):
        assert estimate_gas_cost_eth(0, 10**9) == Decimal(0)


class TestProfitAfterGas:
    def test_profitable(self):
        gross = Decimal("0.01")
        gas_used = 150_000
        gas_price_wei = 20 * 10**9  # 20 Gwei → 0.003 ETH
        net = profit_after_gas(gross, gas_used, gas_price_wei)
        assert net == gross - Decimal("3000000000000000") / Decimal(10**18)

    def test_unprofitable(self):
        gross = Decimal("0.001")
        gas_used = 300_000
        gas_price_wei = 100 * 10**9  # very high gas
        net = profit_after_gas(gross, gas_used, gas_price_wei)
        assert net < 0


class TestIsValidAddress:
    def test_valid_checksummed(self):
        assert is_valid_address("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")

    def test_valid_lowercase(self):
        assert is_valid_address("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2")

    def test_invalid(self):
        assert not is_valid_address("not_an_address")

    def test_none(self):
        assert not is_valid_address(None)

    def test_empty(self):
        assert not is_valid_address("")
