# PowerTrader AI+ Technical Architecture

**Post Phase 1 & Phase 2 Implementation**

This document describes the modern, modular architecture of PowerTrader AI+ after the comprehensive Phase 1 (Core Architecture & Real Neural Networks) and Phase 2 (Modern Architecture & Scalability) implementation.

## Architecture Overview

PowerTrader AI+ has been transformed from a single 8,102-line monolithic application into a modern, modular, and scalable architecture consisting of 11 specialized components.

### Core Architecture

```
PowerTrader AI+ Modular Architecture
├── Core Orchestration (pt_hub.py)
├── AI/ML Systems
│   ├── Neural Networks (pt_neural_network.py) - Real PyTorch Implementation
│   └── Model Evaluation (pt_model_evaluation.py) - Trading-Specific Metrics
├── Infrastructure Systems  
│   ├── Logging System (pt_logging_system.py) - Structured JSON Logging
│   ├── Caching System (pt_caching_system.py) - Multi-tier TTL Caching
│   ├── Async Patterns (pt_async_patterns.py) - HTTP/File/Task Async Operations
│   ├── Process Manager (pt_process_manager.py) - Subprocess Monitoring
│   └── Settings Manager (pt_settings_manager.py) - Validated Configuration
├── UI/UX Systems
│   ├── Theme Manager (pt_theme_manager.py) - Centralized Styling
│   ├── GUI Components (pt_hub_gui_components.py) - Reusable Widgets
│   └── Chart Components (pt_hub_chart_components.py) - Visualization
└── Individual Trainers (*/neural_trainer.py) - Coin-Specific Training
```

## Phase 1: Core Architecture & Real Neural Networks

### Real Machine Learning Implementation

**CRITICAL TRANSFORMATION**: Replaced completely simulated "neural networks" (using `time.sleep()` with fake accuracy) with real PyTorch implementations.

#### Neural Network Architecture (`pt_neural_network.py`)
- **TradingLSTM**: Long Short-Term Memory networks for sequential market data
- **TradingTransformer**: Modern transformer architecture with attention mechanisms
- **FeatureEngineering**: 20+ technical indicators and market features
- **ModelTrainer**: Complete training pipeline with validation and early stopping

```python
# Real Implementation Example
model = TradingLSTM(input_size=20, hidden_size=64, num_layers=2)
trainer = ModelTrainer(model, feature_eng)
training_result = trainer.train(market_data, epochs=100)
```

#### Model Evaluation Framework (`pt_model_evaluation.py`)
- **Trading-Specific Metrics**: Sharpe ratio, maximum drawdown, win rate
- **TradingBacktest**: Comprehensive backtesting with transaction costs
- **Performance Attribution**: Risk-adjusted performance analysis

### Enhanced Trainer System
All coin-specific trainers (`BTC/neural_trainer.py`, `ETH/neural_trainer.py`, etc.) have been completely rewritten to use real PyTorch training instead of simulation.

## Phase 2: Modern Architecture & Scalability

### Infrastructure Systems

#### Comprehensive Logging (`pt_logging_system.py`)
- **Structured JSON Logging**: Machine-readable logs with metadata
- **Specialized Loggers**: Trade, security, audit, and performance logging
- **Performance Monitoring**: Execution time tracking and method profiling
- **Log Management**: Automatic rotation and size management

```python
# Enhanced Logging Usage
from pt_logging_system import log_trade, log_security
log_trade("BUY order executed", {"symbol": "BTCUSDT", "amount": 0.1})
log_security("API key validation", {"exchange": "binance", "status": "success"})
```

#### Advanced Caching System (`pt_caching_system.py`)
- **Multi-Tier Caching**: Memory and persistent disk storage
- **TTL Management**: Configurable time-to-live with automatic expiration
- **Eviction Policies**: LRU, LFU, and TTL-based strategies
- **Specialized Caches**: Market data, model storage, configuration caching

