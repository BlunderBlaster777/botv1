# botv1 – Liquidity Sniper Bot

A Python bot that monitors Uniswap V2 and V3 pools across **Ethereum, Polygon,
Base, and Arbitrum**, identifies price discrepancies between pools, and executes
atomic buy-low / sell-high arbitrage trades to capture the spread.

---

## How It Works

1. **Scan** – Every *N* seconds the bot queries spot prices for each watched
   token (paired against the wrapped native token) from all active V2 and V3
   pools on the selected chain.
2. **Identify** – When the same token trades at different prices in two pools
   (e.g. cheaper in V2, more expensive in V3), an `Opportunity` object is
   created with the calculated spread percentage.
3. **Evaluate** – The strategy estimates the net profit after gas costs.
   Only opportunities that exceed `MIN_PROFIT_ETH` are executed.
4. **Execute** – Two sequential transactions are submitted:
   - **Buy leg** – swap `quote_token → token` in the cheaper pool.
   - **Sell leg** – swap `token → quote_token` in the more expensive pool.

---

## Project Structure

```
botv1/
├── src/
│   ├── bot.py                  # Entry point – main event loop
│   ├── config.py               # Environment-based configuration
│   ├── dex/
│   │   ├── uniswap_v2.py       # Uniswap V2 price queries & swaps
│   │   ├── uniswap_v3.py       # Uniswap V3 price queries & swaps
│   │   └── price_feed.py       # Cross-pool price scanner
│   ├── strategy/
│   │   └── arbitrage.py        # Profit evaluation & trade execution
│   └── utils/
│       └── helpers.py          # Wei conversion, gas utilities, etc.
├── tests/
│   ├── test_helpers.py
│   ├── test_price_feed.py
│   ├── test_arbitrage.py
│   └── test_config.py
├── .env.example                # Configuration template (copy to .env)
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/BlunderBlaster777/botv1.git
cd botv1
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and follow the numbered steps inside it.  At minimum you must
fill in:

| Variable | Description |
|---|---|
| `NETWORK` | Target chain: `ethereum`, `polygon`, `base`, or `arbitrum` |
| `RPC_URL` | JSON-RPC endpoint (Infura / Alchemy / local node) |
| `PRIVATE_KEY` | Private key of the **dedicated bot wallet** |

All contract addresses and token lists are **automatically set** based on
your chosen `NETWORK`.  You only need to override them if you want a custom
configuration.

> ⚠️ **Never commit your `.env` file or expose your private key.**

### 3. Fund the bot wallet

The wallet must hold enough native tokens to cover:
- **Trade amounts** – up to `MAX_TRADE_ETH` per leg
- **Gas fees** – each trade submits 2–4 transactions

Recommended **minimum starting balances**:

| Network | Recommended Balance | Notes |
|---|---|---|
| Ethereum | **1 ETH** | Gas is expensive; budget for several trades |
| Polygon | **500 MATIC** | Gas is cheap (~0.01 MATIC/tx) |
| Base | **0.5 ETH** | L2 gas is cheap (~$0.01/tx) |
| Arbitrum | **0.5 ETH** | L2 gas is cheap (~$0.02/tx) |

> 💡 The bot logs a warning at startup if your wallet balance is below the
> recommended minimum for the selected network.

### 4. Run

```bash
python -m src.bot
```

The bot prints structured logs to stdout:

```
2024-01-01 12:00:00 [INFO] sniper – 🚀 Liquidity Sniper Bot starting …
2024-01-01 12:00:00 [INFO] sniper – Network: ETHEREUM
2024-01-01 12:00:01 [INFO] sniper – Connected to chain ID 1
2024-01-01 12:00:01 [INFO] sniper – Wallet: 0xYourWallet…
2024-01-01 12:00:01 [INFO] sniper – Wallet balance: 1.250000 ETH  (recommended minimum: 1.0 ETH)
2024-01-01 12:00:01 [INFO] sniper – Monitoring 3 token(s) every 5s. Min profit: 0.0050 ETH.
2024-01-01 12:00:06 [INFO] sniper – Token 0xA0b86991: 1 opportunity(ies), best spread=0.3142%
```

### 5. Run tests

```bash
pytest tests/ -v
```

---

## Supported Networks

### Ethereum Mainnet

| Item | Value |
|---|---|
| `NETWORK` | `ethereum` |
| V2 DEX | Uniswap V2 |
| V3 DEX | Uniswap V3 |
| Wrapped native | WETH `0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2` |
| Default tokens | WETH, USDC, DAI |
| Recommended wallet | **1 ETH** |
| RPC example | `https://mainnet.infura.io/v3/YOUR_KEY` |

