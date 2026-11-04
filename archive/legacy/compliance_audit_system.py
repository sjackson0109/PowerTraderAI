"""
PowerTrader AI - Compliance and Audit System
Regulatory compliance, audit trails, and transaction logging for institutional requirements
"""

import csv
import hashlib
import io
import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of audit events"""

    ORDER_CREATED = "order_created"
    ORDER_MODIFIED = "order_modified"
    ORDER_EXECUTED = "order_executed"
    ORDER_CANCELLED = "order_cancelled"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    RISK_BREACH = "risk_breach"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    SYSTEM_ERROR = "system_error"
    COMPLIANCE_VIOLATION = "compliance_violation"
    CONFIGURATION_CHANGE = "configuration_change"


class RiskLevel(Enum):
    """Risk classification levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplianceStatus(Enum):
    """Compliance check status"""

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    EXEMPT = "exempt"


@dataclass
class AuditEvent:
    """Comprehensive audit event record"""

    event_id: str
    event_type: EventType
    timestamp: datetime
    user_id: str
    session_id: str
    entity_type: str  # order, position, user, system
    entity_id: str
    action: str
    details: Dict[str, Any]
    risk_level: RiskLevel
    compliance_status: ComplianceStatus
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "session_id": self.session_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "action": self.action,
            "details": self.details,
            "risk_level": self.risk_level.value,
            "compliance_status": self.compliance_status.value,
            "source_ip": self.source_ip,
            "user_agent": self.user_agent,
            "correlation_id": self.correlation_id,
        }


