"""
Approval gate for paper-trade proposals.

The gate binds a human approval to the exact execution payload that may be
passed to PaperTradingAccount.place_order(...).
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pt_paper_trading import OrderSide, OrderType


class TradeProposalState(Enum):
    """Lifecycle states for a proposed paper trade."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    EXECUTED = "executed"


class TradeApprovalError(Exception):
    """Base error for approval-gate failures."""


class ProposalNotFoundError(TradeApprovalError):
    """Raised when a proposal id does not exist."""


class ProposalStateError(TradeApprovalError):
    """Raised when a proposal is in the wrong state for the requested action."""


class PayloadDigestMismatchError(TradeApprovalError):
    """Raised when approval does not match the execution payload."""


class ProposalExpiredError(TradeApprovalError):
    """Raised when a proposal is expired."""


class RiskCheckFailedError(TradeApprovalError):
    """Raised when risk checks do not approve a proposal."""


@dataclass
class TradeProposalPayload:
    """Execution-relevant fields for a paper-trade proposal."""

    tool_name: str
    account_scope: str
    exchange_scope: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    quote_timestamp: Optional[Any] = None

    def __post_init__(self) -> None:
        self.side = _coerce_order_side(self.side)
        self.order_type = _coerce_order_type(self.order_type)
        self.quantity = _coerce_decimal(self.quantity, "quantity")
        self.price = _coerce_optional_decimal(self.price, "price")
        self.stop_price = _coerce_optional_decimal(self.stop_price, "stop_price")

    def canonical_payload(self) -> Dict[str, Any]:
        """Return only the fields that determine paper-trade execution."""

        return {
            "account_scope": self.account_scope,
            "exchange_scope": self.exchange_scope,
            "order_type": self.order_type,
            "price": self.price,
            "quantity": self.quantity,
            "quote_timestamp": self.quote_timestamp,
            "side": self.side,
            "stop_price": self.stop_price,
            "symbol": self.symbol,
            "tool_name": self.tool_name,
        }

    def place_order_kwargs(self) -> Dict[str, Any]:
        """Build kwargs for PaperTradingAccount.place_order(...)."""

        return {
            "symbol": self.symbol,
            "order_type": self.order_type,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "stop_price": self.stop_price,
        }


@dataclass
class RiskCheckResult:
    """Risk result attached to the exact proposal payload."""

    approved: bool
    warnings: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    risk_score: Decimal = Decimal("0")
    policy_id: str = ""
    policy_version: str = ""

    def __post_init__(self) -> None:
        self.risk_score = _coerce_decimal(self.risk_score, "risk_score")
        self.warnings = list(self.warnings)
        self.violations = list(self.violations)


@dataclass
class TradeProposal:
    """Stored approval-gate proposal."""

    proposal_id: str
    payload: TradeProposalPayload
    payload_digest: str
    risk_result: RiskCheckResult
    state: TradeProposalState
    proposed_at: datetime
    expires_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    executed_order_id: Optional[str] = None


@dataclass
class AuditEntry:
    """Audit entry for proposal lifecycle changes."""

    event_type: str
    proposal_id: str
    actor_id: str
    at: datetime
    payload_digest: str
    details: Dict[str, Any] = field(default_factory=dict)


