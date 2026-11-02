# RUN-LOG-live-1: Coinbase live trading (FDS-LIVE-001)

## 2026-10-31: phases A, B, C and E built

The owner accepted D1-D10 as recommended ("happy to go and build D1-D10"). Nothing was run against Coinbase: every test uses recorded HTTP (`app/tests/helpers_coinbase.py`), and no request left the machine.

| Phase | Branch | Tests |
|---|---|---|
| A | `feat/live-a-coinbase-connector` | `test_coinbase_live_connector.py`, `test_coinbase_auth.py` |
| B | `feat/live-b-coinbase-orders` | `test_coinbase_live_orders.py`, `test_coinbase_paper_gate.py` |
| C | `feat/live-c-live-path` | `test_coinbase_live_trader.py`, `test_trading_mode.py`, `test_exchange_choice_and_runner.py` |
| E | `feat/live-e-docs` | docs only |

Phase C's acceptance test runs a buy and a sell through the real trader against a fake Coinbase that fills at its own prices and fees. The books in `live/coinbase/` carry Coinbase's quantity, price and fee.

## Phase 0: not run

Phase 0 needs the owner's go-ahead for each run (D9). Its four calls and what each one settles:

1. `GET /accounts?limit=250`, signed without the query: the query-string rule, and an Ed25519 key on a list call.
2. `POST /orders/preview`, a market buy (`quote_size` about $2) and a market sell (`base_size`): an Ed25519 key on a POST.
3. `GET /products/BTC-USD`: the increments and minimums.
4. `GET /transaction_summary`: the owner's fee tier.

**Preview orders only** in the Trading Mode window makes calls 1 to 3 (balances, product rules, previews), so a day of preview mode (phase D, step 1) also answers them.
