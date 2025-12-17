"""Fund service module.

Provides services for fund data retrieval with hybrid mock/real data sources.
"""

from app.services.fund.service import FundService
from app.services.fund.metrics import FundMetricsService

__all__ = [
    "FundService",
    "FundMetricsService",
]
