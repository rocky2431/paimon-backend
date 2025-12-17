"""On-chain approval execution service.

Executes approval decisions on-chain by calling RedemptionManager contract methods.
Implements VIP_APPROVER_ROLE functionality per 04-approval-workflow.md.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.core.config import get_settings
from app.infrastructure.blockchain.client import BSCClient
from app.infrastructure.blockchain.contracts import get_abi_loader
from app.infrastructure.blockchain.transaction import (
    TransactionResult,
    TransactionService,
    TransactionStatus,
    get_transaction_service,
)
from app.services.approval.schemas import ApprovalResult, ApprovalTicketType

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """On-chain execution status."""

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    NOT_REQUIRED = "NOT_REQUIRED"


@dataclass
class ApprovalExecutionResult:
    """Result of on-chain approval execution."""

    status: ExecutionStatus
    tx_hash: str | None = None
    block_number: int | None = None
    gas_used: int | None = None
    error: str | None = None
    executed_at: datetime | None = None


class ApprovalExecutor:
    """Executes approval decisions on-chain.

    Implements the on-chain execution flow per 04-approval-workflow.md:
    - Calls approveRedemption() for approved redemptions
    - Calls rejectRedemption() for rejected redemptions
    - Supports custom settlement times via approveRedemptionWithDate()
    """

    def __init__(
        self,
        tx_service: TransactionService | None = None,
        wait_for_confirmation: bool = True,
        confirmation_timeout: int = 120,
    ):
        """Initialize approval executor.

        Args:
            tx_service: Transaction service for sending transactions
            wait_for_confirmation: Whether to wait for tx confirmation
            confirmation_timeout: Timeout for confirmation in seconds
        """
        self.tx_service = tx_service or get_transaction_service()
        self.abi_loader = get_abi_loader()
        self.wait_for_confirmation = wait_for_confirmation
        self.confirmation_timeout = confirmation_timeout
        self.settings = get_settings()

    async def execute_redemption_approval(
        self,
        request_id: int,
        result: ApprovalResult,
        custom_settlement_time: int = 0,
        rejection_reason: str = "",
    ) -> ApprovalExecutionResult:
        """Execute redemption approval on-chain.

        Per 04-approval-workflow.md Section 6 (on-chain execution):
        - VIP_APPROVER_ROLE calls approveRedemption() or rejectRedemption()

        Args:
            request_id: On-chain redemption request ID
            result: Approval result (APPROVED or REJECTED)
            custom_settlement_time: Custom settlement timestamp for approved
                                   (0 = use default)
            rejection_reason: Reason for rejection

        Returns:
            ApprovalExecutionResult with transaction details
        """
        if result not in (ApprovalResult.APPROVED, ApprovalResult.REJECTED):
            return ApprovalExecutionResult(
                status=ExecutionStatus.NOT_REQUIRED,
                error=f"Result {result} does not require on-chain execution",
            )

        logger.info(
            f"Executing on-chain approval: request_id={request_id}, "
            f"result={result.value}"
        )

        abi = self.abi_loader.redemption_manager_abi
        address = self.settings.active_redemption_manager

        try:
            if result == ApprovalResult.APPROVED:
                tx_result = await self._execute_approve(
                    request_id=request_id,
                    custom_settlement_time=custom_settlement_time,
                    abi=abi,
                    address=address,
                )
            else:
                tx_result = await self._execute_reject(
                    request_id=request_id,
                    reason=rejection_reason,
                    abi=abi,
                    address=address,
                )

            return self._to_execution_result(tx_result)

        except Exception as e:
            logger.error(f"On-chain execution failed: {e}")
            return ApprovalExecutionResult(
                status=ExecutionStatus.FAILED,
                error=str(e),
            )

    async def _execute_approve(
        self,
        request_id: int,
        custom_settlement_time: int,
        abi: list[dict[str, Any]],
        address: str,
    ) -> TransactionResult:
        """Execute approveRedemption or approveRedemptionWithDate."""
        if custom_settlement_time > 0:
            logger.info(
                f"Approving with custom settlement time: {custom_settlement_time}"
            )
            return await self._send_tx(
                address=address,
                abi=abi,
                function_name="approveRedemptionWithDate",
                args=[request_id, custom_settlement_time],
            )
        else:
            return await self._send_tx(
                address=address,
                abi=abi,
                function_name="approveRedemption",
                args=[request_id],
            )

    async def _execute_reject(
        self,
        request_id: int,
        reason: str,
        abi: list[dict[str, Any]],
        address: str,
    ) -> TransactionResult:
        """Execute rejectRedemption."""
        return await self._send_tx(
            address=address,
            abi=abi,
            function_name="rejectRedemption",
            args=[request_id, reason or "Rejected by approver"],
        )

    async def _send_tx(
        self,
        address: str,
        abi: list[dict[str, Any]],
        function_name: str,
        args: list[Any],
    ) -> TransactionResult:
        """Send transaction with optional confirmation wait."""
        if self.wait_for_confirmation:
            return await self.tx_service.send_and_wait(
                contract_address=address,
                abi=abi,
                function_name=function_name,
                args=args,
                timeout=self.confirmation_timeout,
            )
        else:
            return await self.tx_service.send_transaction(
                contract_address=address,
                abi=abi,
                function_name=function_name,
                args=args,
            )

    def _to_execution_result(
        self, tx_result: TransactionResult
    ) -> ApprovalExecutionResult:
        """Convert TransactionResult to ApprovalExecutionResult."""
        status_map = {
            TransactionStatus.SUCCESS: ExecutionStatus.SUCCESS,
            TransactionStatus.FAILED: ExecutionStatus.FAILED,
            TransactionStatus.TIMEOUT: ExecutionStatus.TIMEOUT,
            TransactionStatus.PENDING: ExecutionStatus.PENDING,
        }

        return ApprovalExecutionResult(
            status=status_map.get(tx_result.status, ExecutionStatus.FAILED),
            tx_hash=tx_result.tx_hash,
            block_number=tx_result.block_number,
            gas_used=tx_result.gas_used,
            error=tx_result.error,
            executed_at=datetime.now(timezone.utc) if tx_result.tx_hash else None,
        )

    async def execute_approval_ticket(
        self,
        ticket_type: ApprovalTicketType,
        reference_id: str,
        result: ApprovalResult,
        **kwargs: Any,
    ) -> ApprovalExecutionResult:
        """Execute approval for any ticket type.

        Routes to appropriate execution method based on ticket type.

        Args:
            ticket_type: Type of approval ticket
            reference_id: ID of the referenced entity
            result: Approval result
            **kwargs: Additional arguments for specific ticket types

        Returns:
            ApprovalExecutionResult
        """
        if ticket_type == ApprovalTicketType.REDEMPTION:
            return await self.execute_redemption_approval(
                request_id=int(reference_id),
                result=result,
                custom_settlement_time=kwargs.get("custom_settlement_time", 0),
                rejection_reason=kwargs.get("rejection_reason", ""),
            )

        elif ticket_type == ApprovalTicketType.REBALANCING:
            # TODO: Implement rebalancing approval execution
            logger.warning(f"Rebalancing approval execution not yet implemented")
            return ApprovalExecutionResult(
                status=ExecutionStatus.NOT_REQUIRED,
                error="Rebalancing approval execution not implemented",
            )

        elif ticket_type == ApprovalTicketType.EMERGENCY:
            # Emergency mode changes may require on-chain execution
            # TODO: Implement emergency approval execution
            logger.warning(f"Emergency approval execution not yet implemented")
            return ApprovalExecutionResult(
                status=ExecutionStatus.NOT_REQUIRED,
                error="Emergency approval execution not implemented",
            )

        else:
            return ApprovalExecutionResult(
                status=ExecutionStatus.NOT_REQUIRED,
                error=f"Ticket type {ticket_type} does not require on-chain execution",
            )


# Factory function
def get_approval_executor(
    wait_for_confirmation: bool = True,
    confirmation_timeout: int = 120,
) -> ApprovalExecutor:
    """Create ApprovalExecutor instance.

    Args:
        wait_for_confirmation: Whether to wait for tx confirmation
        confirmation_timeout: Timeout for confirmation in seconds

    Returns:
        Configured ApprovalExecutor instance
    """
    return ApprovalExecutor(
        wait_for_confirmation=wait_for_confirmation,
        confirmation_timeout=confirmation_timeout,
    )
