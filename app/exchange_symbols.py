"""
Coins, and their symbols in the connected exchange's own format: one place for
every tab, so none writes a symbol or a symbol format of its own.

* ``market_pair(coin)`` - the coin's market on the connected exchange: the primary
  exchange first, then the others in Settings order (``pt_multi_exchange.
  market_exchanges``, public market data, no credentials), in that exchange's own
  format (``BTC-USD`` on Coinbase, ``BTCUSDT`` on Binance). With no exchange
  connected, the exchange layer's common form (``dollar_symbol``: ``BTC-USD``).
* ``coin_of(text)`` - the coin in a symbol as a user or a file may write it
  (``btc``, ``BTC-USD``, ``BTCUSDT``, ``BTC/USDC``).
* ``parse_symbols(text, known)`` - the coins in a comma list, each symbol read back
  through the pairs ``market_pairs`` gave (``known``) before ``coin_of``.
* ``settings_coins()`` - the coins in Settings (the hub's coin list).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional


@dataclass(frozen=True)
class MarketPair:
    coin: str  # "BTC"
    pair: str  # the exchange's market: "BTC-USD", "BTCUSDT", ...
    exchange: str  # its id ("coinbase"), "" when no exchange is connected
    quote: str  # the quote currency in the pair ("USD", "USDT", ...)


def coin_of(symbol: Any) -> str:
    """``BTC`` from ``btc``, ``BTC-USD``, ``BTCUSDT``, ``BTC/USDC`` ..."""
    from pt_exchange_abstraction import dollar_symbol

    text = str(symbol or "").strip()
    if not text:
        return ""
    return dollar_symbol(text).split("-", 1)[0]


def _quote(coin: str, pair: str) -> str:
    text = str(pair or "").upper()
    if text.startswith(coin.upper()):
        rest = text[len(coin) :].strip("-/_ ")
        if rest:
            return rest
    for sep in ("-", "/", "_"):
        if sep in text:
            return text.split(sep, 1)[1]
    return "USD"


def _layer():
    from pt_multi_exchange import market_exchanges

    return market_exchanges()


def market_pairs(
    coins: Iterable[str], layer: Optional[Callable[[], Any]] = None
) -> List[MarketPair]:
    """Each coin's market on the connected exchange (see the module docstring)."""
    from pt_exchange_abstraction import ExchangeType, dollar_symbol

    connector, exchange = None, ""
    try:
        manager = (layer or _layer)()
        names = manager.exchange_manager.exchange_names()
        if names:
            exchange = names[0]
            connector = manager.exchange_manager.exchanges[ExchangeType(exchange)]
    except Exception:
        connector, exchange = None, ""
    out = []
    for raw in coins:
        coin = coin_of(raw)
        if not coin:
            continue
        common = dollar_symbol(coin)
        pair = common
        if connector is not None:
            try:
                pair = str(connector.market_symbol(common)) or common
            except Exception:
                pair = common
        out.append(MarketPair(coin, pair, exchange, _quote(coin, pair)))
    return out


def market_pair(coin: str, layer: Optional[Callable[[], Any]] = None) -> MarketPair:
    pairs = market_pairs([coin], layer)
    if pairs:
        return pairs[0]
    return MarketPair("", "", "", "USD")


def parse_symbols(text: str, known: Optional[Mapping[str, str]] = None) -> List[str]:
    """The coins in a comma (or space) list, in order, each once. ``known`` maps a
    pair the app showed (any case) to its coin, so an exchange's own name for a
    coin reads back as the coin it was shown for."""
    lookup: Dict[str, str] = {str(k).upper(): v for k, v in (known or {}).items()}
    out: List[str] = []
    for token in str(text or "").replace(",", " ").split():
        coin = lookup.get(token.upper()) or coin_of(token)
        if coin and coin not in out:
            out.append(coin)
    return out


def settings_coins() -> List[str]:
    """The coins in Settings (gui_settings.json), or the default coins."""
    from exchange_check import settings_coins as coins

    return coins()
