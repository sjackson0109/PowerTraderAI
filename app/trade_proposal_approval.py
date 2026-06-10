"""
Approval gate for paper-trade proposals.

The gate binds a human approval to the exact execution payload that may be
passed to PaperTradingAccount.place_order(...).
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
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

    def __init__(self) -> None:
        self._proposals: Dict[str, TradeProposal] = {}
        self._audit_log: List[AuditEntry] = []

    def propose_trade(
        self,
        payload: TradeProposalPayload,
        risk_result: RiskCheckResult,
        expires_at: Optional[datetime] = None,
        proposer_id: str = "agent",
    ) -> TradeProposal:
        proposed_at = datetime.now()
        stored_payload = copy.deepcopy(payload)
        proposal = TradeProposal(
            proposal_id=str(uuid.uuid4()),
            payload=stored_payload,
            payload_digest=compute_payload_digest(stored_payload),
            risk_result=copy.deepcopy(risk_result),
            state=TradeProposalState.PROPOSED,
            proposed_at=proposed_at,
            expires_at=expires_at,
        )
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
        proposal = self._get_proposal(proposal_id)
        checked_at = now or datetime.now()
        self._mark_expired_if_needed(proposal, checked_at)
        if proposal.state == TradeProposalState.EXPIRED:
            raise ProposalExpiredError(f"Proposal {proposal_id} is expired")
        if proposal.state != TradeProposalState.PROPOSED:
            raise ProposalStateError(
                f"Proposal {proposal_id} is {proposal.state.value}, not proposed"
            )
        if not proposal.risk_result.approved:
            raise RiskCheckFailedError(f"Proposal {proposal_id} failed risk approval")

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
        proposal = self._get_proposal(proposal_id)
        checked_at = now or datetime.now()
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

    def execute_paper_trade(
        self,
        proposal_id: str,
        payload: TradeProposalPayload,
        paper_account: Any,
    ) -> str:
        proposal = self.assert_executable(proposal_id, payload)
        order_id = paper_account.place_order(**payload.place_order_kwargs())
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
        if proposal_id is None:
            return list(self._audit_log)
        return [entry for entry in self._audit_log if entry.proposal_id == proposal_id]

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
        if proposal.expires_at <= now:
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
        self._audit_log.append(
            AuditEntry(
                event_type=event_type,
                proposal_id=proposal.proposal_id,
                actor_id=actor_id,
                at=at or datetime.now(),
                payload_digest=proposal.payload_digest,
                details=details or {},
            )
        )


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
