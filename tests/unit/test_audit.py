"""Tests for audit logging service."""

from datetime import datetime, timedelta

import pytest

from app.services.audit import (
    AuditAction,
    AuditCategory,
    AuditEntry,
    AuditLogger,
    AuditQuery,
    AuditSeverity,
    get_audit_logger,
)


class TestAuditEntry:
    """Tests for audit entry schema."""

    def test_entry_creation(self):
        """Test creating an entry."""
        entry = AuditEntry(
            entry_id="test-123",
            timestamp=datetime.now(),
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            description="User logged in",
        )

        assert entry.entry_id == "test-123"
        assert entry.category == AuditCategory.AUTHENTICATION
        assert entry.action == AuditAction.LOGIN_SUCCESS
        assert entry.success is True

    def test_entry_with_actor(self):
        """Test entry with actor info."""
        entry = AuditEntry(
            entry_id="test-123",
            timestamp=datetime.now(),
            category=AuditCategory.USER_ACTION,
            action=AuditAction.REDEMPTION_CREATED,
            description="Redemption created",
            actor_id="user-001",
            actor_ip="192.168.1.1",
        )

        assert entry.actor_id == "user-001"
        assert entry.actor_ip == "192.168.1.1"

    def test_entry_with_resource(self):
        """Test entry with resource info."""
        entry = AuditEntry(
            entry_id="test-123",
            timestamp=datetime.now(),
            category=AuditCategory.FINANCIAL,
            action=AuditAction.REDEMPTION_APPROVED,
            description="Redemption approved",
            resource_type="redemption",
            resource_id="RD-001",
        )

        assert entry.resource_type == "redemption"
        assert entry.resource_id == "RD-001"


class TestAuditLogger:
    """Tests for audit logger."""

    @pytest.fixture
    def logger(self):
        """Create fresh logger."""
        return AuditLogger()

    def test_log_basic(self, logger):
        """Test basic logging."""
        entry = logger.log(
            AuditCategory.AUTHENTICATION,
            AuditAction.LOGIN_SUCCESS,
            "User logged in",
        )

        assert entry.entry_id is not None
        assert entry.category == AuditCategory.AUTHENTICATION
        assert entry.action == AuditAction.LOGIN_SUCCESS

    def test_log_with_details(self, logger):
        """Test logging with details."""
        entry = logger.log(
            AuditCategory.FINANCIAL,
            AuditAction.REDEMPTION_CREATED,
            "Redemption created",
            actor_id="user-001",
            resource_type="redemption",
            resource_id="RD-001",
            details={"amount": "1000"},
        )

        assert entry.actor_id == "user-001"
        assert entry.resource_type == "redemption"
        assert entry.details["amount"] == "1000"

    def test_log_failure(self, logger):
        """Test logging failure."""
        entry = logger.log(
            AuditCategory.AUTHENTICATION,
            AuditAction.LOGIN_FAILED,
            "Invalid credentials",
            success=False,
            error_message="Wrong password",
        )

        assert entry.success is False
        assert entry.error_message == "Wrong password"

    def test_log_auth(self, logger):
        """Test auth logging helper."""
        entry = logger.log_auth(
            AuditAction.LOGIN_SUCCESS,
            "User authenticated",
            actor_id="user-001",
            actor_ip="192.168.1.1",
        )

        assert entry.category == AuditCategory.AUTHENTICATION
        assert entry.actor_id == "user-001"

    def test_log_financial(self, logger):
        """Test financial logging helper."""
        entry = logger.log_financial(
            AuditAction.REDEMPTION_APPROVED,
            "Redemption approved",
            resource_type="redemption",
            resource_id="RD-001",
            details={"amount": "5000"},
        )

        assert entry.category == AuditCategory.FINANCIAL
        assert entry.resource_type == "redemption"

    def test_log_security(self, logger):
        """Test security logging helper."""
        entry = logger.log_security(
            AuditAction.LOGIN_FAILED,
            "Multiple failed attempts",
            severity=AuditSeverity.WARNING,
            actor_ip="192.168.1.1",
        )

        assert entry.category == AuditCategory.SECURITY
        assert entry.severity == AuditSeverity.WARNING

    def test_log_emergency(self, logger):
        """Test emergency logging helper."""
        entry = logger.log_emergency(
            AuditAction.EMERGENCY_TRIGGERED,
            "Emergency protocol activated",
            details={"trigger": "high_risk"},
        )

        assert entry.category == AuditCategory.EMERGENCY
        assert entry.severity == AuditSeverity.CRITICAL

    def test_log_config_change(self, logger):
        """Test config change logging."""
        entry = logger.log_config_change(
            "Risk threshold updated",
            actor_id="admin-001",
            resource_type="risk_config",
            old_value={"threshold": 50},
            new_value={"threshold": 70},
        )

        assert entry.category == AuditCategory.CONFIGURATION
        assert entry.action == AuditAction.CONFIG_UPDATED
        assert entry.details["old_value"]["threshold"] == 50
        assert entry.details["new_value"]["threshold"] == 70