### Polygon PoS

| Item | Value |
|---|---|
| `NETWORK` | `polygon` |
| V2 DEX | QuickSwap V2 (Uniswap V2 fork) |
| V3 DEX | Uniswap V3 |
| Wrapped native | WMATIC `0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270` |
| Default tokens | WMATIC, USDC (PoS), USDT (PoS) |
| Recommended wallet | **500 MATIC** |
| RPC example | `https://polygon-mainnet.infura.io/v3/YOUR_KEY` |

### Base (Coinbase L2)

| Item | Value |
|---|---|
| `NETWORK` | `base` |
| V2 DEX | BaseSwap V2 (Uniswap V2 fork) |
| V3 DEX | Uniswap V3 |
| Wrapped native | WETH `0x4200000000000000000000000000000000000006` |
| Default tokens | WETH, USDbC, DAI |
| Recommended wallet | **0.5 ETH** |
| RPC example | `https://mainnet.base.org` |

### Arbitrum One

| Item | Value |
|---|---|
| `NETWORK` | `arbitrum` |
| V2 DEX | SushiSwap V2 (Uniswap V2 fork) |
| V3 DEX | Uniswap V3 |
| Wrapped native | WETH `0x82aF49447D8a07e3bd95BD0d56f35241523fBab1` |
| Default tokens | WETH, USDC (native), USDT |
| Recommended wallet | **0.5 ETH** |
| RPC example | `https://arbitrum-mainnet.infura.io/v3/YOUR_KEY` |

---

## Configuration Reference

All settings are loaded from environment variables (or a `.env` file).

### Required

| Variable | Description |
|---|---|
| `RPC_URL` | JSON-RPC URL for the target network |
| `PRIVATE_KEY` | Bot wallet private key (hex, 0x prefix) |

### Network

| Variable | Default | Description |
|---|---|---|
| `NETWORK` | `ethereum` | Target chain (`ethereum`, `polygon`, `base`, `arbitrum`) |

### Strategy

| Variable | Default | Description |
|---|---|---|
| `MIN_PROFIT_ETH` | `0.005` | Min net profit (native token) to execute a trade |
| `MAX_TRADE_ETH` | `0.1` | Max native tokens spent per trade leg |
| `SLIPPAGE_TOLERANCE` | `0.005` | Slippage fraction (0.005 = 0.5 %) |
| `MAX_GAS_PRICE_GWEI` | `100` | Cap on gas price (Gwei) |
| `POLL_INTERVAL_SECONDS` | `5` | Delay between scan cycles (seconds) |

### Tokens & Contracts (optional overrides)

| Variable | Default | Description |
|---|---|---|
| `WATCHED_TOKENS` | Network default | Comma-separated ERC-20 addresses to monitor |
| `UNISWAP_V2_FACTORY` | Network default | V2 DEX factory address |
| `UNISWAP_V2_ROUTER` | Network default | V2 DEX router address |
| `UNISWAP_V3_FACTORY` | Network default | Uniswap V3 factory address |
| `UNISWAP_V3_QUOTER` | Network default | Uniswap V3 quoter address |
| `UNISWAP_V3_ROUTER` | Network default | Uniswap V3 swap router address |
| `WETH_ADDRESS` | Network default | Wrapped native token address |

---

## Switching Networks

To switch from Ethereum to, for example, Arbitrum:

1. Open your `.env` file.
2. Change `NETWORK=ethereum` to `NETWORK=arbitrum`.
3. Update `RPC_URL` to an Arbitrum-compatible endpoint.
4. Optionally update `WATCHED_TOKENS` (or leave blank for Arbitrum defaults).
5. Restart the bot.

All DEX contract addresses are automatically updated when you change `NETWORK`.

---

## Security Checklist

- [ ] `.env` is in `.gitignore` and has never been committed
- [ ] Bot wallet holds only the minimum balance needed
- [ ] Private key is stored only in `.env`, not in code or logs
- [ ] Token approvals are revoked when the bot is not running
- [ ] RPC API key is kept private (use environment variables, not hardcoded)

---

## Disclaimer

This software is provided for educational purposes only. Trading
cryptocurrencies carries significant financial risk. You could lose all
funds in the trading wallet. **Use at your own risk.**