@dataclass
class ComplianceRule:
    """Compliance rule definition"""

    rule_id: str
    name: str
    description: str
    rule_type: str  # position_limit, volume_limit, time_restriction, etc.
    parameters: Dict[str, Any]
    severity: RiskLevel
    active: bool = True
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class ComplianceEngine:
    """Core compliance monitoring and enforcement engine"""

    def __init__(self):
        self.rules: Dict[str, ComplianceRule] = {}
        self.violations: List[Dict[str, Any]] = []
        self.exemptions: Set[str] = set()

        # Load default compliance rules
        self._load_default_rules()

    def _load_default_rules(self):
        """Load default compliance rules"""
        default_rules = [
            ComplianceRule(
                rule_id="MAX_POSITION_SIZE",
                name="Maximum Position Size",
                description="Limit maximum position size per symbol",
                rule_type="position_limit",
                parameters={"max_size": 1000000, "currency": "USD"},
                severity=RiskLevel.HIGH,
            ),
            ComplianceRule(
                rule_id="DAILY_VOLUME_LIMIT",
                name="Daily Trading Volume Limit",
                description="Limit daily trading volume per account",
                rule_type="volume_limit",
                parameters={"max_volume": 10000000, "currency": "USD"},
                severity=RiskLevel.HIGH,
            ),
            ComplianceRule(
                rule_id="CONCENTRATION_RISK",
                name="Portfolio Concentration Risk",
                description="Limit concentration in single asset",
                rule_type="concentration_limit",
                parameters={"max_concentration": 0.25},
                severity=RiskLevel.MEDIUM,
            ),
            ComplianceRule(
                rule_id="TRADING_HOURS",
                name="Trading Hours Restriction",
                description="Restrict trading to market hours",
                rule_type="time_restriction",
                parameters={"start_hour": 9, "end_hour": 16, "timezone": "UTC"},
                severity=RiskLevel.LOW,
            ),
            ComplianceRule(
                rule_id="ORDER_SIZE_CHECK",
                name="Minimum Order Size",
                description="Enforce minimum viable order size",
                rule_type="order_validation",
                parameters={"min_size": 0.001},
                severity=RiskLevel.LOW,
            ),
        ]

        for rule in default_rules:
            self.rules[rule.rule_id] = rule

    def add_rule(self, rule: ComplianceRule) -> bool:
        """Add new compliance rule"""
        try:
            self.rules[rule.rule_id] = rule
            logger.info(f"Compliance rule added: {rule.name}")
            return True
        except Exception as e:
            logger.error(f"Error adding compliance rule: {e}")
            return False

    def check_compliance(
        self, entity_type: str, entity_data: Dict[str, Any]
    ) -> tuple[ComplianceStatus, List[str]]:
        """Check compliance for entity against all relevant rules"""
        violations = []
        overall_status = ComplianceStatus.PASSED

        for rule in self.rules.values():
            if not rule.active:
                continue

            try:
                is_compliant, message = self._check_rule(rule, entity_type, entity_data)

                if not is_compliant:
                    violations.append(f"Rule '{rule.name}': {message}")

                    if rule.severity == RiskLevel.CRITICAL:
                        overall_status = ComplianceStatus.FAILED
                    elif (
                        rule.severity == RiskLevel.HIGH
                        and overall_status != ComplianceStatus.FAILED
                    ):
                        overall_status = ComplianceStatus.FAILED
                    elif (
                        rule.severity == RiskLevel.MEDIUM
                        and overall_status == ComplianceStatus.PASSED
                    ):
                        overall_status = ComplianceStatus.WARNING

            except Exception as e:
                logger.error(f"Error checking rule {rule.rule_id}: {e}")
                violations.append(f"Rule check error: {rule.name}")

        return overall_status, violations

    def _check_rule(
        self, rule: ComplianceRule, entity_type: str, entity_data: Dict[str, Any]
    ) -> tuple[bool, str]:
        """Check individual compliance rule"""
        if rule.rule_type == "position_limit":
            return self._check_position_limit(rule, entity_data)
        elif rule.rule_type == "volume_limit":
            return self._check_volume_limit(rule, entity_data)
        elif rule.rule_type == "concentration_limit":
            return self._check_concentration_limit(rule, entity_data)
        elif rule.rule_type == "time_restriction":
            return self._check_time_restriction(rule, entity_data)
        elif rule.rule_type == "order_validation":
            return self._check_order_validation(rule, entity_data)
        else:
            return True, "Unknown rule type"

    def _check_position_limit(
        self, rule: ComplianceRule, data: Dict[str, Any]
    ) -> tuple[bool, str]:
        """Check position size limits"""
        position_value = data.get("position_value", 0)
        max_size = rule.parameters.get("max_size", float("inf"))

        if position_value > max_size:
            return False, f"Position value {position_value} exceeds limit {max_size}"
        return True, ""

    def _check_volume_limit(
        self, rule: ComplianceRule, data: Dict[str, Any]
    ) -> tuple[bool, str]:
        """Check daily volume limits"""
        daily_volume = data.get("daily_volume", 0)
        max_volume = rule.parameters.get("max_volume", float("inf"))

        if daily_volume > max_volume:
            return False, f"Daily volume {daily_volume} exceeds limit {max_volume}"
        return True, ""

    def _check_concentration_limit(
        self, rule: ComplianceRule, data: Dict[str, Any]
    ) -> tuple[bool, str]:
        """Check portfolio concentration limits"""
        concentration = data.get("concentration", 0)
        max_concentration = rule.parameters.get("max_concentration", 1.0)

        if concentration > max_concentration:
            return (
                False,
                f"Concentration {concentration:.2%} exceeds limit {max_concentration:.2%}",
            )
        return True, ""

    def _check_time_restriction(
        self, rule: ComplianceRule, data: Dict[str, Any]
    ) -> tuple[bool, str]:
        """Check trading time restrictions"""
        current_hour = datetime.now().hour
        start_hour = rule.parameters.get("start_hour", 0)
        end_hour = rule.parameters.get("end_hour", 24)

        if not (start_hour <= current_hour <= end_hour):
            return False, f"Trading outside allowed hours ({start_hour}-{end_hour})"
        return True, ""

    def _check_order_validation(
        self, rule: ComplianceRule, data: Dict[str, Any]
    ) -> tuple[bool, str]:
        """Check order validation rules"""
        order_size = data.get("quantity", 0)
        min_size = rule.parameters.get("min_size", 0)

        if order_size < min_size:
            return False, f"Order size {order_size} below minimum {min_size}"
        return True, ""