class TestAuditQuery:
    """Tests for audit querying."""

    @pytest.fixture
    def logger_with_entries(self):
        """Create logger with sample entries."""
        logger = AuditLogger()

        # Add sample entries
        logger.log(
            AuditCategory.AUTHENTICATION,
            AuditAction.LOGIN_SUCCESS,
            "User A logged in",
            actor_id="user-a",
        )
        logger.log(
            AuditCategory.AUTHENTICATION,
            AuditAction.LOGIN_FAILED,
            "User B failed login",
            actor_id="user-b",
            success=False,
        )
        logger.log(
            AuditCategory.FINANCIAL,
            AuditAction.REDEMPTION_CREATED,
            "Redemption created",
            actor_id="user-a",
            resource_type="redemption",
            resource_id="RD-001",
        )
        logger.log(
            AuditCategory.SECURITY,
            AuditAction.LOGIN_FAILED,
            "Suspicious activity",
            severity=AuditSeverity.WARNING,
        )

        return logger

    def test_query_all(self, logger_with_entries):
        """Test querying all entries."""
        query = AuditQuery(limit=100)
        results = logger_with_entries.query(query)

        assert len(results) == 4

    def test_query_by_category(self, logger_with_entries):
        """Test filtering by category."""
        query = AuditQuery(categories=[AuditCategory.AUTHENTICATION])
        results = logger_with_entries.query(query)

        assert len(results) == 2
        for entry in results:
            assert entry.category == AuditCategory.AUTHENTICATION

    def test_query_by_action(self, logger_with_entries):
        """Test filtering by action."""
        query = AuditQuery(actions=[AuditAction.LOGIN_FAILED])
        results = logger_with_entries.query(query)

        assert len(results) == 2

    def test_query_by_actor(self, logger_with_entries):
        """Test filtering by actor."""
        query = AuditQuery(actor_id="user-a")
        results = logger_with_entries.query(query)

        assert len(results) == 2
        for entry in results:
            assert entry.actor_id == "user-a"

    def test_query_by_success(self, logger_with_entries):
        """Test filtering by success."""
        query = AuditQuery(success=False)
        results = logger_with_entries.query(query)

        assert len(results) == 1
        assert results[0].success is False

    def test_query_by_resource(self, logger_with_entries):
        """Test filtering by resource."""
        query = AuditQuery(resource_type="redemption", resource_id="RD-001")
        results = logger_with_entries.query(query)

        assert len(results) == 1
        assert results[0].resource_id == "RD-001"

    def test_query_pagination(self, logger_with_entries):
        """Test pagination."""
        query = AuditQuery(limit=2, offset=0)
        results1 = logger_with_entries.query(query)

        query = AuditQuery(limit=2, offset=2)
        results2 = logger_with_entries.query(query)

        assert len(results1) == 2
        assert len(results2) == 2
        assert results1[0].entry_id != results2[0].entry_id


class TestAuditStats:
    """Tests for audit statistics."""

    @pytest.fixture
    def logger_with_entries(self):
        """Create logger with sample entries."""
        logger = AuditLogger()

        for _ in range(5):
            logger.log(
                AuditCategory.AUTHENTICATION,
                AuditAction.LOGIN_SUCCESS,
                "Login",
                actor_id="user-a",
            )
        for _ in range(3):
            logger.log(
                AuditCategory.FINANCIAL,
                AuditAction.REDEMPTION_CREATED,
                "Redemption",
                actor_id="user-b",
            )
        logger.log(
            AuditCategory.SECURITY,
            AuditAction.LOGIN_FAILED,
            "Failed",
            success=False,
        )

        return logger

    def test_get_stats(self, logger_with_entries):
        """Test getting statistics."""
        stats = logger_with_entries.get_stats()

        assert stats.total_entries == 9
        assert stats.entries_by_category["AUTHENTICATION"] == 5
        assert stats.entries_by_category["FINANCIAL"] == 3
        assert stats.entries_by_category["SECURITY"] == 1
        assert stats.unique_actors == 2
        assert stats.success_rate == (8 / 9) * 100


class TestAuditHelpers:
    """Tests for audit helper methods."""

    @pytest.fixture
    def logger(self):
        """Create logger with entries."""
        logger = AuditLogger()
        logger.log(
            AuditCategory.AUTHENTICATION,
            AuditAction.LOGIN_SUCCESS,
            "Login",
            correlation_id="corr-001",
        )
        logger.log(
            AuditCategory.FINANCIAL,
            AuditAction.REDEMPTION_CREATED,
            "Redemption",
            correlation_id="corr-001",
        )
        return logger

    def test_get_entry(self, logger):
        """Test getting entry by ID."""
        # Get an existing entry ID
        entries = logger.get_recent(limit=1)
        entry_id = entries[0].entry_id

        entry = logger.get_entry(entry_id)
        assert entry is not None
        assert entry.entry_id == entry_id

    def test_get_entry_not_found(self, logger):
        """Test getting nonexistent entry."""
        entry = logger.get_entry("nonexistent")
        assert entry is None

    def test_get_recent(self, logger):
        """Test getting recent entries."""
        entries = logger.get_recent(limit=10)
        assert len(entries) == 2

    def test_get_by_correlation(self, logger):
        """Test getting by correlation ID."""
        entries = logger.get_by_correlation("corr-001")
        assert len(entries) == 2

    def test_clear(self, logger):
        """Test clearing entries."""
        count = logger.clear()
        assert count == 2
        assert len(logger.get_recent()) == 0


class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_audit_logger_singleton(self):
        """Test singleton returns same instance."""
        # Reset singleton
        import app.services.audit.logger as logger_module

        logger_module._audit_logger = None

        logger1 = get_audit_logger()
        logger2 = get_audit_logger()

        assert logger1 is logger2
