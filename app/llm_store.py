"""
What the LLM layer keeps: ``llm_research.db`` (SQLite) in the user data folder.

* ``usage``     every answer: provider, model, tokens, cost (None while the model's
                price is not set), what it was for. The monthly spend caps read it.
* ``prompts``   every version of the analysis, signal and report prompt templates,
                with when it was saved; ``active_prompts`` names the one in use.
* ``analyses``  each Market Analysis answer: the coin, the model's text, the facts
                it was given, and which provider, model and prompt version answered.
* ``signals``   each trade signal (from the LLM Research tab or from the trader at
                an entry), with its outcome and score once known.
* ``decisions`` each confirm or veto the trader's entry hook made, and why.
* ``provider_status`` / ``models`` the last connection test and the last model
                list fetched for each provider.

The hub and the trader both use it (a connection per call, WAL journal, a busy
timeout). Tables and columns are only ever added, so older files stay readable.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

FILE_NAME = "llm_research.db"
SCHEMA_VERSION = 1
PROMPT_KINDS = ("analysis", "signal", "report")

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE IF NOT EXISTS usage (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "ts REAL NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, purpose TEXT, "
    "input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL)",
    "CREATE TABLE IF NOT EXISTS prompts (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "kind TEXT NOT NULL, version INTEGER NOT NULL, template TEXT NOT NULL, "
    "created_at REAL NOT NULL, UNIQUE(kind, version))",
    "CREATE TABLE IF NOT EXISTS active_prompts (kind TEXT PRIMARY KEY, "
    "version INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS analyses (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "ts REAL NOT NULL, coin TEXT NOT NULL, pair TEXT, exchange TEXT, provider TEXT, "
    "model TEXT, prompt_version INTEGER, text TEXT, facts TEXT)",
    "CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "ts REAL NOT NULL, coin TEXT NOT NULL, pair TEXT, exchange TEXT, provider TEXT, "
    "model TEXT, prompt_version INTEGER, direction TEXT, strength TEXT, "
    "confidence REAL, price REAL, price_target REAL, stop_loss REAL, "
    "time_horizon TEXT, reasoning TEXT, source TEXT, trading_mode TEXT, "
    "outcome TEXT, net_return REAL, hit INTEGER, exit_price REAL, scored_at REAL)",
    "CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "ts REAL NOT NULL, coin TEXT NOT NULL, mode TEXT, decision TEXT, reason TEXT, "
    "signal_id INTEGER, trade_ref TEXT, trading_mode TEXT, allowed INTEGER)",
    "CREATE TABLE IF NOT EXISTS provider_status (provider TEXT PRIMARY KEY, "
    "ts REAL, ok INTEGER, message TEXT)",
    "CREATE TABLE IF NOT EXISTS models (provider TEXT PRIMARY KEY, fetched_at REAL, "
    "ids TEXT)",
    "CREATE INDEX IF NOT EXISTS signals_by_key ON signals "
    "(provider, model, prompt_version)",
    "CREATE INDEX IF NOT EXISTS signals_by_coin ON signals (coin, ts)",
    "CREATE INDEX IF NOT EXISTS usage_by_provider ON usage (provider, ts)",
)

SIGNAL_COLUMNS = (
    "id",
    "ts",
    "coin",
    "pair",
    "exchange",
    "provider",
    "model",
    "prompt_version",
    "direction",
    "strength",
    "confidence",
    "price",
    "price_target",
    "stop_loss",
    "time_horizon",
    "reasoning",
    "source",
    "trading_mode",
    "outcome",
    "net_return",
    "hit",
    "exit_price",
    "scored_at",
)


@dataclass
class SignalRecord:
    """One trade signal as the store keeps it."""

    ts: float
    coin: str
    provider: str
    model: str
    prompt_version: int
    direction: Optional[str]  # BUY, SELL, HOLD; None when the answer had none
    strength: str = "neutral"
    confidence: Optional[float] = None
    price: Optional[float] = None  # the price when the signal was made
    price_target: Optional[float] = None
    stop_loss: Optional[float] = None
    time_horizon: str = "MEDIUM"
    reasoning: str = ""
    pair: str = ""
    exchange: str = ""
    source: str = "manual"  # manual | analysis | entry
    trading_mode: str = "paper"
    outcome: Optional[str] = None
    net_return: Optional[float] = None
    hit: Optional[bool] = None
    exit_price: Optional[float] = None
    scored_at: Optional[float] = None
    id: Optional[int] = None

    @property
    def key(self) -> tuple:
        return (self.provider, self.model, self.prompt_version)


@dataclass
class AnalysisRecord:
    ts: float
    coin: str
    provider: str
    model: str
    prompt_version: int
    text: str
    pair: str = ""
    exchange: str = ""
    facts: Dict[str, Any] = field(default_factory=dict)
    id: Optional[int] = None


@dataclass
class PromptVersion:
    kind: str
    version: int
    template: str
    created_at: float
    active: bool = False


def month_start(now: float) -> float:
    """The start of ``now``'s calendar month (UTC), in epoch seconds."""
    d = datetime.fromtimestamp(now, tz=timezone.utc)
    return datetime(d.year, d.month, 1, tzinfo=timezone.utc).timestamp()


