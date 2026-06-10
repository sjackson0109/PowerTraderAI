from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

from pt_paper_trading import OrderSide, OrderStatus, OrderType, PaperTradingAccount
from trade_proposal_approval import (
    PayloadDigestMismatchError,
    ProposalExpiredError,
    ProposalNotFoundError,
    ProposalStateError,
    RiskCheckFailedError,
    RiskCheckResult,
    TradeProposalApprovalGate,
    TradeProposalPayload,
    TradeProposalState,
    compute_payload_digest,
)


class SpyPaperAccount:
    def __init__(self):
        self.calls = []
        self.next_order_id = "paper-order-1"

    def place_order(self, **kwargs):
        self.calls.append(kwargs)
        return self.next_order_id


def make_payload(**overrides):
    fields = {
        "tool_name": "agentic_trade",
        "account_scope": "paper:default",
        "exchange_scope": "paper:simulated",
        "symbol": "BTC",
        "side": OrderSide.BUY,
        "order_type": OrderType.MARKET,
        "quantity": Decimal("0.001"),
        "price": None,
        "stop_price": None,
        "quote_timestamp": "2026-06-10T00:00:00Z",
    }
    fields.update(overrides)
    return TradeProposalPayload(**fields)


def passing_risk(**overrides):
    fields = {
        "approved": True,
        "warnings": ["paper-mode only"],
        "violations": [],
        "risk_score": Decimal("0.10"),
        "policy_id": "paper-tier-3",
        "policy_version": "1",
    }
    fields.update(overrides)
    return RiskCheckResult(**fields)


