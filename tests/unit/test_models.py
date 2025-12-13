"""Test cases for database models."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest


class TestRedemptionRequest:
    """Test RedemptionRequest model."""

    def test_redemption_request_creation(self):
        """Test creating a redemption request."""
        from app.models.redemption import RedemptionRequest

        request = RedemptionRequest(
            request_id=Decimal("123456789"),
            tx_hash="0x" + "a" * 64,
            block_number=12345678,
            log_index=0,
            owner="0x" + "1" * 40,
            receiver="0x" + "2" * 40,
            shares=Decimal("1000000000000000000"),
            gross_amount=Decimal("1000000000000000000000"),
            locked_nav=Decimal("1050000000000000000"),
            estimated_fee=Decimal("10000000000000000000"),
            request_time=datetime.now(timezone.utc),
            settlement_time=datetime.now(timezone.utc),
            channel="STANDARD",
            status="PENDING",
            requires_approval=False,
        )

        assert request.status == "PENDING"
        assert request.requires_approval is False
        assert request.channel == "STANDARD"

    def test_redemption_status_values(self):
        """Test that status has valid values."""
        valid_statuses = ["PENDING", "PENDING_APPROVAL", "APPROVED", "SETTLED", "CANCELLED", "REJECTED"]
        from app.models.redemption import RedemptionRequest

        for status in valid_statuses:
            request = RedemptionRequest(
                request_id=Decimal("1"),
                tx_hash="0x" + "a" * 64,
                block_number=1,
                log_index=0,
                owner="0x" + "1" * 40,
                receiver="0x" + "2" * 40,
                shares=Decimal("1"),
                gross_amount=Decimal("1"),
                locked_nav=Decimal("1"),
                estimated_fee=Decimal("1"),
                request_time=datetime.now(timezone.utc),
                settlement_time=datetime.now(timezone.utc),
                channel="STANDARD",
                status=status,
            )
            assert request.status == status


class TestApprovalTicket:
    """Test ApprovalTicket model."""

    def test_approval_ticket_creation(self):
        """Test creating an approval ticket."""
        from app.models.approval import ApprovalTicket

        ticket = ApprovalTicket(
            id="ticket-001",
            ticket_type="REDEMPTION",
            reference_type="redemption_request",
            reference_id="123",
            requester="0x" + "1" * 40,
            amount=Decimal("1000000000000000000000"),
            sla_warning=datetime.now(timezone.utc),
            sla_deadline=datetime.now(timezone.utc),
            status="PENDING",
            required_approvals=1,
            current_approvals=0,
        )

        assert ticket.status == "PENDING"
        assert ticket.required_approvals == 1
        assert ticket.current_approvals == 0


class TestAssetConfig:
    """Test AssetConfig model."""

    def test_asset_config_creation(self):
        """Test creating an asset config."""
        from app.models.asset import AssetConfig

        config = AssetConfig(
            token_address="0x" + "a" * 40,
            token_symbol="USDT",
            token_name="Tether USD",
            decimals=6,
            tier="L1",
            target_allocation=Decimal("0.10"),
            is_active=True,
        )

        assert config.tier == "L1"
        assert config.is_active is True
        assert config.decimals == 6


class TestAuditLog:
    """Test AuditLog model."""

    def test_audit_log_creation(self):
        """Test creating an audit log."""
        from app.models.audit import AuditLog

        log = AuditLog(
            action="CREATE",
            resource_type="redemption_request",
            resource_id="123",
            actor_address="0x" + "1" * 40,
        )

        assert log.action == "CREATE"
        assert log.resource_type == "redemption_request"
