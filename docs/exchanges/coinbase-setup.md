# Coinbase Exchange Setup Guide

## Overview
Coinbase is one of the most user-friendly and trusted cryptocurrency exchanges, especially popular in the United States and Europe. Known for strong regulatory compliance and security.

## 🌍 Regional Availability
- **US**: Coinbase Advanced Trade (all US states except Hawaii)
- **EU**: Available in 40+ European countries
- **UK**: Fully licensed and regulated by FCA
- **Global**: 100+ countries supported

## 📋 Prerequisites

### Account Requirements
- Valid government-issued photo ID
- Proof of address document
- Age 18 or older (21 in some US states)
- Supported country residence
- Bank account for fiat deposits

### Trading Prerequisites
- Completed identity verification
- Linked and verified payment method
- Two-factor authentication enabled

## 🚀 Step 1: Create Coinbase Account

### Registration Process
1. **Visit** [coinbase.com](https://coinbase.com)
2. **Click** "Sign up" and enter details
3. **Verify email** through confirmation link
4. **Complete phone verification**
5. **Add personal information** (name, DOB, address)

### Identity Verification
1. **Navigate** to Settings → Identity Verification
2. **Upload photo ID**:
   - Driver's license (preferred)
   - Passport
   - State ID card
3. **Verify address** with utility bill or bank statement
4. **Complete facial recognition** verification
5. **Wait for approval** (usually instant to 24 hours)

### Enable Two-Factor Authentication
1. **Go to** Settings → Security
2. **Enable 2FA** with authenticator app (Google Authenticator, Authy)
3. **Save backup codes** in secure location
4. **Test 2FA** with test login

## 🔑 Step 2: API Key Creation (Coinbase Developer Platform)

Coinbase's Advanced Trade API uses **CDP API keys**. The older Coinbase Pro keys
(key + secret + passphrase) were retired with Coinbase Pro in 2023 and the legacy
HMAC key/secret scheme is not accepted by the current API, so they cannot be used.

1. **Sign in** at the [Coinbase Developer Platform](https://portal.cdp.coinbase.com)
   (2FA required) and open **API Keys → Secret API Keys → Create API key**.
2. Give it a nickname, then expand **API restrictions** and **Advanced Settings**.
3. **Signature algorithm:** leave it on **Ed25519** (Coinbase's default and
   recommendation). **ECDSA**, shown as legacy, also works.
4. Set permissions:
   - ✅ **View**: required. It is enough for *Test Connection*, paper trading and
     **Preview orders only** (see Step 6).
   - ✅ **Trade**: needed to place real orders. Live trading with a key that cannot
     trade is refused.
   - ❌ **Transfer**: leave off. PowerTraderAI+ never moves funds. *Test Connection*
     and the Trading Mode window warn when a key has it.
5. Add your IP address to the **IP allowlist** (recommended).
6. Click **Create API key**, then copy or download the two values. You cannot
   retrieve the private key again.

### What you get
- **Key name**: `organizations/<org-id>/apiKeys/<key-id>`. Some Ed25519 keys show
  just the key ID, a UUID such as `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`; that works
  too.
- **Private key**, depending on the signature algorithm:
  - **Ed25519**: one line of base64, about 88 characters, ending in `==`.
  - **ECDSA**: an EC key in PEM form, several lines:
    ```
    -----BEGIN EC PRIVATE KEY-----
    ...
    -----END EC PRIVATE KEY-----
    ```

Every request is signed with a short-lived (2 minute) JWT built from these two
values: EdDSA for an Ed25519 key, ES256 for an ECDSA key. Source:
[CDP API key authentication](https://docs.cdp.coinbase.com/get-started/authentication/overview).

## 🔐 Step 3: Configure PowerTraderAI+

### GUI Configuration
1. Launch PowerTraderAI+: `python app/pt_hub.py`
2. Go to **Settings** → **Exchange Provider Settings**, set your **Region** and
   **Primary Exchange** to "coinbase".
3. Click **Configure exchange APIs**, open the **Setup Exchange** tab and pick
   **coinbase**.
4. Paste the **Key name** and the **Private key**: for Ed25519 the single line of
   base64; for ECDSA the whole block, including the BEGIN/END lines (pasting it on
   one line or with `\n` escapes also works).
5. Press **Test Connection**, then **Save Configuration**.

Saved credentials go to your operating system's credential store (Windows Credential
Manager, macOS Keychain or the Linux Secret Service) as `coinbase:key_name` and
`coinbase:private_key`. Nothing is written to a file; `trading_config.json` in the
config folder only records that Coinbase is enabled. See
[Where your data lives](../../README.md#where-your-data-lives).

### Environment variables (alternative)
```bash
export POWERTRADER_COINBASE_API_KEY="organizations/<org-id>/apiKeys/<key-id>"
export POWERTRADER_COINBASE_API_SECRET="<the Ed25519 base64 line>"   # or: "$(cat coinbase_private_key.pem)" for ECDSA
```

## 🔧 Step 4: Testing Connection

**Test Connection** makes exactly one read-only request
(`GET /api/v3/brokerage/key_permissions`). It never places, previews or cancels
an order, and what you typed is tested without being saved.

| Result | Meaning |
|---|---|
| ✅ connection successful | Key accepted; shows whether it can view / trade / transfer |
| ❌ credentials not valid | The pasted values are malformed; nothing was sent to Coinbase |
| 🔑❌ authentication failed | Coinbase rejected the key (HTTP 401) |
| 🚫 permission denied | Key accepted but lacks View (HTTP 403 or `can_view: false`) |
| 🌐❌ network error | Could not reach Coinbase (DNS, TLS, timeout) |
| ⚠️ unexpected response | 404 / 429 / 5xx / non-API reply; not a verdict on your key |

Paper mode never contacts Coinbase for orders: it reads public prices only.

## 💰 Step 5: Funding Your Account

### Deposit Methods

#### Bank Transfer (ACH) - US Only
1. **Navigate** to Portfolio → Deposit
2. **Select** "US Dollar" or your local currency
3. **Choose** "Bank transfer (ACH)"
4. **Link bank account** (micro-deposit verification)
5. **Initiate transfer** (1-3 business days)
6. **No fees** for ACH transfers

#### Wire Transfer
1. **Select** "Wire transfer" option
2. **Get wire instructions** from Coinbase
3. **Initiate wire** from your bank
4. **Same day processing** (usually)
5. **$10 fee** for wire transfers

#### Debit Card
1. **Select** "Debit card" option
2. **Enter card details** and verify
3. **Instant deposit** (up to $1,000/day initially)
4. **3.99% fee** for debit card deposits

#### Cryptocurrency Deposits
1. **Select cryptocurrency** to deposit
2. **Copy deposit address**
3. **Send crypto** from external wallet
4. **Wait for confirmations**:
   - Bitcoin: 3 confirmations
   - Ethereum: 35 confirmations
   - Others: varies by coin

## 🟢 Step 6: Live Trading on Coinbase

> **Real money.** No strategy in PowerTraderAI+ has shown that it makes money: every
> out-of-sample backtest so far lost money. Live trading sends the same decisions to
> Coinbase with your funds.

Coinbase has **no test network**: a live order on Coinbase is a real order.

### Switching to live
1. **File → Trading Mode...** and choose **Live trading**.
2. **Broker:** `coinbase`. The list shows only the exchanges this version can place
   orders on.
3. **Preview orders only** is ticked to start with. Leave it ticked for your first run
   (see below).
4. Press **Check API key** to see the saved key's permissions (view, trade, transfer).
5. Tick **Yes, I understand real money is at risk**, press **Apply**, then restart
   the trader.

Apply runs the same key check. It is refused when Coinbase rejects the key, or when
the key cannot trade and **Preview orders only** is not ticked. A key that can
transfer funds is accepted with a warning. The trader runs the check again when it
starts.

### Preview orders only
The trader runs exactly as in live trading: it reads your Coinbase balances, follows
the strategy and decides each order. Each order then goes to Coinbase's **preview**
(`POST /api/v3/brokerage/orders/preview`) instead of being placed. The trader's log
shows what Coinbase would have done, for example:

```
ORDER PREVIEW (BTC-USD buy, ENTRY): would buy 0.00002857 BTC, for $2.00, at about $70,010.20, fee $0.01, total $2.01
```

Nothing is bought or sold, nothing is recorded as a trade, and a preview needs only
the **View** permission, so it works with a view-only key. The same order is
previewed at most once every 15 minutes.

The hub's **Exchange** line shows `COINBASE (preview orders)` in this mode, and
`COINBASE (live orders)` once preview is turned off. In paper mode it names the
primary exchange: `COINBASE (prices)`.

### What PowerTraderAI+ sends to Coinbase
- **Market orders only**, as immediate-or-cancel (`market_market_ioc`). No limit,
  stop or bracket orders.
- **A buy is sized in dollars** (`quote_size`): the coins the trader decided on, times
  the current ask, to the cent. Coinbase's documentation asks for this on a market
  buy. **A sell is sized in coins** (`base_size`), rounded down to Coinbase's
  increment for the product.
- An order below Coinbase's minimum size, or on a product Coinbase has marked trading
  disabled, cancel-only or limit-only, is refused by PowerTraderAI+ and not sent.
- Every order carries the trader's own order id (`client_order_id`). Coinbase answers
  a repeated id with the order it already made, and that order is recorded once.
- An order is never sent twice: after a network error the trader reports the error
  and does not retry it.

### Your books
- Live Coinbase trades are kept in `hub_data/live/coinbase/` in the data folder;
  preview runs use `hub_data/live/coinbase/preview/`.
- Each trade is recorded with Coinbase's own filled quantity, average price and fee.
  The cost and the profit include the fee.
- An immediate-or-cancel order can fill in part. It is recorded at the part that
  filled, and the log says, for example, `partly filled: 0.0001 of 0.0002`.
- After a sell that filled in part, the rest of the coin is still held and still
  managed: its stop, trailing line and DCA stages stay (also after a restart), and
  the next cycle sells the rest.
- A sell is rounded down to Coinbase's step, so a tiny remainder can be left. A
  remainder worth less than Coinbase's smallest order cannot be sold: it is shown,
  left alone, and does not stop a new trade in that coin.
- **USDC** is shown as cash but is not spent: the trader buys with **USD**.
- Live books from an older version, kept in the `hub_data` folder itself, are moved
  once into `hub_data/live/<broker>/`, after a copy is made in
  `hub_data/live_books_backup_<date>/`. If the move cannot finish (for example, a
  file is in use), the trader does not start; the move is finished the next time,
  into the same broker's folder.

### Ed25519 or ECDSA
Both key types work for reading the account. Coinbase's documentation disagrees on
whether Ed25519 keys can place orders. If Coinbase answers an order with
**HTTP 401** and your key is Ed25519, the error says so: create a key with the
**ECDSA** signature algorithm and save it in **Configure exchange APIs**.

## 📊 Trading Features

### Supported Trading Pairs
Major cryptocurrencies available:
- **Bitcoin**: BTC-USD, BTC-EUR
- **Ethereum**: ETH-USD, ETH-EUR
- **Altcoins**: ADA-USD, DOT-USD, LINK-USD, etc.
- **Stablecoins**: USDC-USD (1:1 conversion)

### Order Types
Coinbase offers market, limit, stop-limit and bracket orders. PowerTraderAI+ places
**market (immediate-or-cancel) orders only** (Step 6).

### Fee Structure
**Coinbase Advanced Trade Fees**:
- **Maker**: 0.00% to 0.60% (based on volume)
- **Taker**: 0.05% to 0.60% (based on volume)
- **Volume tiers**: Higher volume = lower fees

**Regular Coinbase** (not recommended for trading):
- **Buy/Sell spread**: ~0.50%
- **Coinbase fee**: 1.49% to 3.99%

## ⚙️ Advanced Configuration

### Symbol Formats
Coinbase uses dash-separated symbols. For prices, PowerTraderAI+ also maps the
compact and USDT forms used elsewhere in the app (`BTCUSDT`, `BTC-USDT`,
`BTC/USDT`, `BTCUSD`) to Coinbase's USD market (`BTC-USD`). A coin Coinbase does
not list (for example BNB) has no price there.
```python
# Coinbase format
"BTC-USD"   # Bitcoin vs US Dollar
"ETH-USD"   # Ethereum vs US Dollar
"ADA-USD"   # Cardano vs US Dollar
"DOT-USD"   # Polkadot vs US Dollar

# These work directly with PowerTraderAI+
symbols = ["BTC-USD", "ETH-USD", "ADA-USD"]
```

### Rate Limits
When Coinbase answers a read (balances, product rules, order status) with
**HTTP 429**, PowerTraderAI+ waits and asks again, up to three times. An order is
never sent again. The trader places at most a few orders an hour.

## 🚨 Troubleshooting

### Common Issues

#### ❌ "authentication failed"
**Causes**:
- Key name and private key are from different API keys
- The key was deleted or the private key was altered when pasting
- Computer clock is wrong (tokens last 2 minutes)
- The key's IP allowlist does not include this machine
- A retired Coinbase Pro key or a key + secret + passphrase set was used

**Solutions**:
1. Re-copy both values from the CDP portal (for ECDSA, include the BEGIN/END lines)
2. Check the system clock is synchronised
3. Check the IP allowlist, or create a new key
4. If an Ed25519 key keeps failing, create one with the ECDSA signature algorithm

#### ❌ "permission denied"
**Causes**:
- The key lacks the View permission
- Portfolio restrictions on the key exclude the default portfolio

**Solutions**:
1. Edit the key in the CDP portal and enable View (and Trade only for live use)
2. Check the portfolio restrictions

#### ❌ "Rate limit exceeded"
**Causes**:
- Too many requests per second
- Multiple applications using same API
- Burst of requests

**Solutions**:
1. Implement request throttling (max 10/sec)
2. Use WebSocket feed for market data
3. Space out API calls
4. Check for other applications using API

#### ❌ "Product not found"
**Causes**:
- Invalid trading pair symbol
- Trading pair not available in your region
- Symbol format incorrect

**Solutions**:
1. Verify symbol format (BTC-USD not BTCUSD)
2. Check available products for your region
3. Use only supported trading pairs
4. Check the Coinbase product list

### Support Resources
- **Coinbase Support**: help.coinbase.com
- **API Documentation**: docs.cloud.coinbase.com
- **Status Page**: status.coinbase.com
- **Community**: reddit.com/r/CoinbaseSupport

## 🔒 Security Best Practices

### API Security
- **IP Restrictions**: Whitelist your IP addresses only
- **Minimal permissions**: Only enable View and Trade
- **Regular monitoring**: Review API activity logs
- **Key rotation**: Change API keys periodically

### Account Security
- **Strong 2FA**: Use app-based TOTP (not SMS)
- **Unique passwords**: Don't reuse passwords
- **Vault storage**: Use Coinbase Vault for long-term storage
- **Device security**: Keep devices secure and updated

### Trading Security
- **Start small**: Test with minimal amounts
- **Monitor closely**: Watch for unexpected activity
- **Withdrawal security**: Set up withdrawal whitelisting
- **Backup access**: Store recovery information safely

## 📈 Performance Optimization

### WebSocket Integration
```python
import asyncio
import json
import websockets

async def coinbase_websocket():
    uri = "wss://ws-feed.exchange.coinbase.com"

    subscribe_msg = {
        "type": "subscribe",
        "product_ids": ["BTC-USD", "ETH-USD"],
        "channels": ["ticker"]
    }

    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps(subscribe_msg))

        async for message in websocket:
            data = json.loads(message)
            if data.get('type') == 'ticker':
                symbol = data['product_id']
                price = float(data['price'])
                print(f"{symbol}: ${price:,.2f}")
```

### Connection Optimization
```python
import aiohttp
import asyncio

class CoinbaseOptimized:
    def __init__(self, key_name, private_key_pem):
        self.key_name = key_name
        self.private_key_pem = private_key_pem
        self.session = None

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=20,
            ttl_dns_cache=300,
            use_dns_cache=True
        )

        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
```

### Fee Optimization
- **Use Advanced Trade**: Much lower fees than regular Coinbase
- **Maker orders**: Use limit orders to pay maker fees
- **Volume tiers**: Increase trading volume for better rates
- **USDC trading**: No fees for USD ↔ USDC conversion

---

**Coinbase Setup Complete!** Your trusted and regulated cryptocurrency exchange integration is ready for PowerTraderAI+.
