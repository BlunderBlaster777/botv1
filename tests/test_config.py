"""Tests for network-defaults and validation logic in src/config.py"""

from unittest.mock import patch

import pytest

from src.config import NETWORK_DEFAULTS, SUPPORTED_NETWORKS, Config


# ── Helpers ───────────────────────────────────────────────────────────────────

BASE_ENV = {
    "RPC_URL": "http://localhost:8545",
    "PRIVATE_KEY": "0x" + "a" * 64,
}


def _make_config(extra_env: dict | None = None) -> Config:
    env = {**BASE_ENV, **(extra_env or {})}
    # Clear any address overrides so network defaults are exercised.
    for key in (
        "NETWORK",
        "UNISWAP_V2_FACTORY",
        "UNISWAP_V2_ROUTER",
        "UNISWAP_V3_FACTORY",
        "UNISWAP_V3_QUOTER",
        "UNISWAP_V3_ROUTER",
        "WETH_ADDRESS",
        "WATCHED_TOKENS",
    ):
        env.setdefault(key, "")
    with patch.dict("os.environ", env, clear=False):
        return Config()


# ── Tests: supported-network table ───────────────────────────────────────────


class TestNetworkDefaults:
    def test_all_supported_networks_present(self):
        for net in SUPPORTED_NETWORKS:
            assert net in NETWORK_DEFAULTS

    def test_each_network_has_required_keys(self):
        required = {
            "UNISWAP_V2_FACTORY",
            "UNISWAP_V2_ROUTER",
            "UNISWAP_V3_FACTORY",
            "UNISWAP_V3_QUOTER",
            "UNISWAP_V3_ROUTER",
            "WETH_ADDRESS",
            "WATCHED_TOKENS",
            "MIN_WALLET_BALANCE",
            "NATIVE_SYMBOL",
        }
        for net in SUPPORTED_NETWORKS:
            missing = required - set(NETWORK_DEFAULTS[net].keys())
            assert not missing, f"Network '{net}' is missing keys: {missing}"

    def test_each_network_has_non_empty_values(self):
        for net, defaults in NETWORK_DEFAULTS.items():
            for key, value in defaults.items():
                assert value, f"Network '{net}' key '{key}' is empty"


# ── Tests: Config defaults per network ───────────────────────────────────────


class TestConfigNetworkSelection:
    def test_default_network_is_ethereum(self):
        cfg = _make_config()
        assert cfg.network == "ethereum"

    @pytest.mark.parametrize("network", SUPPORTED_NETWORKS)
    def test_all_networks_load_without_error(self, network):
        cfg = _make_config({"NETWORK": network})
        assert cfg.network == network

    def test_invalid_network_raises(self):
        with pytest.raises(ValueError, match="not supported"):
            _make_config({"NETWORK": "solana"})

    def test_ethereum_weth_address_auto_set(self):
        cfg = _make_config({"NETWORK": "ethereum"})
        assert cfg.weth_address == NETWORK_DEFAULTS["ethereum"]["WETH_ADDRESS"]

    def test_polygon_weth_address_is_wmatic(self):
        cfg = _make_config({"NETWORK": "polygon"})
        assert cfg.weth_address == NETWORK_DEFAULTS["polygon"]["WETH_ADDRESS"]

    def test_base_weth_address_auto_set(self):
        cfg = _make_config({"NETWORK": "base"})
        assert cfg.weth_address == NETWORK_DEFAULTS["base"]["WETH_ADDRESS"]

    def test_arbitrum_weth_address_auto_set(self):
        cfg = _make_config({"NETWORK": "arbitrum"})
        assert cfg.weth_address == NETWORK_DEFAULTS["arbitrum"]["WETH_ADDRESS"]

    def test_watched_tokens_populated_from_network(self):
        cfg = _make_config({"NETWORK": "arbitrum"})
        assert len(cfg.watched_tokens) >= 1
        assert all(t.startswith("0x") for t in cfg.watched_tokens)

    def test_explicit_weth_override_takes_precedence(self):
        custom = "0xDeaDbeefdEAdbeefdEadbEEFdeadbeEFdEaDbeeF"
        cfg = _make_config({"NETWORK": "ethereum", "WETH_ADDRESS": custom})
        assert cfg.weth_address == custom

    def test_explicit_watched_tokens_override(self):
        custom = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
        cfg = _make_config({"NETWORK": "polygon", "WATCHED_TOKENS": custom})
        assert cfg.watched_tokens == [custom]


# ── Tests: native_symbol and min_recommended_balance properties ───────────────


class TestNativeProperties:
    def test_ethereum_native_symbol(self):
        cfg = _make_config({"NETWORK": "ethereum"})
        assert cfg.native_symbol == "ETH"

    def test_polygon_native_symbol(self):
        cfg = _make_config({"NETWORK": "polygon"})
        assert cfg.native_symbol == "MATIC"

    def test_base_native_symbol(self):
        cfg = _make_config({"NETWORK": "base"})
        assert cfg.native_symbol == "ETH"

    def test_arbitrum_native_symbol(self):
        cfg = _make_config({"NETWORK": "arbitrum"})
        assert cfg.native_symbol == "ETH"

    @pytest.mark.parametrize("network", SUPPORTED_NETWORKS)
    def test_min_recommended_balance_is_positive(self, network):
        cfg = _make_config({"NETWORK": network})
        assert cfg.min_recommended_balance > 0
