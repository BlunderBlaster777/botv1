# botv1 – Liquidity Sniper Bot

A Python bot that monitors Uniswap V2 and V3 pools, identifies price
discrepancies between pools, and executes atomic buy-low / sell-high
arbitrage trades to capture the spread.

---

## How It Works

1. **Scan** – Every *N* seconds the bot queries spot prices for each
   watched token (paired against WETH) from all active Uniswap V2 pairs
   and V3 fee-tier pools.
2. **Identify** – When the same token trades at different prices in two
   pools (e.g. cheaper in V2, more expensive in V3), an `Opportunity`
   object is created with the calculated spread percentage.
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
│   └── test_arbitrage.py
├── .env.example                # Configuration template
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

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` and fill in at minimum:

| Variable | Description |
|---|---|
| `RPC_URL` | JSON-RPC endpoint (Infura / Alchemy / local node) |
| `PRIVATE_KEY` | Private key of the trading wallet |
| `MIN_PROFIT_ETH` | Minimum net profit in ETH required to execute a trade |
| `MAX_TRADE_ETH` | Maximum ETH to spend per trade |
| `WATCHED_TOKENS` | Comma-separated ERC-20 addresses to monitor |

> ⚠️ **Never commit your `.env` file or expose your private key.**

### 3. Run

```bash
python -m src.bot
```

The bot will print structured logs to stdout:

```
2024-01-01 12:00:00 [INFO] sniper – 🚀 Liquidity Sniper Bot starting …
2024-01-01 12:00:01 [INFO] sniper – Connected to chain ID 1
2024-01-01 12:00:01 [INFO] sniper – Wallet: 0xYourWallet…
2024-01-01 12:00:01 [INFO] sniper – Monitoring 3 token(s) every 5s. Min profit: 0.0050 ETH.
2024-01-01 12:00:06 [INFO] sniper – Token 0xA0b86991: 1 opportunity(ies), best spread=0.3142%
```

### 4. Run tests

```bash
pytest tests/ -v
```

---

## Configuration Reference

All settings are loaded from environment variables (or a `.env` file).

| Variable | Default | Description |
|---|---|---|
| `RPC_URL` | – | Ethereum JSON-RPC URL |
| `PRIVATE_KEY` | – | Wallet private key (hex with 0x prefix) |
| `MIN_PROFIT_ETH` | `0.005` | Min net profit (ETH) to execute a trade |
| `MAX_TRADE_ETH` | `0.1` | Max ETH spent per trade leg |
| `SLIPPAGE_TOLERANCE` | `0.005` | Slippage fraction (0.005 = 0.5 %) |
| `MAX_GAS_PRICE_GWEI` | `100` | Cap on gas price (Gwei) |
| `POLL_INTERVAL_SECONDS` | `5` | Delay between scan cycles |
| `WATCHED_TOKENS` | WETH, USDC, DAI | Comma-separated token addresses |
| `UNISWAP_V2_FACTORY` | Mainnet default | Uniswap V2 factory address |
| `UNISWAP_V2_ROUTER` | Mainnet default | Uniswap V2 router address |
| `UNISWAP_V3_FACTORY` | Mainnet default | Uniswap V3 factory address |
| `UNISWAP_V3_QUOTER` | Mainnet default | Uniswap V3 quoter address |
| `UNISWAP_V3_ROUTER` | Mainnet default | Uniswap V3 swap router address |
| `WETH_ADDRESS` | Mainnet WETH | Wrapped ETH address |

---

## Disclaimer

This software is provided for educational purposes only. Trading
cryptocurrencies carries significant financial risk. You could lose all
funds in the trading wallet. **Use at your own risk.**