class LLMStore:
    """The SQLite file; see the module docstring. ``path`` None: the user data
    folder's ``llm_research.db`` (pt_paths)."""

    def __init__(self, path: Optional[str] = None):
        if path is None:
            import pt_paths

            path = pt_paths.data_file(FILE_NAME)
        self.path = path
        self._lock = threading.Lock()  # one writer of prompt versions at a time
        self._init_lock = threading.Lock()
        self._ready = False

    # ---- the file ----

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        if not self._ready:
            with self._init_lock:
                if not self._ready:
                    try:
                        conn.execute("PRAGMA journal_mode=WAL")
                    except sqlite3.DatabaseError:
                        pass
                    for statement in _SCHEMA:
                        conn.execute(statement)
                    conn.execute(
                        "INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)",
                        ("schema_version", str(SCHEMA_VERSION)),
                    )
                    conn.commit()
                    self._ready = True
        return conn

    def _run(self, sql: str, args: Sequence[Any] = ()) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(sql, tuple(args))
            conn.commit()
            return int(cur.lastrowid or 0)
        finally:
            conn.close()

    def _rows(self, sql: str, args: Sequence[Any] = ()) -> List[sqlite3.Row]:
        conn = self._connect()
        try:
            return list(conn.execute(sql, tuple(args)))
        finally:
            conn.close()

    # ---- usage and spend ----

    def record_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Optional[float],
        purpose: str = "",
        ts: Optional[float] = None,
    ) -> None:
        self._run(
            "INSERT INTO usage (ts, provider, model, purpose, input_tokens, "
            "output_tokens, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                time.time() if ts is None else ts,
                provider,
                model,
                purpose,
                int(input_tokens or 0),
                int(output_tokens or 0),
                cost_usd,
            ),
        )

    def month_spend(self, provider: str, now: Optional[float] = None) -> float:
        """Dollars spent with ``provider`` this calendar month (UTC), counting the
        answers whose cost is known."""
        now = time.time() if now is None else now
        (row,) = self._rows(
            "SELECT COALESCE(SUM(cost_usd), 0) AS spent FROM usage "
            "WHERE provider = ? AND ts >= ? AND cost_usd IS NOT NULL",
            (provider, month_start(now)),
        )
        return float(row["spent"] or 0.0)

    def average_tokens(
        self, provider: str, model: str, purpose: str, last: int = 20
    ) -> Optional[Dict[str, float]]:
        """The mean input and output tokens of the last ``last`` answers of this
        model for ``purpose``, or None when there are none yet."""
        rows = self._rows(
            "SELECT input_tokens, output_tokens FROM usage WHERE provider = ? AND "
            "model = ? AND purpose = ? ORDER BY ts DESC LIMIT ?",
            (provider, model, purpose, int(last)),
        )
        if not rows:
            return None
        return {
            "input": sum(r["input_tokens"] or 0 for r in rows) / len(rows),
            "output": sum(r["output_tokens"] or 0 for r in rows) / len(rows),
        }

    # ---- provider status and model lists ----

    def set_status(self, provider: str, ok: bool, message: str, ts=None) -> None:
        self._run(
            "INSERT OR REPLACE INTO provider_status (provider, ts, ok, message) "
            "VALUES (?, ?, ?, ?)",
            (provider, time.time() if ts is None else ts, int(bool(ok)), message),
        )

    def status(self, provider: str) -> Optional[Dict[str, Any]]:
        rows = self._rows(
            "SELECT ts, ok, message FROM provider_status WHERE provider = ?",
            (provider,),
        )
        if not rows:
            return None
        r = rows[0]
        return {"ts": r["ts"], "ok": bool(r["ok"]), "message": r["message"] or ""}

    def save_models(self, provider: str, ids: Sequence[str], ts=None) -> None:
        self._run(
            "INSERT OR REPLACE INTO models (provider, fetched_at, ids) VALUES (?, ?, ?)",
            (provider, time.time() if ts is None else ts, json.dumps(list(ids))),
        )

    def models(self, provider: str) -> Optional[Dict[str, Any]]:
        """``{"fetched_at", "ids"}``: the model list last fetched, or None."""
        rows = self._rows(
            "SELECT fetched_at, ids FROM models WHERE provider = ?", (provider,)
        )
        if not rows:
            return None
        try:
            ids = [str(i) for i in json.loads(rows[0]["ids"] or "[]")]
        except ValueError:
            ids = []
        return {"fetched_at": rows[0]["fetched_at"], "ids": ids}

    # ---- prompt versions ----

    def prompt_versions(self, kind: str) -> List[PromptVersion]:
        """Every saved version of ``kind``'s prompt, oldest first."""
        active = self.active_version(kind)
        return [
            PromptVersion(
                kind,
                int(r["version"]),
                r["template"],
                float(r["created_at"]),
                int(r["version"]) == active,
            )
            for r in self._rows(
                "SELECT version, template, created_at FROM prompts WHERE kind = ? "
                "ORDER BY version",
                (kind,),
            )
        ]

    def active_version(self, kind: str) -> Optional[int]:
        rows = self._rows("SELECT version FROM active_prompts WHERE kind = ?", (kind,))
        return int(rows[0]["version"]) if rows else None

    def ensure_prompt(self, kind: str, default_template: str) -> PromptVersion:
        """The active version of ``kind``'s prompt; with none saved yet, the
        default template is saved as version 1."""
        if kind not in PROMPT_KINDS:
            raise ValueError(f"unknown prompt kind {kind!r}")
        with self._lock:
            current = self.active_prompt(kind)
            if current is not None:
                return current
            versions = self.prompt_versions(kind)
            if versions:  # versions but no active one: the newest
                self._run(
                    "INSERT OR REPLACE INTO active_prompts (kind, version) "
                    "VALUES (?, ?)",
                    (kind, versions[-1].version),
                )
            else:
                self._save_version(kind, default_template, 1)
        return self.active_prompt(kind)

    def _save_version(self, kind: str, template: str, version: int, ts=None) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO prompts (kind, version, template, created_at) "
                "VALUES (?, ?, ?, ?)",
                (kind, version, template, time.time() if ts is None else ts),
            )
            conn.execute(
                "INSERT OR REPLACE INTO active_prompts (kind, version) VALUES (?, ?)",
                (kind, version),
            )
            conn.commit()
        finally:
            conn.close()

    def active_prompt(self, kind: str) -> Optional[PromptVersion]:
        version = self.active_version(kind)
        if version is None:
            return None
        for v in self.prompt_versions(kind):
            if v.version == version:
                return v
        return None

    def save_prompt(self, kind: str, template: str, ts=None) -> PromptVersion:
        """Save an edited template as a new version (the next number, with its
        time) and make it the one in use."""
        if kind not in PROMPT_KINDS:
            raise ValueError(f"unknown prompt kind {kind!r}")
        if not str(template).strip():
            raise ValueError("a prompt template cannot be empty")
        with self._lock:
            rows = self._rows(
                "SELECT COALESCE(MAX(version), 0) AS v FROM prompts WHERE kind = ?",
                (kind,),
            )
            version = int(rows[0]["v"]) + 1
            self._save_version(kind, str(template), version, ts)
        return self.active_prompt(kind)

    def restore_prompt(self, kind: str, version: int) -> PromptVersion:
        """Use an earlier version again (it keeps its number, and with it the
        signals and scores recorded with it)."""
        if not any(v.version == int(version) for v in self.prompt_versions(kind)):
            raise ValueError(f"{kind} prompt version {version} does not exist")
        self._run(
            "INSERT OR REPLACE INTO active_prompts (kind, version) VALUES (?, ?)",
            (kind, int(version)),
        )
        return self.active_prompt(kind)

    # ---- analyses ----

    def add_analysis(self, record: AnalysisRecord) -> AnalysisRecord:
        record.id = self._run(
            "INSERT INTO analyses (ts, coin, pair, exchange, provider, model, "
            "prompt_version, text, facts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.ts,
                record.coin,
                record.pair,
                record.exchange,
                record.provider,
                record.model,
                record.prompt_version,
                record.text,
                json.dumps(record.facts, default=str),
            ),
        )
        return record

    def latest_analyses(
        self, coins: Optional[Iterable[str]] = None
    ) -> Dict[str, AnalysisRecord]:
        """Each coin's newest analysis (only ``coins`` when given)."""
        rows = self._rows(
            "SELECT a.* FROM analyses a JOIN (SELECT coin, MAX(id) AS id FROM analyses "
            "GROUP BY coin) b ON a.id = b.id"
        )
        wanted = None if coins is None else {str(c).upper() for c in coins}
        out = {}
        for r in rows:
            if wanted is not None and r["coin"] not in wanted:
                continue
            try:
                facts = json.loads(r["facts"] or "{}")
            except ValueError:
                facts = {}
            out[r["coin"]] = AnalysisRecord(
                ts=float(r["ts"]),
                coin=r["coin"],
                provider=r["provider"] or "",
                model=r["model"] or "",
                prompt_version=int(r["prompt_version"] or 0),
                text=r["text"] or "",
                pair=r["pair"] or "",
                exchange=r["exchange"] or "",
                facts=facts if isinstance(facts, dict) else {},
                id=int(r["id"]),
            )
        return out

    # ---- signals ----

    def add_signal(self, s: SignalRecord) -> SignalRecord:
        values = [getattr(s, c) for c in SIGNAL_COLUMNS[1:]]
        values[SIGNAL_COLUMNS.index("hit") - 1] = None if s.hit is None else int(s.hit)
        s.id = self._run(
            f"INSERT INTO signals ({', '.join(SIGNAL_COLUMNS[1:])}) VALUES "
            f"({', '.join('?' for _ in SIGNAL_COLUMNS[1:])})",
            values,
        )
        return s

    @staticmethod
    def _signal(r: sqlite3.Row) -> SignalRecord:
        values = {c: r[c] for c in SIGNAL_COLUMNS if c in r.keys()}
        values["hit"] = None if values.get("hit") is None else bool(values["hit"])
        values["prompt_version"] = int(values.get("prompt_version") or 0)
        for text in ("provider", "model", "pair", "exchange", "reasoning"):
            values[text] = values.get(text) or ""
        values["strength"] = values.get("strength") or "neutral"
        values["time_horizon"] = values.get("time_horizon") or "MEDIUM"
        values["source"] = values.get("source") or "manual"
        values["trading_mode"] = values.get("trading_mode") or "paper"
        return SignalRecord(**values)

    def signals(
        self, limit: Optional[int] = None, coin: Optional[str] = None
    ) -> List[SignalRecord]:
        """Signals, newest first."""
        sql, args = "SELECT * FROM signals", []
        if coin:
            sql += " WHERE coin = ?"
            args.append(str(coin).upper())
        sql += " ORDER BY ts DESC, id DESC"
        if limit:
            sql += " LIMIT ?"
            args.append(int(limit))
        return [self._signal(r) for r in self._rows(sql, args)]

    def latest_signal(self, coin: str) -> Optional[SignalRecord]:
        found = self.signals(limit=1, coin=coin)
        return found[0] if found else None

    def unscored_signals(self) -> List[SignalRecord]:
        return [
            self._signal(r)
            for r in self._rows(
                "SELECT * FROM signals WHERE scored_at IS NULL AND direction IS NOT "
                "NULL ORDER BY ts"
            )
        ]

    def set_outcome(
        self,
        signal_id: int,
        outcome: str,
        net_return: Optional[float],
        hit: Optional[bool],
        exit_price: Optional[float],
        ts=None,
    ) -> None:
        self._run(
            "UPDATE signals SET outcome = ?, net_return = ?, hit = ?, exit_price = ?, "
            "scored_at = ? WHERE id = ?",
            (
                outcome,
                net_return,
                None if hit is None else int(hit),
                exit_price,
                time.time() if ts is None else ts,
                int(signal_id),
            ),
        )

    def scored(
        self, provider: str, model: str, prompt_version: int, trading_mode: str
    ) -> List[SignalRecord]:
        """The scored signals with a direction (a hit or a miss) of one
        provider/model/prompt version, made in ``trading_mode``."""
        return [
            self._signal(r)
            for r in self._rows(
                "SELECT * FROM signals WHERE provider = ? AND model = ? AND "
                "prompt_version = ? AND trading_mode = ? AND hit IS NOT NULL",
                (provider, model, int(prompt_version), trading_mode),
            )
        ]

    def keys(self) -> List[tuple]:
        """Every (provider, model, prompt version) with a signal."""
        return [
            (r["provider"] or "", r["model"] or "", int(r["prompt_version"] or 0))
            for r in self._rows(
                "SELECT DISTINCT provider, model, prompt_version FROM signals "
                "ORDER BY provider, model, prompt_version"
            )
        ]

    # ---- decisions ----

    def add_decision(
        self,
        coin: str,
        mode: str,
        decision: str,
        reason: str,
        allowed: bool,
        signal_id: Optional[int] = None,
        trade_ref: str = "",
        trading_mode: str = "paper",
        ts=None,
    ) -> int:
        return self._run(
            "INSERT INTO decisions (ts, coin, mode, decision, reason, signal_id, "
            "trade_ref, trading_mode, allowed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                time.time() if ts is None else ts,
                coin,
                mode,
                decision,
                reason,
                signal_id,
                trade_ref,
                trading_mode,
                int(bool(allowed)),
            ),
        )

    def decisions(self, limit: int = 200) -> List[Dict[str, Any]]:
        return [
            dict(r)
            for r in self._rows(
                "SELECT * FROM decisions ORDER BY ts DESC, id DESC LIMIT ?",
                (int(limit),),
            )
        ]