class TestTradeProposalApprovalGate(unittest.TestCase):
    def setUp(self):
        self.gate = TradeProposalApprovalGate()
        self.payload = make_payload()
        self.risk = passing_risk()

    def test_propose_trade_records_digest_risk_and_audit(self):
        proposal = self.gate.propose_trade(
            self.payload, self.risk, proposer_id="agent-1"
        )

        self.assertEqual(proposal.state, TradeProposalState.PROPOSED)
        self.assertEqual(proposal.payload_digest, compute_payload_digest(self.payload))
        self.assertTrue(proposal.risk_result.approved)
        self.assertEqual(proposal.risk_result.policy_id, "paper-tier-3")

        audit = self.gate.get_audit_log(proposal.proposal_id)
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0].event_type, "proposed")
        self.assertEqual(audit[0].actor_id, "agent-1")
        self.assertEqual(audit[0].payload_digest, proposal.payload_digest)

    def test_digest_is_stable_for_same_execution_payload(self):
        same_payload = make_payload(
            quantity=Decimal("0.0010"),
            side="buy",
            order_type="market",
        )

        self.assertEqual(
            compute_payload_digest(self.payload),
            compute_payload_digest(same_payload),
        )

    def test_approve_binds_to_original_digest(self):
        proposal = self.gate.propose_trade(self.payload, self.risk)

        approved = self.gate.approve(proposal.proposal_id, approver_id="human-1")
        executable = self.gate.assert_executable(proposal.proposal_id, self.payload)

        self.assertEqual(approved.state, TradeProposalState.APPROVED)
        self.assertEqual(executable.payload_digest, proposal.payload_digest)
        self.assertEqual(approved.approved_by, "human-1")
        audit_events = [
            entry.event_type for entry in self.gate.get_audit_log(proposal.proposal_id)
        ]
        self.assertEqual(audit_events, ["proposed", "approved"])

    def test_unapproved_paper_trade_does_not_call_place_order(self):
        proposal = self.gate.propose_trade(self.payload, self.risk)
        account = SpyPaperAccount()

        with self.assertRaises(ProposalStateError):
            self.gate.execute_paper_trade(proposal.proposal_id, self.payload, account)

        self.assertEqual(account.calls, [])

    def test_approved_paper_trade_calls_place_order_once(self):
        proposal = self.gate.propose_trade(self.payload, self.risk)
        self.gate.approve(proposal.proposal_id, approver_id="human-1")
        account = SpyPaperAccount()

        order_id = self.gate.execute_paper_trade(
            proposal.proposal_id, self.payload, account
        )

        self.assertEqual(order_id, "paper-order-1")
        self.assertEqual(len(account.calls), 1)
        self.assertEqual(account.calls[0]["symbol"], "BTC")
        self.assertEqual(account.calls[0]["side"], OrderSide.BUY)
        self.assertEqual(account.calls[0]["quantity"], Decimal("0.001"))
        self.assertEqual(proposal.state, TradeProposalState.EXECUTED)
        self.assertEqual(proposal.executed_order_id, "paper-order-1")

    def test_changed_symbol_requires_new_approval(self):
        self._assert_changed_payload_blocked(symbol="ETH")

    def test_changed_side_requires_new_approval(self):
        self._assert_changed_payload_blocked(side=OrderSide.SELL)

    def test_changed_quantity_requires_new_approval(self):
        self._assert_changed_payload_blocked(quantity=Decimal("0.002"))

    def test_changed_order_type_requires_new_approval(self):
        self._assert_changed_payload_blocked(order_type=OrderType.LIMIT)

    def test_changed_price_requires_new_approval(self):
        self._assert_changed_payload_blocked(price=Decimal("42000"))

    def test_changed_stop_price_requires_new_approval(self):
        self._assert_changed_payload_blocked(stop_price=Decimal("39000"))

    def test_rejected_proposal_cannot_execute(self):
        proposal = self.gate.propose_trade(self.payload, self.risk)
        self.gate.reject(proposal.proposal_id, actor_id="human-1")
        account = SpyPaperAccount()

        with self.assertRaises(ProposalStateError):
            self.gate.execute_paper_trade(proposal.proposal_id, self.payload, account)

        self.assertEqual(account.calls, [])
        self.assertEqual(proposal.state, TradeProposalState.REJECTED)

    def test_cancelled_proposal_cannot_execute(self):
        proposal = self.gate.propose_trade(self.payload, self.risk)
        self.gate.approve(proposal.proposal_id, approver_id="human-1")
        self.gate.cancel(proposal.proposal_id, actor_id="human-1")
        account = SpyPaperAccount()

        with self.assertRaises(ProposalStateError):
            self.gate.execute_paper_trade(proposal.proposal_id, self.payload, account)

        self.assertEqual(account.calls, [])
        self.assertEqual(proposal.state, TradeProposalState.CANCELLED)

    def test_expired_proposal_cannot_execute(self):
        expires_at = datetime.now() - timedelta(seconds=1)
        proposal = self.gate.propose_trade(
            self.payload, self.risk, expires_at=expires_at
        )
        account = SpyPaperAccount()

        with self.assertRaises(ProposalExpiredError):
            self.gate.execute_paper_trade(proposal.proposal_id, self.payload, account)

        self.assertEqual(account.calls, [])
        self.assertEqual(proposal.state, TradeProposalState.EXPIRED)

    def test_failed_risk_result_cannot_be_approved(self):
        risk = passing_risk(
            approved=False,
            warnings=[],
            violations=["max position exceeded"],
            risk_score=Decimal("0.95"),
        )
        proposal = self.gate.propose_trade(self.payload, risk)

        with self.assertRaises(RiskCheckFailedError):
            self.gate.approve(proposal.proposal_id, approver_id="human-1")

        self.assertEqual(proposal.state, TradeProposalState.PROPOSED)

    def test_unknown_proposal_id_fails_closed(self):
        account = SpyPaperAccount()

        with self.assertRaises(ProposalNotFoundError):
            self.gate.execute_paper_trade("missing-proposal", self.payload, account)

        self.assertEqual(account.calls, [])

    def test_terminal_state_writes_audit_entry(self):
        proposal = self.gate.propose_trade(self.payload, self.risk)

        self.gate.reject(proposal.proposal_id, actor_id="human-1", reason="not now")

        audit = self.gate.get_audit_log(proposal.proposal_id)
        self.assertEqual(audit[-1].event_type, "rejected")
        self.assertEqual(audit[-1].details, {"reason": "not now"})
        self.assertEqual(proposal.state, TradeProposalState.REJECTED)

    def test_real_paper_account_happy_path_executes_market_order(self):
        proposal = self.gate.propose_trade(self.payload, self.risk)
        self.gate.approve(proposal.proposal_id, approver_id="human-1")
        account = PaperTradingAccount(initial_balance=Decimal("10000"))

        order_id = self.gate.execute_paper_trade(
            proposal.proposal_id, self.payload, account
        )

        self.assertEqual(account.get_order_status(order_id), OrderStatus.FILLED)

    def _assert_changed_payload_blocked(self, **overrides):
        proposal = self.gate.propose_trade(self.payload, self.risk)
        self.gate.approve(proposal.proposal_id, approver_id="human-1")
        changed_payload = replace(self.payload, **overrides)
        account = SpyPaperAccount()

        with self.assertRaises(PayloadDigestMismatchError):
            self.gate.execute_paper_trade(
                proposal.proposal_id, changed_payload, account
            )

        self.assertEqual(account.calls, [])
        self.assertEqual(proposal.state, TradeProposalState.APPROVED)


if __name__ == "__main__":
    unittest.main()