class AuditTrail:
    """Comprehensive audit trail system"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            import pt_paths

            db_path = pt_paths.data_file("compliance_audit.db")
        self.db_path = db_path
        self.db_lock = threading.Lock()
        self._init_database()

    def _init_database(self):
        """Initialize audit database"""
        try:
            with self.db_lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                # Audit events table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS audit_events (
                        event_id TEXT PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        entity_type TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        details TEXT NOT NULL,
                        risk_level TEXT NOT NULL,
                        compliance_status TEXT NOT NULL,
                        source_ip TEXT,
                        user_agent TEXT,
                        correlation_id TEXT,
                        checksum TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Compliance violations table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS compliance_violations (
                        violation_id TEXT PRIMARY KEY,
                        rule_id TEXT NOT NULL,
                        entity_type TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        violation_details TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        resolved BOOLEAN DEFAULT FALSE,
                        resolution_notes TEXT,
                        resolved_at TIMESTAMP
                    )
                """)

                # User sessions table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        session_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        login_time TIMESTAMP NOT NULL,
                        logout_time TIMESTAMP,
                        source_ip TEXT,
                        user_agent TEXT,
                        active BOOLEAN DEFAULT TRUE
                    )
                """)

                conn.commit()
                conn.close()

            logger.info("Audit database initialized")

        except Exception as e:
            logger.error(f"Error initializing audit database: {e}")

    def log_event(self, event: AuditEvent) -> bool:
        """Log audit event to database"""
        try:
            # Calculate checksum for integrity
            event_data = json.dumps(event.to_dict(), sort_keys=True)
            checksum = hashlib.sha256(event_data.encode()).hexdigest()

            with self.db_lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO audit_events
                    (event_id, event_type, timestamp, user_id, session_id, entity_type,
                     entity_id, action, details, risk_level, compliance_status,
                     source_ip, user_agent, correlation_id, checksum)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        event.event_id,
                        event.event_type.value,
                        event.timestamp.isoformat(),
                        event.user_id,
                        event.session_id,
                        event.entity_type,
                        event.entity_id,
                        event.action,
                        json.dumps(event.details),
                        event.risk_level.value,
                        event.compliance_status.value,
                        event.source_ip,
                        event.user_agent,
                        event.correlation_id,
                        checksum,
                    ),
                )

                conn.commit()
                conn.close()

            return True

        except Exception as e:
            logger.error(f"Error logging audit event: {e}")
            return False

    def log_violation(
        self,
        rule_id: str,
        entity_type: str,
        entity_id: str,
        details: str,
        severity: RiskLevel,
    ) -> str:
        """Log compliance violation"""
        try:
            violation_id = str(uuid.uuid4())

            with self.db_lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO compliance_violations
                    (violation_id, rule_id, entity_type, entity_id, violation_details,
                     severity, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        violation_id,
                        rule_id,
                        entity_type,
                        entity_id,
                        details,
                        severity.value,
                        datetime.now().isoformat(),
                    ),
                )

                conn.commit()
                conn.close()

            return violation_id

        except Exception as e:
            logger.error(f"Error logging compliance violation: {e}")
            return ""

    def get_audit_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[str] = None,
        event_type: Optional[EventType] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Retrieve audit events with filters"""
        try:
            with self.db_lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                query = "SELECT * FROM audit_events WHERE 1=1"
                params = []

                if start_date:
                    query += " AND timestamp >= ?"
                    params.append(start_date.isoformat())

                if end_date:
                    query += " AND timestamp <= ?"
                    params.append(end_date.isoformat())

                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)

                if event_type:
                    query += " AND event_type = ?"
                    params.append(event_type.value)

                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)

                columns = [desc[0] for desc in cursor.description]
                events = []
                for row in cursor.fetchall():
                    event_dict = dict(zip(columns, row))
                    # Parse JSON details
                    event_dict["details"] = json.loads(event_dict["details"])
                    events.append(event_dict)

                conn.close()
                return events

        except Exception as e:
            logger.error(f"Error retrieving audit events: {e}")
            return []

    def export_audit_report(
        self, start_date: datetime, end_date: datetime, format: str = "csv"
    ) -> Optional[str]:
        """Export audit report for regulatory compliance"""
        try:
            events = self.get_audit_events(start_date, end_date, limit=10000)

            if format.lower() == "csv":
                output = io.StringIO()
                writer = csv.writer(output)

                # Header
                writer.writerow(
                    [
                        "Event ID",
                        "Event Type",
                        "Timestamp",
                        "User ID",
                        "Session ID",
                        "Entity Type",
                        "Entity ID",
                        "Action",
                        "Risk Level",
                        "Compliance Status",
                        "Source IP",
                        "Details",
                    ]
                )

                # Data
                for event in events:
                    writer.writerow(
                        [
                            event["event_id"],
                            event["event_type"],
                            event["timestamp"],
                            event["user_id"],
                            event["session_id"],
                            event["entity_type"],
                            event["entity_id"],
                            event["action"],
                            event["risk_level"],
                            event["compliance_status"],
                            event.get("source_ip", ""),
                            json.dumps(event["details"]),
                        ]
                    )

                return output.getvalue()

            elif format.lower() == "json":
                return json.dumps(events, indent=2)

        except Exception as e:
            logger.error(f"Error exporting audit report: {e}")
            return None