```python
# Caching System Usage
cache_manager = get_cache_manager()
cache_manager.cache_market_data("BTCUSDT", price_data, ttl_seconds=60)
cached_data = cache_manager.get_market_data("BTCUSDT")
```

#### Async Patterns (`pt_async_patterns.py`)
- **AsyncHTTPClient**: Connection pooling, retries, and rate limiting
- **AsyncFileManager**: Concurrent file I/O operations
- **AsyncTaskQueue**: Background task processing with priority
- **Rate Limiting**: Configurable request throttling for API compliance

```python
# Async Operations Example
async def fetch_market_data():
    http_client = get_http_client()
    result = await http_client.get("https://api.binance.com/api/v3/ticker/24hr")
    return result.data
```

#### Process Management (`pt_process_manager.py`)
- **LogProc**: Subprocess management with live log streaming
- **ProcessManager**: Multi-process coordination and monitoring
- **Statistics Tracking**: CPU, memory, and runtime monitoring
- **Graceful Shutdown**: Proper signal handling and resource cleanup

#### Settings Management (`pt_settings_manager.py`)
- **Validation System**: Automatic validation with error reporting
- **Auto-Recovery**: Invalid settings automatically corrected
- **Nested Configuration**: Dot notation for structured settings access
- **Change Notifications**: Callback system for configuration updates
- **Trading Mode**: `trading.mode` (`paper`|`live`, default `paper`), `trading.active_broker` and `trading.<broker>_testnet` persist in `pt_config.json` (in the user config folder)

#### User Folders and Credentials (`pt_paths.py`, `pt_secrets.py`, `pt_migrate.py`)
- **`pt_paths`** is the only module that knows where files live: config, data, logs and cache resolve to the OS per-user folders through `platformdirs` (`SJackson` / `PowerTraderAI`), or under `POWERTRADER_HOME`. The program folder is read-only at runtime; shipped `*.example.json` templates are copied into the config folder on first run only.
- **`pt_secrets`** is the only module that reads or writes credentials: OS keyring (service `SJackson.PowerTraderAI`, entries `<exchange>:<field>`), environment variables first, no plaintext fallback. The setup windows, `MultiExchangeManager` and the live gate (`ExchangeFactory`) all read through it. Config files never hold a credential: one found in a loaded file is ignored and never written back.
- **`pt_migrate`** moves files left in the program folder by older versions at hub start-up (copies only, never overwrites, report in `migration-report.md`, old files removed only after confirmation).

#### Trading-Mode Gate (`trading_mode.py`)
Every order passes through `resolve_order_target(settings)` before it can reach an exchange:
- **Paper (default / any ambiguity)**: the order goes to `PaperExchange`, an `AbstractExchange` adapter over `PaperTradingAccount`. No credentials, no live venue.
- **Live without an active broker**: refused (`LiveTradingRefused`); nothing is sent anywhere.
- **Live with a broker**: `ExchangeFactory.get_exchange(ExchangeType(active_broker))`.

`pt_trader.py` has no broker-specific REST code; it uses the target's `place_order`, `get_balance`, `get_order_status` and `get_market_data`. The trader is pinned to the mode it started in and refuses orders if `trading.mode`/broker changes underneath it. Each mode keeps its own ledger and history under the hub data directory (`paper/`, `testnet/`, or the base directory for live). The hub shows the active mode in an always-visible header strip, and switching to Live (File > Trading Mode...) requires choosing a broker and ticking "Yes, I understand real money is at risk".

### Signal Path and Strategy Engine (FDS-121)

**How the trader consumed signals before FDS-121 (documented before it was changed).**
`pt_trainer_standalone.py` and the per-coin `pt_trainer.py` copies are mocks (a sleep loop, hard-coded
"accuracy"). `pt_thinker.py` reads the `memories_<tf>.txt` files they produce and writes, per coin folder,
`long_dca_signal.txt`, `short_dca_signal.txt` (integers 0-7) and `low_bound_prices.html`. `pt_trader.py` then:

- opens a trade when `long_dca_signal >= trade_start_level (3)` and `short_dca_signal == 0`;
- DCAs when the loss passes a hard % level (-2.5, -5, -10, -20, -30, -40, -50) **or** the long signal reaches the
  neural level for that stage (4-7 for stages 0-3) while below cost basis;
- sells on its trailing profit margin (start +5% / +2.5% after a DCA, 0.5% trail gap).

Those signals are noise from an untrained mock, so they are **not** a basis for trading.

**The replacement.** `strategy.engine` (setting, default `catalogue`) selects the signal source:

| Setting | Behaviour |
|---|---|
| `strategy.engine = catalogue` | `SignalEngine` fetches the latest *closed* candles (Binance public klines, cached under `<cache folder>/candles/`), runs the active strategy plus overlays through `StrategyRunner`, and the trader enters on `ENTER_LONG` and exits on `EXIT_LONG`. Legacy DCA buys and trailing-PM sells are **off** in this mode. |
| `strategy.engine = legacy_neural` | The old neural-signal logic, unchanged. The hub strip shows `SIGNALS: LEGACY (UNTRAINED)`. |
| anything else, or an unknown `strategy.active_id` | **No orders** are placed and an ERROR is logged (fail closed). |

Other settings: `strategy.active_id` (default `STRAT-000`, a trivial EMA 20/50 cross), `strategy.symbols`
(default `["BTCUSDT"]`), `strategy.timeframe` (default `1h`), `strategy.overlays` (`[{id, params}]`).
Entry size is the trader's existing start allocation; a strategy exit sells only the quantity the trader's own
ledger says it bought (never the user's other holdings), and a holding without a ledger cost basis is never sold.
If the last closed candle is older than 2x the timeframe the engine returns `HOLD` with reason `STALE_CANDLES`.

**One interface everywhere.** `strategies/` holds the `Strategy` interface (`on_bar(candles) -> Signal` on closed
bars only; pure; long-only), indicators (EMA, DEMA, TEMA, Wilder ATR/ADX), a JSON catalogue + registry that fail
loudly when they disagree, and `StrategyRunner`, the single place where a strategy and its overlays are combined.
The backtester (`python -m app.backtest`) and the trader use the same runner and the same lookback window, so a
backtest and a paper run cannot disagree.

**Backtest honesty rules.** Signal on bar *t* close fills at bar *t+1* open; 10 bps fee + 5 bps slippage per fill;
fixed-fraction sizing; nothing opened during warm-up; first 70% of bars in-sample and last 30% out-of-sample,
reported separately; buy-and-hold over the same window and fee model as the benchmark. The random-price example in
`backtesting_engine.py` is labelled `DEMO ONLY - SYNTHETIC DATA`.
**Risk overlays (FDS-129).** `OVL-RATCHET`, `OVL-ATR`, `OVL-PLOCK` and `OVL-COOLDOWN` attach to any strategy via
`strategy.overlays: [{"id": "OVL-ATR", "params": {...}}]` (or `--overlays` in the backtester). `StrategyRunner`
composes them identically in backtest and paper: the effective stop is the **max** of all overlay stops, a stop only
ever moves **up**, an exit fires on any overlay `exit_now`, a close below the effective stop, or the strategy's own
exit (the rule that fired is recorded, e.g. `stop:OVL-ATR`), and an entry needs the strategy **and** every overlay
gate. Everything is evaluated on closed bars and exits fill at the next open. The trader persists open positions and
overlay state (stops, cooldown timers) to `strategy_state.json` next to its ledger, so a restart mid-position keeps its
stop; each cycle prints and logs the effective stop, its owning overlay and each overlay's state, and the hub's
trail-line column shows the stop and its owner with the active overlay ids in the heading.
### UI/UX Enhancement

#### Theme Management (`pt_theme_manager.py`)
- **Centralized Theming**: Single source for all UI colors and styles
- **Widget Factories**: Themed widget creation methods
- **Runtime Updates**: Dynamic theme modifications
- **Consistent Styling**: Unified appearance across all components

#### Component Modularization
- **GUI Components** (`pt_hub_gui_components.py`): Extracted reusable widgets
- **Chart Components** (`pt_hub_chart_components.py`): Specialized visualization components

## Technical Specifications

### Dependencies
```
# Core ML Dependencies
torch>=2.0.0
torchvision>=0.15.0
scikit-learn>=1.3.0
ta>=0.10.2

# Async Dependencies
aiohttp>=3.8.0
aiofiles>=23.1.0
aiodns>=3.0.0

# Existing Dependencies
matplotlib>=3.7.0
pandas>=2.0.0
numpy>=1.24.0
ccxt>=4.0.0
```

### Performance Features
- **Memory Management**: Configurable cache limits and automatic cleanup
- **Concurrent Processing**: Async patterns for I/O-bound operations
- **Resource Monitoring**: Real-time process and memory statistics
- **Optimized Loading**: Lazy initialization of heavy components

### Quality Assurance
- **Comprehensive Testing**: Complete test suite (`test_phase1_phase2_integration.py`)
- **Modular Testing**: Individual component validation
- **Integration Testing**: Cross-module communication verification
- **Error Handling**: Robust exception handling with detailed logging

## Migration from Legacy Architecture

### Before vs After

| Aspect | Legacy | Modern (Phase 1 & 2) |
|--------|--------|----------------------|
| Neural Networks | Mock simulation | Real PyTorch LSTM/Transformer |
| Code Structure | 8,102-line monolith | 11 modular components |
| Logging | Basic print statements | Structured JSON with levels |
| Caching | None | Multi-tier TTL-based |
| Configuration | Basic JSON loading | Validated with auto-recovery |
| Async Support | None | Full async/await patterns |
| Process Management | Basic subprocess | Full monitoring and streaming |
| Testing | Minimal | Comprehensive test suite |
| Maintainability | Low (monolithic) | High (modular) |
| Scalability | Limited | High (async, caching, monitoring) |

### Migration Benefits
1. **Real AI**: Genuine machine learning instead of simulation
2. **Better Performance**: Async patterns and intelligent caching
3. **Enhanced Reliability**: Validated settings, error recovery, and monitoring
4. **Improved Maintainability**: Modular design enables easier updates and testing
5. **Professional Logging**: Structured logs for operational monitoring

## Development Guidelines

### Adding New Features
1. **Follow Modular Design**: Create specialized modules for distinct functionality
2. **Use Provided Infrastructure**: Leverage logging, caching, and async patterns
3. **Test Thoroughly**: Add tests to the comprehensive test suite
4. **Document Changes**: Update relevant documentation

### Performance Optimization
1. **Cache Frequently Used Data**: Use the caching system for market data and configurations
2. **Async for I/O Operations**: Use async patterns for network and file operations
3. **Monitor Resource Usage**: Use process management for resource monitoring
4. **Log Performance**: Use performance logging for optimization insights

### Debugging and Monitoring
1. **Structured Logging**: Use appropriate log levels and include metadata
2. **Process Monitoring**: Monitor subprocess health and performance
3. **Cache Statistics**: Review cache hit/miss ratios for optimization
4. **Error Tracking**: Use comprehensive error logging for troubleshooting

## Future Architecture Considerations

The modular architecture enables future enhancements:
- **Distributed Processing**: Process management supports distributed architectures
- **External Monitoring**: Structured logs enable external monitoring integration
- **Database Backends**: Caching system can be extended with database backends
- **Microservices**: Individual modules can be deployed as separate services
- **API Extensions**: Async patterns facilitate external API integrations

---

**PowerTrader AI+ Technical Architecture** - Modern, scalable, and maintainable trading platform with real machine learning capabilities.