def compute_payload_digest(payload: TradeProposalPayload) -> str:
    """Compute the approval digest for a paper-trade payload."""

    canonical_payload = _json_ready(payload.canonical_payload())
    encoded = json.dumps(
        canonical_payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class TradeProposalApprovalGate:
    """In-memory approval gate for proposed paper trades."""

    def __init__(self, audit_sink: Optional[Any] = None) -> None:
        self._proposals: Dict[str, TradeProposal] = {}
        self._audit_log: List[AuditEntry] = []
        self._audit_sink = audit_sink
        self._lock = threading.RLock()

    def propose_trade(
        self,
        payload: TradeProposalPayload,
        risk_result: RiskCheckResult,
        expires_at: Optional[datetime] = None,
        proposer_id: str = "agent",
    ) -> TradeProposal:
        proposed_at = _utc_now()
        stored_payload = copy.deepcopy(payload)
        proposal = TradeProposal(
            proposal_id=str(uuid.uuid4()),
            payload=stored_payload,
            payload_digest=compute_payload_digest(stored_payload),
            risk_result=copy.deepcopy(risk_result),
            state=TradeProposalState.PROPOSED,
            proposed_at=proposed_at,
            expires_at=_normalize_optional_utc(expires_at),
        )
        with self._lock:
            self._proposals[proposal.proposal_id] = proposal
            self._record_audit(
                "proposed",
                proposal=proposal,
                actor_id=proposer_id,
                at=proposed_at,
                details={
                    "risk_approved": proposal.risk_result.approved,
                    "risk_policy_id": proposal.risk_result.policy_id,
                    "risk_policy_version": proposal.risk_result.policy_version,
                },
            )
        return proposal

    def approve(
        self, proposal_id: str, approver_id: str, now: Optional[datetime] = None
    ) -> TradeProposal:
        with self._lock:
            proposal = self._get_proposal(proposal_id)
            checked_at = _normalize_utc(now) if now else _utc_now()
            self._mark_expired_if_needed(proposal, checked_at)
            if proposal.state == TradeProposalState.EXPIRED:
                raise ProposalExpiredError(f"Proposal {proposal_id} is expired")
            if proposal.state != TradeProposalState.PROPOSED:
                raise ProposalStateError(
                    f"Proposal {proposal_id} is {proposal.state.value}, not proposed"
                )
            if not proposal.risk_result.approved:
                raise RiskCheckFailedError(
                    f"Proposal {proposal_id} failed risk approval"
                )

            proposal.state = TradeProposalState.APPROVED
            proposal.approved_by = approver_id
            proposal.approved_at = checked_at
            self._record_audit(
                "approved", proposal=proposal, actor_id=approver_id, at=checked_at
            )
            return proposal

    def reject(
        self, proposal_id: str, actor_id: str, reason: Optional[str] = None
    ) -> TradeProposal:
        with self._lock:
            proposal = self._get_proposal(proposal_id)
            if proposal.state != TradeProposalState.PROPOSED:
                raise ProposalStateError(
                    f"Proposal {proposal_id} is {proposal.state.value}, not proposed"
                )

            proposal.state = TradeProposalState.REJECTED
            self._record_audit(
                "rejected",
                proposal=proposal,
                actor_id=actor_id,
                details=_optional_reason(reason),
            )
            return proposal

    def cancel(
        self, proposal_id: str, actor_id: str, reason: Optional[str] = None
    ) -> TradeProposal:
        with self._lock:
            proposal = self._get_proposal(proposal_id)
            if proposal.state not in (
                TradeProposalState.PROPOSED,
                TradeProposalState.APPROVED,
            ):
                raise ProposalStateError(
                    f"Proposal {proposal_id} is {proposal.state.value}, not cancellable"
                )

            proposal.state = TradeProposalState.CANCELLED
            self._record_audit(
                "cancelled",
                proposal=proposal,
                actor_id=actor_id,
                details=_optional_reason(reason),
            )
            return proposal

    def assert_executable(
        self,
        proposal_id: str,
        payload: TradeProposalPayload,
        now: Optional[datetime] = None,
    ) -> TradeProposal:
        with self._lock:
            return self._assert_executable_locked(proposal_id, payload, now)

    def execute_paper_trade(
        self,
        proposal_id: str,
        payload: TradeProposalPayload,
        paper_account: Any,
        circuit_breaker: Optional[Any] = None,
    ) -> str:
        with self._lock:
            proposal = self._assert_executable_locked(proposal_id, payload)

            def place_order() -> str:
                return paper_account.place_order(**payload.place_order_kwargs())

            if circuit_breaker is None:
                order_id = place_order()
            else:
                order_id = circuit_breaker.call(place_order)

            proposal.state = TradeProposalState.EXECUTED
            proposal.executed_order_id = order_id
            self._record_audit(
                "executed",
                proposal=proposal,
                actor_id=proposal.approved_by or "unknown",
                details={"order_id": order_id},
            )
            return order_id

    def get_audit_log(self, proposal_id: Optional[str] = None) -> List[AuditEntry]:
        with self._lock:
            if proposal_id is None:
                return list(self._audit_log)
            return [
                entry for entry in self._audit_log if entry.proposal_id == proposal_id
            ]

    def get_proposal(self, proposal_id: str) -> TradeProposal:
        with self._lock:
            return copy.deepcopy(self._get_proposal(proposal_id))

    def _assert_executable_locked(
        self,
        proposal_id: str,
        payload: TradeProposalPayload,
        now: Optional[datetime] = None,
    ) -> TradeProposal:
        proposal = self._get_proposal(proposal_id)
        checked_at = _normalize_utc(now) if now else _utc_now()
        self._mark_expired_if_needed(proposal, checked_at)
        if proposal.state == TradeProposalState.EXPIRED:
            raise ProposalExpiredError(f"Proposal {proposal_id} is expired")
        if proposal.state != TradeProposalState.APPROVED:
            raise ProposalStateError(
                f"Proposal {proposal_id} is {proposal.state.value}, not approved"
            )
        if not proposal.risk_result.approved:
            raise RiskCheckFailedError(f"Proposal {proposal_id} failed risk approval")

        execution_digest = compute_payload_digest(payload)
        if execution_digest != proposal.payload_digest:
            raise PayloadDigestMismatchError(
                f"Proposal {proposal_id} approval does not match payload digest"
            )
        return proposal

    def _get_proposal(self, proposal_id: str) -> TradeProposal:
        try:
            return self._proposals[proposal_id]
        except KeyError as exc:
            raise ProposalNotFoundError(
                f"Proposal {proposal_id} was not found"
            ) from exc

    def _mark_expired_if_needed(self, proposal: TradeProposal, now: datetime) -> None:
        if proposal.expires_at is None:
            return
        if proposal.state in (
            TradeProposalState.EXPIRED,
            TradeProposalState.REJECTED,
            TradeProposalState.CANCELLED,
            TradeProposalState.EXECUTED,
        ):
            return
        if _normalize_utc(proposal.expires_at) <= _normalize_utc(now):
            proposal.state = TradeProposalState.EXPIRED
            self._record_audit("expired", proposal=proposal, actor_id="system", at=now)

    def _record_audit(
        self,
        event_type: str,
        proposal: TradeProposal,
        actor_id: str,
        at: Optional[datetime] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = AuditEntry(
            event_type=event_type,
            proposal_id=proposal.proposal_id,
            actor_id=actor_id,
            at=_normalize_utc(at) if at else _utc_now(),
            payload_digest=proposal.payload_digest,
            details=details or {},
        )
        self._audit_log.append(entry)
        if self._audit_sink is not None:
            self._write_audit_sink(entry)

    def _write_audit_sink(self, entry: AuditEntry) -> None:
        if callable(self._audit_sink):
            self._audit_sink(entry)
            return
        if hasattr(self._audit_sink, "write"):
            self._audit_sink.write(entry)


class ApprovalGatedPaperTradingAccount:
    """Adapter that makes paper-mode order execution enter the approval gate."""

    def __init__(
        self,
        paper_account: Any,
        gate: Optional[TradeProposalApprovalGate] = None,
        account_scope: Optional[str] = None,
        exchange_scope: str = "paper:simulated",
        circuit_breaker: Optional[Any] = None,
        proposal_ttl_seconds: int = 300,
        risk_policy_id: str = "paper-risk-manager",
        risk_policy_version: str = "1",
    ) -> None:
        self.paper_account = paper_account
        self.gate = gate or TradeProposalApprovalGate()
        self.account_scope = account_scope or f"paper:{paper_account.account_id}"
        self.exchange_scope = exchange_scope
        self.circuit_breaker = circuit_breaker
        self.proposal_ttl_seconds = proposal_ttl_seconds
        self.risk_policy_id = risk_policy_id
        self.risk_policy_version = risk_policy_version

    def propose_order(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        proposer_id: str = "agent",
    ) -> TradeProposal:
        payload = TradeProposalPayload(
            tool_name="paper_trading.place_order",
            account_scope=self.account_scope,
            exchange_scope=self.exchange_scope,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            quote_timestamp=_utc_now().isoformat(),
        )
        risk_result = build_paper_trade_risk_result(
            payload,
            self.paper_account,
            policy_id=self.risk_policy_id,
            policy_version=self.risk_policy_version,
        )
        return self.gate.propose_trade(
            payload,
            risk_result,
            expires_at=_utc_now_delta(self.proposal_ttl_seconds),
            proposer_id=proposer_id,
        )

    def approve_order(self, proposal_id: str, approver_id: str) -> TradeProposal:
        return self.gate.approve(proposal_id, approver_id=approver_id)

    def reject_order(
        self, proposal_id: str, actor_id: str, reason: Optional[str] = None
    ) -> TradeProposal:
        return self.gate.reject(proposal_id, actor_id=actor_id, reason=reason)

    def place_order(self, proposal_id: str) -> str:
        proposal = self.gate.get_proposal(proposal_id)
        return self.gate.execute_paper_trade(
            proposal_id,
            proposal.payload,
            self.paper_account,
            circuit_breaker=self.circuit_breaker,
        )


def build_paper_trade_risk_result(
    payload: TradeProposalPayload,
    paper_account: Any,
    policy_id: str = "paper-risk-manager",
    policy_version: str = "1",
) -> RiskCheckResult:
    reference_price = _reference_price(payload, paper_account)
    approved, reason = paper_account.risk_manager.validate_trade(
        payload.symbol,
        float(payload.quantity),
        float(reference_price),
    )
    return RiskCheckResult(
        approved=approved,
        warnings=[] if approved else [],
        violations=[] if approved else [reason],
        risk_score=Decimal("0") if approved else Decimal("1"),
        policy_id=policy_id,
        policy_version=policy_version,
    )


def _reference_price(payload: TradeProposalPayload, paper_account: Any) -> Decimal:
    if payload.price is not None:
        return payload.price
    return paper_account.market_simulator.get_current_price(payload.symbol)


def _coerce_order_side(side: Any) -> OrderSide:
    if isinstance(side, OrderSide):
        return side
    return OrderSide(str(side))


def _coerce_order_type(order_type: Any) -> OrderType:
    if isinstance(order_type, OrderType):
        return order_type
    return OrderType(str(order_type))


def _coerce_decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field_name} must be decimal-compatible") from exc


def _coerce_optional_decimal(value: Any, field_name: str) -> Optional[Decimal]:
    if value is None:
        return None
    return _coerce_decimal(value, field_name)


def _optional_reason(reason: Optional[str]) -> Dict[str, Any]:
    if reason is None:
        return {}
    return {"reason": reason}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_delta(seconds: int) -> datetime:
    return _utc_now() + timedelta(seconds=seconds)


def _normalize_optional_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return _normalize_utc(value)


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value