class ComplianceAuditSystem:
    """Main compliance and audit system"""

    def __init__(self):
        self.compliance_engine = ComplianceEngine()
        self.audit_trail = AuditTrail()
        self.active_sessions = {}
        self.current_user = "system"
        self.current_session = str(uuid.uuid4())

        # Log system startup
        self._log_system_event(
            "System initialized", EventType.SYSTEM_ERROR, RiskLevel.LOW
        )

    def start_user_session(
        self, user_id: str, source_ip: str = None, user_agent: str = None
    ) -> str:
        """Start new user session"""
        session_id = str(uuid.uuid4())

        self.active_sessions[session_id] = {
            "user_id": user_id,
            "login_time": datetime.now(),
            "source_ip": source_ip,
            "user_agent": user_agent,
            "active": True,
        }

        # Log session start
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.USER_LOGIN,
            timestamp=datetime.now(),
            user_id=user_id,
            session_id=session_id,
            entity_type="session",
            entity_id=session_id,
            action="login",
            details={"source_ip": source_ip, "user_agent": user_agent},
            risk_level=RiskLevel.LOW,
            compliance_status=ComplianceStatus.PASSED,
            source_ip=source_ip,
            user_agent=user_agent,
        )

        self.audit_trail.log_event(event)

        return session_id

    def validate_order(
        self, order_data: Dict[str, Any], user_id: str, session_id: str
    ) -> tuple[ComplianceStatus, List[str]]:
        """Validate order against compliance rules"""
        # Check compliance
        status, violations = self.compliance_engine.check_compliance(
            "order", order_data
        )

        # Log compliance check
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=(
                EventType.ORDER_CREATED
                if status == ComplianceStatus.PASSED
                else EventType.COMPLIANCE_VIOLATION
            ),
            timestamp=datetime.now(),
            user_id=user_id,
            session_id=session_id,
            entity_type="order",
            entity_id=order_data.get("order_id", "unknown"),
            action="compliance_check",
            details={
                "order_data": order_data,
                "violations": violations,
                "status": status.value,
            },
            risk_level=(
                RiskLevel.HIGH if status == ComplianceStatus.FAILED else RiskLevel.LOW
            ),
            compliance_status=status,
        )

        self.audit_trail.log_event(event)

        # Log violations if any
        if violations and status == ComplianceStatus.FAILED:
            for violation in violations:
                self.audit_trail.log_violation(
                    "COMPLIANCE_CHECK",
                    "order",
                    order_data.get("order_id", "unknown"),
                    violation,
                    RiskLevel.HIGH,
                )

        return status, violations

    def log_order_execution(
        self,
        order_id: str,
        execution_details: Dict[str, Any],
        user_id: str,
        session_id: str,
    ):
        """Log order execution for audit trail"""
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.ORDER_EXECUTED,
            timestamp=datetime.now(),
            user_id=user_id,
            session_id=session_id,
            entity_type="order",
            entity_id=order_id,
            action="executed",
            details=execution_details,
            risk_level=RiskLevel.MEDIUM,
            compliance_status=ComplianceStatus.PASSED,
        )

        self.audit_trail.log_event(event)

    def log_risk_breach(
        self, breach_type: str, details: Dict[str, Any], user_id: str, session_id: str
    ):
        """Log risk management breach"""
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.RISK_BREACH,
            timestamp=datetime.now(),
            user_id=user_id,
            session_id=session_id,
            entity_type="risk",
            entity_id=breach_type,
            action="risk_breach",
            details=details,
            risk_level=RiskLevel.CRITICAL,
            compliance_status=ComplianceStatus.FAILED,
        )

        self.audit_trail.log_event(event)

        # Log as violation
        self.audit_trail.log_violation(
            "RISK_BREACH",
            "risk",
            breach_type,
            f"Risk breach: {breach_type}",
            RiskLevel.CRITICAL,
        )

    def _log_system_event(
        self, message: str, event_type: EventType, risk_level: RiskLevel
    ):
        """Log system-level events"""
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(),
            user_id="system",
            session_id=self.current_session,
            entity_type="system",
            entity_id="compliance_system",
            action=message,
            details={"message": message},
            risk_level=risk_level,
            compliance_status=ComplianceStatus.PASSED,
        )

        self.audit_trail.log_event(event)

    def get_compliance_report(
        self, start_date: datetime, end_date: datetime
    ) -> Dict[str, Any]:
        """Generate comprehensive compliance report"""
        try:
            # Get audit events
            events = self.audit_trail.get_audit_events(
                start_date, end_date, limit=10000
            )

            # Analyze events
            event_counts = {}
            compliance_statuses = {}
            risk_levels = {}

            for event in events:
                # Count event types
                event_type = event["event_type"]
                event_counts[event_type] = event_counts.get(event_type, 0) + 1

                # Count compliance statuses
                status = event["compliance_status"]
                compliance_statuses[status] = compliance_statuses.get(status, 0) + 1

                # Count risk levels
                risk = event["risk_level"]
                risk_levels[risk] = risk_levels.get(risk, 0) + 1

            # Calculate compliance metrics
            total_events = len(events)
            failed_events = compliance_statuses.get("failed", 0)
            compliance_rate = (
                ((total_events - failed_events) / total_events * 100)
                if total_events > 0
                else 100
            )

            return {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "summary": {
                    "total_events": total_events,
                    "compliance_rate": round(compliance_rate, 2),
                    "violations": failed_events,
                    "warnings": compliance_statuses.get("warning", 0),
                },
                "event_breakdown": event_counts,
                "compliance_breakdown": compliance_statuses,
                "risk_breakdown": risk_levels,
                "active_rules": len(self.compliance_engine.rules),
                "generated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error generating compliance report: {e}")
            return {"error": str(e)}


# Global compliance system instance
compliance_system = None


def get_compliance_system() -> ComplianceAuditSystem:
    """Get global compliance system instance"""
    global compliance_system
    if compliance_system is None:
        compliance_system = ComplianceAuditSystem()
    return compliance_system


if __name__ == "__main__":
    # Test the compliance system
    system = get_compliance_system()

    # Test order validation
    order_data = {
        "order_id": "TEST_001",
        "symbol": "BTC/USD",
        "quantity": 1.5,
        "position_value": 75000,
        "daily_volume": 150000,
    }

    session_id = system.start_user_session("trader_001", "192.168.1.100")
    status, violations = system.validate_order(order_data, "trader_001", session_id)

    print(f"Order validation: {status}")
    if violations:
        print(f"Violations: {violations}")

    # Generate sample report
    start_date = datetime.now() - timedelta(days=1)
    end_date = datetime.now()

    report = system.get_compliance_report(start_date, end_date)
    print(f"Compliance report: {json.dumps(report, indent=2)}")
