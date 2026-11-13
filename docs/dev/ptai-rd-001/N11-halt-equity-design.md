# N11: the drawdown halt, and money moved in or out of the account

> **Design only. Trading is unchanged.** Nothing here changes the app. The owner's decision O21 (2026-11-13) was to write a design first and to leave trading as it is until a build is approved. A fix loosens a protective limit, so every rule below falls back to the stricter reading when the app cannot tell what happened.

**Prepared:** 2026-11-13, on `docs/n11-halt-design`, cut from `main` at `9fd0ee1` (#288 to #293 merged; #294 to #297 not).
**Defect:** A2 row N11 (`A2-defect-register.md:46`). Its evidence has moved: `app/pt_trader.py:53-55, 1722-1761, 2484-2589, 437-460` on this tree.
**Decisions so far:** O15 held N11; O21 asked for this design (`D-backlog.md` §3; O21 is recorded by the docs PR for #288 to #297, not yet on `main` at `9fd0ee1`). O1 (PR #270) made the halt refuse buys and keep managing what is held.
**Method:** code and documents read only. Nothing was run, and no exchange was called. Line numbers refer to `9fd0ee1`; a bare path is under `app/`. **"Not verified"** marks anything that depends on how an exchange behaves, or on documentation that is not in the repository.

## Summary

- **Today the halt measures the whole exchange account:** US dollars (or USDT where there are none) plus every other coin at its bid, against the highest value seen since the last Reset peak. Anything that moves that value counts as a gain or a loss: withdrawals, deposits, the owner's own coins, funds held for a resting order, and dollars moved into USDC, which is counted nowhere.
- **It fails in both directions.**
  - A withdrawal of 8% or more halts buying. This is the defect as registered, and it fails safe.
  - **A deposit hides a real loss.** The peak only rises, so a deposit made 7% into a drawdown can let the trader lose another 8% before it halts. This half loosens the limit today, and is the more serious.
- **Where it matters:** live trading. Coinbase live trading has not started (phase 0 not run, `docs/dev/RUN-LOG-live-1.md:16`). In paper, money moves only through Settings > Paper Account, which already clears the peak.
- **Recommendation: three PRs, each approved on its own.**
  1. The halt measures every balance, funds on hold included, with USD and the stablecoins at par. This fixes USD to USDC and resting orders, and no trading loss can hide behind it.
  2. A rise in balances that no recorded fill explains is a deposit, and the peak rises in proportion, so the drawdown is unchanged. This part only ever makes the halt stricter.
  3. A fall in dollars or stablecoins alone, with no order of the trader's unsettled, is a withdrawal, treated the same way. Every other unexplained fall stays a loss, and Settings > Risk lists it with **Count as a withdrawal**. This is the one part that loosens the limit, and its worst misread is bounded (§4).
- **Unchanged:** the owner's own coins still count, entry sizes are unchanged, and paper trading is unchanged in practice.
- **Nine decisions for the owner** (§6). §7 lists four things found on the way that are not N11, one of which switches the halt off.

## 1. What the halt measures today

### 1.1 The account value, each pass

The trader takes one snapshot of the account in each pass of `manage_trades()`.

| Step | What happens | Where |
|---|---|---|
| Balances | `get_balance()` of the trading target: in live, the broker's; in paper, the paper book | `pt_trader.py:1728-1761`; `trading_mode.py:1455-1456` |
| Cash | `buying_power` is the `USD` balance, or `USDT` when there is no `USD` entry. Nothing else is cash | `pt_trader.py:55, 1722-1726` |
| Left out | `USD`, `ZUSD`, `USDT`, `USDC` and `BUSD` are never holdings. So `USDC`, `BUSD` and `ZUSD` are in neither cash nor holdings, and nor is `USDT` when `USD` exists | `pt_trader.py:53, 1752-1753, 2541-2542` |
| Holdings | every other asset with a code of 2 to 10 letters and a quantity above 0, whoever bought it. A code with a digit is dropped | `pt_trader.py:1748-1761`; `pt_validation.py:31` |
| Prices | each held asset and each listed coin at `<COIN>-USD`, valued at the **bid**. `USDC-USD` is skipped | `pt_trader.py:2492-2504, 1789-1839, 2548-2558` |
| Value | `total_account_value = buying_power + Σ quantity × bid` | `pt_trader.py:2563` |
| Incomplete | a balance call that fails, or a held asset with no price this pass, makes the snapshot incomplete. The last complete one is used instead, for as long as that lasts | `pt_trader.py:2510-2560, 2571-2589` |
| Stale prices | live uses a cached bid of any age; paper drops one older than `max_quote_age_s` (N9) | `pt_trader.py:1823-1837` |

**Live balances are the available amounts.**
- Coinbase: `available_balance` from every page of `GET /accounts`. Funds on hold are left out (`pt_exchanges.py:2631-2650`; FDS-LIVE-001 §5.2, `docs/dev/specs/FDS-LIVE-001-coinbase-live-trading.md:86`).
- Binance: `free` only (`pt_exchanges.py:1696-1716`).

**When the check runs.** `run()` checks the last complete snapshot at the start of each cycle (`pt_trader.py:3311-3349`, through `_get_account_value`, `1841-1844`). The check before each order (`_risk_check`, `1846-1892`) also raises the peak from it. Before the first complete snapshot, that check uses buying power alone (`1864-1867`).

### 1.2 The peak

- **Kept:** in `risk_state.json`, in the trader's books folder for its mode (paper, or `live/<broker>/`), so paper and each live broker have their own (`pt_trader.py:510, 618-619`; `risk_state.py:6-14`).
- **Raised:** whenever an account value is above it, every cycle and before every order (`update_portfolio_value`, `pt_trader.py:401-408`). It never falls by itself.
- **Restart:** the peak and a halt survive a restart (`pt_trader.py:345-353`). The snapshot does not: after a start, no drawdown is checked until the first complete pass.
- **New day:** nothing resets it. The peak is the highest value since the last reset. (`pt_risk.py`'s daily-loss check is never called: A1, `A1-capability-matrix.md:81`.)
- **Reset:** only by the owner.
  - Settings > Risk > **Reset peak** sets it to the account value the trader last reported (`risk_settings_ui.py:338-364`; `risk_state.py:106-115, 134-146`).
  - Saving Settings > Paper Account clears the paper peak, so the next value becomes the peak (`pt_hub.py:7633-7643`).

### 1.3 The levels

| Level | Setting (`risk` section of `pt_config.json`) | Default | Range | Effect |
|---|---|---|---|---|
| Warning | `drawdown_warning_pct` | 3% | 0.5-50 | a log line |
| Critical | `drawdown_critical_pct` | 5% | 0.5-50 | a log line |
| Emergency stop | `emergency_drawdown_pct` | 8% | 1-50 | the halt |

- **Set in** Settings > Risk (`risk_settings_ui.py:51-80`).
- **Read** before every check (`pt_trader.py:445-448`; `trading_mode.py:355-411`).
- **Defaults and ranges:** `pt_settings_manager.py:32-37`.
- **Drawdown** = (peak − value) ÷ peak (`pt_trader.py:442`).

### 1.4 What a halt does (since PR #270)

- **It latches.** The halt is saved with its reason, time and account value, and kept across restarts. Only **Resume trading** in Settings > Risk clears it, at the trader's next pass (`pt_trader.py:366-394, 462-475`; `risk_state.py:124-154`). A state file that cannot be read counts as a halt (`risk_state.py:76-87`).
- **Buys are refused:** no entry decision, no DCA buy, and every buy is refused at the gate (`pt_trader.py:410-425, 1857-1862, 3002-3003, 3128-3131`). Order Management refuses buys too.
- **Sells go on:** strategy exits, overlay stops and the trailing margin still sell (`pt_trader.py:3297-3309`; `tests/test_emergency_halt.py`).
- **So the costs are uneven.** A false halt costs entries and DCA buys until the owner resumes. A missed halt costs losses beyond the limit.

### 1.5 Paper and live

| | Paper | Live |
|---|---|---|
| Balances | the paper book: `USD` cash and positions (`trading_mode.py:880-886`) | the broker's available balances |
| Stablecoins | none: the book refuses a cash symbol as a position (`trading_mode.py:1141-1143`) | whatever the account holds; only USD (or USDT) counts |
| Funds on hold | none | left out |
| Money in or out | only through Settings > Paper Account, with the trader stopped. Saving clears the paper peak; a halt stays | any deposit, withdrawal or transfer, at any time |
| The owner's coins | a position added in Paper Account gets a ledger cost, so the trader manages it (`trading_mode.py:1220-1269`) | counted in the value. Catalogue mode does not sell them (`pt_trader.py:2797-2800, 2849-2855`) |
| Quotes | the exchanges in Settings, with an age limit | the broker's ticker, cached at any age |

Live preview reads the real balances, so its halt measures the real account.

## 2. How the value moves without a trading loss

- **Trigger:** the change can cause a halt that no trading loss caused.
- **Mask:** the change can hide a real trading loss, so the halt comes later than its level says.

| Event | Measured value | Trigger today? | Mask today? | Notes |
|---|---|---|---|---|
| Withdrawal of USD | falls by the amount | **Yes**: 8% of the peak or more halts at the next check | No | The registered defect |
| Withdrawal of a coin (sent to a wallet) | falls by its bid value | Yes | No | |
| Deposit of USD or a coin | rises by its value | No | **Yes** | See the example below. Once the value passes the old peak, the deposit is part of the peak, so withdrawing it later triggers |
| USD to USDC (also BUSD or ZUSD, and USDT where USD exists) | falls by the amount: USDC is counted nowhere | Yes | No | The move back raises the value, and masks |
| USD to USDT on Binance (no USD there) | no change | No | No | USDT is the cash there |
| The owner's own coins | moves with their prices | Yes: a fall in them alone can halt | Yes: a rise hides the trader's losses | Live. The trader does not sell them in catalogue mode |
| The owner's trades on the exchange's website | falls by the spread and fee | Only as a real cost | No | Real costs, though not the trader's |
| Funds on hold for a resting order | falls by the order's value until it fills or is cancelled | Yes | No (the release raises it back) | Order Management places Coinbase's own limit, stop-limit and OCO orders (`pt_exchanges.py:2443-2444`; Binance `1509-1512`); the owner can too |
| Staking and rewards | a reward raises a coin's balance | Not verified | Yes, by the reward | Whether staked coins stay available, go on hold or leave the account is not verified. If they leave the available balance, staking triggers like a withdrawal |
| A fee in another asset (Binance BNB) | falls by the fee | Only as a real cost | No | Correct today. Coinbase charges in the quote currency (`total_fees`, `pt_exchanges.py:2721`) |
| Dust | valued at the bid like any holding | No | No | Below the exchange minimum it is not a position (`pt_trader.py:2297-2317`), but it is still in the value |
| An airdrop | a new asset: with a USD price it raises the value; without one, the snapshot is incomplete | No | Yes, if priced | Without a price: §2.2 |
| A coin delisted | its ticker stops | No | Not verified | Live keeps the last cached bid within a run. After a restart there is no price, so every snapshot is incomplete (§2.2). If the exchange converts the coin to USD, the value moves by the difference |
| Funds moved between Coinbase portfolios | like a withdrawal or a deposit | Yes | Yes | Whether `GET /accounts` lists only the key's portfolio is not verified |
| Other fiat (GBP, EUR) | counted as a coin, priced at `GBP-USD` | — | — | §2.2 |
| Paper: a Paper Account save | the book changes, and the peak is cleared | No | **Yes**: a drawdown in progress is forgotten | Paper only |

### 2.1 Can a deposit mask a real loss today? Yes

- **Example.**
  1. The peak is $10,000.
  2. Trading losses take the account to $9,300: a 7% drawdown.
  3. The owner deposits $1,000. The value is $10,300, above the peak, so the peak becomes $10,300 and the drawdown reads 0.
- **Effect.** The halt now comes at $9,476 (8% below $10,300), after $824 more of losses: $1,524 in all. Had the deposit been allowed for, it would come after $111 more.
- **A smaller deposit** masks less, but still masks. Any deposit cuts the measured drawdown by about its own size as a share of the peak.
- **A withdrawal cannot mask a loss:** it only lowers the value.

### 2.2 A holding with no USD price switches the check off

This was traced in code and not verified against an exchange. It is fail-open, unlike N11, and §7 lists it as a separate defect.

- **How it happens.**
  - `GBP` or `EUR` cash in a UK or European Coinbase account is not in `CASH_ASSETS`, so the trader treats it as a coin (`pt_trader.py:1748-1761`) and asks for `GBP-USD`.
  - If Coinbase has no such product (not verified), the ticker raises `MarketNotFound` (`pt_exchanges.py:1993-1997`). The price is missing, so **every** snapshot is incomplete (`pt_trader.py:2553-2555`).
  - An airdropped token or a delisted coin with no USD market does the same.
- **Effect after a start with such a holding.** `_get_account_value()` stays `None`, so `run()` never checks the drawdown (`pt_trader.py:3317-3330`), and orders are sized on buying power alone (`1864-1867`).
- **Effect within a run.** The halt measures the last complete snapshot indefinitely. N9 already covers that stale half.

## 3. Options

Each option is judged on six things: what it fixes; what it can get wrong; its fail-closed rule; what Settings would need; paper; and saved settings.

**The ground rule for all of them:** a misread may make the halt stricter, never looser.
- A fall in value that the app cannot explain is a loss, until something shows it is not.
- A missed fill must never look like a withdrawal that cancels a real loss.

### (a) The trader's own equity, from its own records

**The measure.**
- Capital + realised profit (`total_realized_profit_usd` in `pnl_ledger.json`) + the open positions in the ledger, each at min(ledger quantity, balance) × bid, less its cost.
- "Capital" does not exist in the code: the trader sizes entries on the whole account (`pt_trader.py:2275-2295`). It would be a new setting, or a fixed rule such as "the account value at the last Reset peak".

**It fixes** withdrawals, deposits, USD to USDC and the owner's coins, because none of them touch the books.

**It gets wrong everything the books miss, and each miss hides a loss.**
- **N6:** an order not confirmed within 60 s is settled only at the next start (`pt_trader.py:843-933`). Until then a filled buy is a coin the books do not have, so its fall is not measured.
- **N30:** Order Management's fills are not in the ledger.
- **N31:** a failed ledger write is swallowed.
- **N32:** a sell's remainder stays in the ledger.
- **N7:** Binance reports no fee or average price (PR #295, not merged).
- **Legacy trailing sells** sell the whole holding, the owner's coins included (§7). The proceeds are booked against the ledger's cost, as profit that is not the trader's.
- **Capital** is a second number to keep right. If the owner withdraws more than the free cash, the books still count cash that is gone.

**Fail-closed rule.** While any order is unsettled, count the larger of the ledger quantity and the balance for each coin the trader trades. That brings back the balances, which is option (b).

**Settings:** a capital amount (a new option), or a documented rule. **Paper:** the books follow the paper book, and a Paper Account save sets each position's cost (`trading_mode.py:1220-1269`). **Saved settings:** the saved peak is in whole-account terms and cannot be turned into own-equity terms. The first start would need a fresh peak, which forgets a drawdown in progress.

**Not recommended now.** It becomes sound only after N6, N30 and N31 are fixed.

### (b) Flow-adjusted equity: balance changes that no fill explains

**The measure.**
- The account, as today, plus a comparison each pass.
- For every asset, take the change in balance since the last complete snapshot, less what recorded fills explain: the trader's own, and Order Management's `MANUAL` rows (`order_management_execution.py:1505-1541`). What is left is the **unexplained change**.
- Value it at this pass's bids and sum over the assets: that is the flow.
- Prices do not move balances, so a market move never looks like a flow.

**How a flow is applied.**
- When a flow is accepted, the peak is scaled by the same ratio as the account: `peak × value after ÷ value before`.
- The drawdown is then exactly what it was: a deposit cannot hide a loss, and a withdrawal cannot cause one.
- Scaling keeps the percentage. Subtracting the flow from the peak instead would keep the dollar loss, but then a deposit would shrink the drawdown slightly.

**It fixes** withdrawals, deposits, coin transfers, rewards and airdrops, and, with (d), USD to USDC.

**What it can get wrong.**
- **A trade outside the trader** (the owner's own, on the exchange's website) is two legs: dollars out, coin in. Netted at the bid, it is a small fall, its spread and fee, which is a real cost and correctly a loss. If the two legs land in different passes, they look like a withdrawal followed by a deposit.
- **A fill the trader missed** is the same two legs. While an order of the trader's is unsettled (`pending_orders`, or an order intent, `pt_trader.py:692-756`), a one-sided fall may be the first leg of its fill.
- **A fee charged in another asset after its fill** is a fall in one asset that is a real cost.
- **Rounding** between a fill record and the balance shows as a tiny flow.
- **The owner's coins** still count, price moves included.

**Fail-closed rule.**
- **A rise is always a deposit.** As a deposit it keeps the drawdown; as a gain it would cut it. So reading a rise as a deposit can only be stricter.
- **A fall is a loss unless it is shown to be a withdrawal.** "Shown" means the owner confirms it in Settings > Risk, or a fixed rule whose worst misread is bounded (§4, part 3).
- **Settling:** a change is classified only when the balances have been still for 60 s, so both legs of a trade land in one change. Meanwhile buys wait, and the halt is checked without that change. Exits run as usual.
- **Nothing is classified** across an incomplete snapshot, an order of the trader's whose outcome is unknown, or a peak reset.

**Settings:** no new option. Settings > Risk would list the falls no fill explains, each with **Count as a withdrawal**. **Paper:** money moves only through Paper Account, whose save clears the peak and the comparison, so nothing changes. **Saved settings:** new keys in `risk_state.json` only (the last balances, the flows applied). A file without them reads as "nothing to compare", which is today's behaviour.

### (c) The exchange's own transfer and fill history

**The measure:** as (b), but a fall is a withdrawal only when the exchange lists a transfer of that asset and amount in that window.

**Endpoints in the repository.** The Coinbase Advanced Trade calls documented in FDS-LIVE-001 §4 (`docs/dev/specs/FDS-LIVE-001-coinbase-live-trading.md:53-63`):

| Call | Path (under `/api/v3/brokerage`) | What it would give | In the connector? |
|---|---|---|---|
| Accounts | `GET /accounts` | each currency's `available_balance`, and `hold` (the shape the tests record, `tests/test_coinbase_live_connector.py:46-56`) | Yes, `available_balance` only (`pt_exchanges.py:2631-2650`) |
| Fills | `GET /orders/historical/fills` | the account's fills with their commission, so the owner's own trades are explained too | No |
| Get order | `GET /orders/historical/{order_id}` | one order's fill, fee and value | Yes (`pt_exchanges.py:2686-2724`) |
| Key permissions | `GET /key_permissions` | `portfolio_uuid` and `portfolio_type` (`tests/test_coinbase_connection.py:33-39`) | Yes, `portfolio_type` only (`pt_exchanges.py:1954`) |

**No call in the repository lists deposits, withdrawals, conversions, staking rewards or moves between portfolios.** Coinbase's public documentation names some candidates. It is not in the repository and was not read for this design, so all of these are **not verified**:
- **Advanced Trade:** `GET /portfolios`, `GET /portfolios/{portfolio_uuid}` and `POST /portfolios/move_funds`, and convert trades (`POST /convert/quote`, `GET /convert/trade/{trade_id}`), which move USD to USDC.
- **The Coinbase App (v2) API:** `GET /v2/accounts/{account_id}/transactions` lists deposits, withdrawals and sends, with types such as `send`, `fiat_deposit` and `fiat_withdrawal`.

**Two obstacles are recorded in the repository.**
- FDS-LIVE-001 notes that the Coinbase App pages say Ed25519 keys are not supported, and the owner's key is Ed25519 (`FDS-LIVE-001-coinbase-live-trading.md:69`).
- Coinbase phase 0, which checks even the documented calls, has not been run (`docs/dev/RUN-LOG-live-1.md:16`).
- Binance would need its own deposit and withdrawal history calls, which are not in the repository either.

**It fixes** the classification of every transfer the exchange lists, with no rule of thumb. **It can get wrong** a transfer listed late or still pending. It also needs one call per currency account, works within rate limits, needs separate code for each broker, and has nothing to read in paper. **Fail-closed rule:** a fall with no matching listed transfer is a loss; a listed transfer with no matching fall is ignored. **Settings:** none, as it is a fixed rule. The key needs whatever permission the listing needs (not verified). **Paper:** not applicable. **Saved settings:** none.

**Not now.** This is the right way to automate the confirmation, once phase 0 has run and each endpoint has been checked.

### (d) Count USDC and the other stablecoins as cash

**The measure:** every asset in `CASH_ASSETS` (`USD`, `ZUSD`, `USDT`, `USDC`, `BUSD`) counts at par in the halt's measure.

**It fixes** moves between dollars and a stablecoin: they no longer move the value. Coinbase already takes USDC as USD for orders (`pt_exchanges.py:2738-2740`), and the trader already skips its price (`pt_trader.py:1795-1796`).

**What it can get wrong.**
- A stablecoin worth less than $1 (a depeg) is not seen. Today it is not seen either, because USDC is not counted at all.
- Two codes for the same money would be counted twice if a connector reported both. No current connector does: Kraken's balance is not implemented (`pt_exchanges.py:609-610`).

**Fail-closed rule.** On the first pass after the change, scale the saved peak once by new measure ÷ old measure, both taken on the same snapshot, so a drawdown in progress is kept. Without this, an account holding USDC would set a new peak at once and forget its drawdown.

**Settings:** none. Buying power, which entries are sized from, is unchanged: USD, else USDT (`pt_trader.py:55`). **Paper:** there are no stablecoins, so nothing changes. **Saved settings:** the peak is migrated once, as above. An older version that reads the migrated peak may halt sooner, never later.

### (e) Leave it as it is

- **It fixes** nothing.
- **It keeps** the false halts on withdrawals, USD to USDC and resting orders. The owner clears each with Reset peak and Resume trading. Reset peak forgets the drawdown up to then: after a 5% trading loss and a 4% withdrawal, a reset allows another 8%.
- **It keeps** the mask: a deposit can hide a real loss (§2.1). That is the more serious half of N11, and the only half that loosens the limit today.
- **It costs** nothing to build. Since PR #270, a false halt costs entries until Resume, and positions are still managed.

### The options side by side

| | Withdrawal | Deposit hides a loss | USD to USDC | Resting order | The owner's coins | Can a misread loosen the limit? | Size of build |
|---|---|---|---|---|---|---|---|
| (a) own equity | fixed | fixed | fixed | fixed | fixed | **Yes**: any fill the books miss (N6, N30, N31) | large; after N6, N30, N31 |
| (b) flows, fail closed | fixed (confirmed, or by a rule) | fixed | with (d) | with holds counted | not fixed | Only through the withdrawal rule, and bounded (§4) | medium |
| (c) exchange history | fixed (automatic) | fixed | fixed | not fixed | not fixed | No | large; endpoints not verified |
| (d) stablecoins as cash | not fixed | not fixed | fixed | not fixed | not fixed | No (with the migration) | small |
| (e) leave | not fixed | **not fixed** | not fixed | not fixed | not fixed | Yes, today: deposits | none |

## 4. Recommendation

Build (d) and (b), with funds on hold counted, as three PRs, each approved on its own. Keep (c) for later, and (a) until the books are complete.

**Why this order.**
- Since PR #270 a false halt costs entries until Resume, while a missed halt costs real money. So every ambiguity must resolve towards a halt.
- The trader's books have open gaps (N6, N30, N31, N32, and N7 until #295 merges). A measure built from the books alone, (a), would miss exactly the losses those gaps hide.
- Balances are what the exchange actually holds. Comparing them with the recorded fills, (b), keeps the measure on that, and moves the peak only for a change that is understood.
- (c) would confirm withdrawals best, but its endpoints are not in the repository, may sit in another Coinbase API, and are unchecked.
- (d) is small, and removes the USD to USDC case entirely.

### Part 1: the halt's own measure (one PR)

- **Halt equity** is every balance including funds on hold (Coinbase `hold`, Binance `locked`), with `USD`, `ZUSD`, `USDT`, `USDC` and `BUSD` at par, and every other asset at its bid.
- **A new connector method** returns these totals. A connector without it returns `get_balance()`, as today.
- **Who uses it:** the check, the peak, Reset peak and Settings > Risk. `trader_status.json` reports it beside the account value, so the window measures the drawdown on the same figure as the trader.
- **Unchanged:** entry sizing (Start allocation % and Max per coin %, on today's account value), buying power, the Account panel and the levels.
- **Migration:** the saved peak is scaled once, as in option (d).
- **Why first:** it removes two false triggers (stablecoin moves and resting orders), and no trading loss can hide behind it.

### Part 2: a deposit never reduces the drawdown (one PR)

- **The comparison:** each pass, balances are compared with the last complete snapshot, after recorded fills, as in option (b).
- **Settling:** a change waits 60 s. While it waits, buys wait and the halt is checked without it. Exits run as usual.
- **A net rise**, valued at the bids, is a **deposit**. The peak is scaled up with the account, so the drawdown stays where it was.
- **A net fall** is a **loss**, as today, and Settings > Risk lists it.
- **Across restarts:** the last balances are kept in `risk_state.json`, so a deposit made while the trader was stopped is found at its next start. Reset peak and a Paper Account save clear them.
- **Why:** today a deposit can hide a real loss. This part only ever makes the halt stricter.

### Part 3: a withdrawal does not trigger the halt (one PR: the part that loosens)

- **The rule:** a net fall is a **withdrawal** when it is in `USD` and stablecoins only, no other balance changed, and no order of the trader's is unsettled or of unknown outcome. The peak is scaled down with the account, so the drawdown is what it was before the withdrawal. It is logged, and shown in Settings > Risk.
- **Any other fall stays a loss:** a coin sent out, a fall while a trader order is in flight, or a change with two legs. Settings > Risk lists it with its assets and amounts. **Count as a withdrawal** there scales the peak in the same way.
- **A halt already latched** is cleared only by Resume trading, as now (`risk_state.py:16-20`).
- **The worst misread** is a trade on the exchange's website whose two legs arrive more than 60 s apart (whether Coinbase ever shows that is not verified). The dollar leg reads as a withdrawal and the coin leg as a deposit, so that trade's spread and fee go uncounted. The coin's later fall is counted as usual.
- **The trader's own fills cannot be misread this way.** Each order is recorded before it is sent (PR #271), and nothing is classified while one is unsettled.
- **Theft is not a trading loss.** Money taken from the account would read as a withdrawal. The halt is not a control against theft. The control is a key that cannot transfer (`docs/exchanges/coinbase-setup.md:67`); the key check warns when one can (`pt_exchanges.py:1975-1979`).

### What changes, stated plainly

**Live:**
- Moving dollars into or out of USDC (or USDT, BUSD or ZUSD) no longer moves the drawdown. (Part 1)
- A resting order no longer lowers the account value the halt sees. (Part 1)
- After a deposit the drawdown stays where it was, so the halt can come **sooner** after a deposit than it does today. (Part 2)
- When balances change with no fill to explain them, buys wait up to 60 s. Exits do not. (Part 2)
- Withdrawing dollars or stablecoins no longer halts buying, and the drawdown from before is kept. (Part 3)
- Sending coins out still counts as a loss and can halt, until it is confirmed in Settings > Risk. (Part 3)
- The owner's own coins still count, price moves included. Entry sizes are unchanged.

**Paper:** no change in practice. The paper book has no stablecoins and no holds, and money moves only through Settings > Paper Account, which still clears the peak.

**Observation segments:** a build changes `pt_trader.py`, `risk_state.py` and the exchange files. An observation segment freezes these (`strategy_lab/observation.py:107-121`), so merging a build ends a running segment.

## 5. Tests that would prove a build

These would go in a new `tests/test_halt_equity.py`, on synthetic balances and quotes only, with no network:
- the risk adapter with a temporary books folder;
- a fake target, as in `tests/test_emergency_halt.py`;
- recorded Coinbase answers (`tests/helpers_coinbase.py`) for funds on hold.

**The common starting point** (unless a test says otherwise):
- the peak is $10,000;
- the account holds USD $6,000 and 0.04 BTC at a $100,000 bid ($4,000);
- the emergency stop is 8%;
- no order is unsettled.

The **Today** column says what the same steps do on `9fd0ee1`. "Fails today" marks a reproducing test.

| # | Given | When | Assert | Today |
|---|---|---|---|---|
| T1 | The starting point | USD falls to $5,100 (a 9% withdrawal), and stays there 60 s | No halt. Drawdown 0.0% before and after. One $900 withdrawal recorded. Buys waited during the 60 s, then went on | Fails today: halts at 9.0% (A2's reproducing test) |
| T2 | The starting point | BTC's bid falls 22.5%, to $77,500; balances unchanged | Halt at 9.0%. No flow recorded | Same: halts |
| T3 | USD $6,000, 0.04 BTC at $82,500: value $9,300, a 7.0% drawdown | USD rises by $1,000 (a deposit) | After 60 s: drawdown 7.0%, peak $11,075.27. A further $111 fall in BTC's value halts | Fails today: peak $10,300, drawdown 0, no halt after $111 |
| T4a | An order intent for a BTC buy, outcome unknown | USD falls by $900 and stays there | Not a withdrawal: counted as a loss, halts at 9.0%, and is listed in Settings > Risk | Same: halts (pins the fail-closed rule) |
| T4b | No fill recorded | USD −$1,000 and BTC +0.0099 ($990 at the bid) appear together | No flow. The $10 counts as a loss; no halt. When BTC's bid then falls 25%, the halt triggers (12.6%), as it would had the fill been recorded | Same |
| T4c | No fill recorded | USD −$1,000, then BTC +0.0099 twenty seconds later | One change: a $10 loss. No withdrawal and no deposit recorded | n/a (no flows today) |
| T5 | The starting point, with USDC 0 | USD $5,100 and USDC $900 | Halt equity unchanged at $10,000. No flow. No halt | Fails today: halts at 9.0% |
| T6 | The starting point | BTC falls to 0.031 (0.009 BTC sent out), and stays there 60 s | Counted as a loss: halts at 9.0%, listed. After **Count as a withdrawal**: drawdown 0.0%; buying stays halted until Resume trading | Halts. Fails today on Count as a withdrawal (none exists) |
| T7 | Recorded Coinbase accounts: USD available $5,100 with $900 on hold, BTC 0.04 | A pass | Halt equity $10,000. No halt | Fails today: halts at 9.0% |
| T8 | A saved `risk_state.json` with the last balances; the value is $9,300 (7.0%) | The trader starts, and USD is $1,000 higher than saved | The first complete pass shows a 7.0% drawdown | Fails today: drawdown 0 |
| T9 | A saved peak of $10,000 from today's measure; USD $5,300, BTC $4,000 (today's measure $9,300, 7.0%), and USDC $2,000 | The first pass after the build | Peak scaled once to $12,150.54; drawdown 7.0%; the scaling is recorded and not repeated | n/a (no migration today) |
| T10 | Paper mode; a Paper Account save | The trader starts | The peak and the last balances are cleared; nothing is classified. The sessions in `test_emergency_halt.py` give the same orders as before | Same (paper is unchanged) |
| T11 | USD $6,000, BTC $4,000, USDC $2,000 | An entry is sized | The size is what it is today (from $10,000) | Same (sizing is unchanged) |
| T12 | A held asset with no price | A pass | Nothing is classified; the last complete snapshot is used, as today | Same |
| T13 | Settings > Risk with one listed fall | The owner presses Count as a withdrawal | One request is written, and the trader applies it once. The text states facts only (no defect or spec IDs) | n/a |
| T14 | A `risk_state.json` and a `pt_config.json` written by today's version | The trader starts | Both are read; no setting changes meaning; the peak is migrated as in T9 | n/a |

**Arithmetic used above.**
- T3: 10,000 × 10,300 ÷ 9,300 = 11,075.27; a halt at 0.92 × 11,075.27 = 10,189.25, which is $110.75 below $10,300.
- T9: 10,000 × 11,300 ÷ 9,300 = 12,150.54.

## 6. Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| H1 | Build, or leave it as it is (option (e)) | **Build parts 1 and 2.** They fix the half of N11 that loosens the limit today (deposits) and two false triggers, and cannot hide a trading loss |
| H2 | Part 3: recognise a fall in dollars and stablecoins alone as a withdrawal by a fixed rule, or have every fall confirmed by hand in Settings > Risk | **By the rule**, with the guards in §4. Its worst misread is one website trade's spread and fee. Without the rule, Count as a withdrawal still keeps the drawdown right, but every withdrawal halts buying until confirmed and resumed |
| H3 | Which assets count at par | **The existing cash list:** USD, ZUSD, USDT, USDC and BUSD |
| H4 | Count funds on hold | **Yes.** Coinbase's `hold` is in the recorded account shape but is not read today; phase 0 should check it |
| H5 | The owner's own coins | **Keep counting them for now.** Later, either (a) once N6, N30 and N31 are fixed, or a Coinbase portfolio of the trader's own (whether a key's accounts are limited to its portfolio is not verified) |
| H6 | Size entries on halt equity too | **No.** It would change entry sizes, and is a separate decision |
| H7 | How long a change settles | **60 s, fixed and documented**, the same as the trader's wait for an order of unknown outcome (`pt_trader.py:74`). Not a setting |
| H8 | The exchange's transfer history (option (c)) | **Not now.** Revisit after Coinbase phase 0, with each endpoint checked and the Ed25519 question settled |
| H9 | A Paper Account save | **Leave it:** a save clears the paper peak. The alternative is to scale the peak on an edit and clear it only on Reset |

## 7. Found while reading (not N11)

1. **A holding with no USD price switches the halt off** (§2.2). This is fail-open, and is new: N9 covers the stale snapshot, not a check that never runs. A UK account holding GBP on Coinbase would be affected, if Coinbase serves no `GBP-USD` ticker (not verified). It should be registered as its own row.
2. **The legacy engine treats the whole holding as the trader's.** A trailing-margin exit sells `quantity`, the whole exchange balance (`pt_trader.py:2612, 2927-2937`), and a DCA buy is sized from that holding's value (`3014-3015`). Both include the owner's own coins of that asset. Catalogue mode sells only min(holding, ledger) (`2173-2181`). This applies to live trading with the legacy engine only. It is not in the register (N5 covers a repeated catalogue exit).
3. **Settings > Risk's text is out of date since PR #270.** `APPLY_TEXT` says "After an emergency stop the trader has stopped; after Resume trading it trades again when it is next started" (`risk_settings_ui.py:143-149`). The Emergency stop % help says the trader "stops trading, and stays stopped" (`73-74`). The trader now keeps running, refuses buys only, and applies Resume at its next pass, as the Resume dialog already says (`366-405`).
4. **Asset codes with a digit are dropped from the account value** (`pt_validation.py:31`, used at `pt_trader.py:1754-1757`). Such a coin is neither priced nor counted, so its value is invisible to the halt and to sizing. This is low severity.
