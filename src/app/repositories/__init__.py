"""Repository layer for database operations.

This module provides async repository implementations using SQLAlchemy 2.x.
All repositories follow the Repository pattern with consistent CRUD operations.
"""

from app.repositories.base import BaseRepository
from app.repositories.redemption import RedemptionRepository
from app.repositories.approval import ApprovalRepository, ApprovalRecordRepository
from app.repositories.asset import AssetRepository
from app.repositories.rebalance import RebalanceRepository
from app.repositories.transaction import TransactionRepository
from app.repositories.risk_event import RiskEventRepository
from app.repositories.audit_log import AuditLogRepository
from app.repositories.snapshot import DailySnapshotRepository, RiskMetricsRepository

__all__ = [
    "BaseRepository",
    "RedemptionRepository",
    "ApprovalRepository",
    "ApprovalRecordRepository",
    "AssetRepository",
    "RebalanceRepository",
    "TransactionRepository",
    "RiskEventRepository",
    "AuditLogRepository",
    "DailySnapshotRepository",
    "RiskMetricsRepository",
]
