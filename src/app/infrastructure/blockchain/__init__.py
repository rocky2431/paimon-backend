"""Blockchain infrastructure module."""

from app.infrastructure.blockchain.client import BSCClient, ChainClient
from app.infrastructure.blockchain.contracts import ContractManager, get_abi_loader
from app.infrastructure.blockchain.events import EventParser, EventType, ParsedEvent
from app.infrastructure.blockchain.transaction import (
    TransactionResult,
    TransactionService,
    TransactionStatus,
    get_transaction_service,
)

__all__ = [
    # Client
    "ChainClient",
    "BSCClient",
    # Contracts
    "ContractManager",
    "get_abi_loader",
    # Events
    "EventParser",
    "EventType",
    "ParsedEvent",
    # Transactions (v2.0.0)
    "TransactionService",
    "TransactionResult",
    "TransactionStatus",
    "get_transaction_service",
]
