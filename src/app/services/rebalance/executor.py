"""Rebalancing execution engine."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from app.services.rebalance.executor_schemas import (
    ExecutionConfig,
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    RetryPolicy,
    SimulationResult,
    TransactionRecord,
    TransactionRequest,
    TransactionStatus,
    WalletConfig,
    WalletTier,
)
from app.services.rebalance.schemas import (
    RebalanceAction,
    RebalancePlan,
    RebalancePlanStep,
    RebalanceStatus,
)

logger = logging.getLogger(__name__)


class RebalanceExecutor:
    """Executor for rebalance plan transactions.

    Features:
    - eth_call simulation before execution
    - Tiered wallet selection (hot/warm/cold)
    - Transaction building and submission
    - State updates and monitoring
    - Retry on failure with backoff
    """

    # Default wallet configurations
    DEFAULT_WALLETS: dict[WalletTier, WalletConfig] = {
        WalletTier.HOT: WalletConfig(
            address="0x" + "1" * 40,
            tier=WalletTier.HOT,
            max_single_tx=Decimal("10000"),  # 10k
            daily_limit=Decimal("100000"),  # 100k
        ),
        WalletTier.WARM: WalletConfig(
            address="0x" + "2" * 40,
            tier=WalletTier.WARM,
            max_single_tx=Decimal("100000"),  # 100k
            daily_limit=Decimal("1000000"),  # 1M
        ),
        WalletTier.COLD: WalletConfig(
            address="0x" + "3" * 40,
            tier=WalletTier.COLD,
            max_single_tx=Decimal("1000000"),  # 1M
            daily_limit=Decimal("10000000"),  # 10M
        ),
    }

    def __init__(
        self,
        config: ExecutionConfig | None = None,
        wallets: dict[WalletTier, WalletConfig] | None = None,
        simulator: Callable[[TransactionRequest], SimulationResult] | None = None,
        submitter: Callable[[TransactionRequest, WalletTier], str | None]
        | None = None,
    ):
        """Initialize rebalance executor.

        Args:
            config: Execution configuration
            wallets: Wallet configurations by tier
            simulator: Custom simulation function (for testing)
            submitter: Custom transaction submitter (for testing)
        """
        self.config = config or ExecutionConfig()
        # Create a deep copy of wallets to avoid shared state issues
        if wallets:
            self.wallets = wallets
        else:
            self.wallets = {
                tier: WalletConfig(
                    address=cfg.address,
                    tier=cfg.tier,
                    max_single_tx=cfg.max_single_tx,
                    daily_limit=cfg.daily_limit,
                    is_active=cfg.is_active,
                )
                for tier, cfg in self.DEFAULT_WALLETS.items()
            }
        self._simulator = simulator
        self._submitter = submitter
        self._executions: dict[str, ExecutionContext] = {}
        self._daily_usage: dict[WalletTier, Decimal] = {
            tier: Decimal(0) for tier in WalletTier
        }

    def select_wallet(self, amount: Decimal) -> WalletConfig | None:
        """Select appropriate wallet based on amount.

        Selection priority: HOT -> WARM -> COLD
        Considers: single tx limit, daily limit, active status

        Args:
            amount: Transaction amount

        Returns:
            Selected wallet config or None if no suitable wallet
        """
        for tier in [WalletTier.HOT, WalletTier.WARM, WalletTier.COLD]:
            wallet = self.wallets.get(tier)
            if not wallet or not wallet.is_active:
                continue

            # Check single transaction limit
            if amount > wallet.max_single_tx:
                continue

            # Check daily limit
            current_usage = self._daily_usage.get(tier, Decimal(0))
            if current_usage + amount > wallet.daily_limit:
                continue

            return wallet

        return None

    async def simulate_transaction(
        self,
        request: TransactionRequest,
    ) -> SimulationResult:
        """Simulate transaction using eth_call.

        Args:
            request: Transaction request to simulate

        Returns:
            Simulation result
        """
        if self._simulator:
            return self._simulator(request)

        # Default simulation (mock for now)
        return SimulationResult(
            success=True,
            gas_estimate=200000,
            return_data="0x",
            simulated_at=datetime.now(timezone.utc),
        )

    async def submit_transaction(
        self,
        request: TransactionRequest,
        wallet_tier: WalletTier,
    ) -> str | None:
        """Submit transaction to the blockchain.

        Args:
            request: Transaction request
            wallet_tier: Wallet tier to use for signing

        Returns:
            Transaction hash or None if failed
        """
        if self._submitter:
            return self._submitter(request, wallet_tier)

        # Default submission (mock for now)
        # Generate 64 hex chars for transaction hash
        return "0x" + uuid.uuid4().hex + uuid.uuid4().hex

    async def wait_for_confirmation(
        self,
        tx_hash: str,
        confirmations: int = 3,
    ) -> tuple[bool, int | None, str | None]:
        """Wait for transaction confirmation.

        Args:
            tx_hash: Transaction hash
            confirmations: Required confirmations

        Returns:
            Tuple of (success, block_number, error_message)
        """
        # Mock confirmation (would use actual chain polling)
        await asyncio.sleep(0.01)  # Simulate network latency
        return True, 12345678, None

    def _build_transaction_request(
        self,
        step: RebalancePlanStep,
        wallet: WalletConfig,
    ) -> TransactionRequest:
        """Build transaction request from plan step.

        Args:
            step: Rebalance plan step
            wallet: Wallet to use

        Returns:
            Transaction request
        """
        # Build call data based on action type
        data = self._encode_action_data(step)

        return TransactionRequest(
            step_id=step.step_id,
            from_address=wallet.address,
            to_address="0x" + "a" * 40,  # Contract address (would be from config)
            value=Decimal(0),
            data=data,
            gas_limit=300000,
        )

    def _encode_action_data(self, step: RebalancePlanStep) -> str:
        """Encode action data for transaction.

        Args:
            step: Rebalance plan step

        Returns:
            Hex-encoded call data
        """
        # Mock encoding (would use actual contract ABI)
        if step.action == RebalanceAction.SWAP:
            return "0x" + "swap" + "0" * 56
        elif step.action == RebalanceAction.LIQUIDATE:
            return "0x" + "liquidate" + "0" * 48
        elif step.action == RebalanceAction.DEPOSIT:
            return "0x" + "deposit" + "0" * 50
        elif step.action == RebalanceAction.WITHDRAW:
            return "0x" + "withdraw" + "0" * 48
        return "0x"

    async def _execute_step_with_retry(
        self,
        step: RebalancePlanStep,
        context: ExecutionContext,
    ) -> TransactionRecord:
        """Execute a single step with retry logic.

        Args:
            step: Step to execute
            context: Execution context

        Returns:
            Transaction record
        """
        policy = self.config.retry_policy
        retry_count = 0
        last_error = None

        while retry_count <= policy.max_retries:
            # Select wallet
            wallet = self.select_wallet(step.amount)
            if not wallet:
                raise ValueError(
                    f"No suitable wallet for amount {step.amount}"
                )

            # Build transaction
            tx_request = self._build_transaction_request(step, wallet)

            # Create transaction record
            tx_record = TransactionRecord(
                tx_id=f"TX-{uuid.uuid4().hex[:8].upper()}",
                step_id=step.step_id,
                status=TransactionStatus.PENDING,
                wallet_tier=wallet.tier,
                from_address=wallet.address,
                to_address=tx_request.to_address,
                value=tx_request.value,
                retry_count=retry_count,
                created_at=datetime.now(timezone.utc),
            )

            try:
                # Simulate if enabled
                if self.config.simulation_enabled:
                    tx_record.status = TransactionStatus.SIMULATING
                    sim_result = await self.simulate_transaction(tx_request)

                    if not sim_result.success:
                        tx_record.status = TransactionStatus.SIMULATION_FAILED
                        tx_record.error_message = sim_result.error_message
                        raise ValueError(
                            f"Simulation failed: {sim_result.error_message}"
                        )

                    tx_request.gas_limit = int(
                        sim_result.gas_estimate
                        * float(self.config.gas_price_multiplier)
                    )

                # Build and sign
                tx_record.status = TransactionStatus.BUILDING

                # Submit
                tx_record.status = TransactionStatus.SIGNING
                tx_record.submitted_at = datetime.now(timezone.utc)

                tx_hash = await self.submit_transaction(tx_request, wallet.tier)
                if not tx_hash:
                    tx_record.status = TransactionStatus.FAILED
                    tx_record.error_message = "Transaction submission failed"
                    raise ValueError("Transaction submission failed")

                tx_record.tx_hash = tx_hash
                tx_record.status = TransactionStatus.SUBMITTED

                # Wait for confirmation
                tx_record.status = TransactionStatus.CONFIRMING
                success, block_num, error = await self.wait_for_confirmation(
                    tx_hash, self.config.confirmation_blocks
                )

                if success:
                    tx_record.status = TransactionStatus.CONFIRMED
                    tx_record.block_number = block_num
                    tx_record.confirmed_at = datetime.now(timezone.utc)
                    tx_record.gas_used = tx_request.gas_limit

                    # Update daily usage
                    self._daily_usage[wallet.tier] += step.amount

                    return tx_record
                else:
                    tx_record.status = TransactionStatus.REVERTED
                    tx_record.error_message = error
                    raise ValueError(f"Transaction reverted: {error}")

            except Exception as e:
                last_error = str(e)
                tx_record.error_message = last_error
                logger.warning(
                    f"Step {step.step_id} attempt {retry_count + 1} failed: {e}"
                )

                # Check if should retry
                if tx_record.status not in policy.retry_on_statuses:
                    context.transactions.append(tx_record)
                    raise

                retry_count += 1
                if retry_count <= policy.max_retries:
                    # Calculate delay
                    delay = policy.base_delay_seconds
                    if policy.exponential_backoff:
                        delay = min(
                            delay * (2 ** (retry_count - 1)),
                            policy.max_delay_seconds,
                        )
                    await asyncio.sleep(delay)

        # All retries exhausted
        tx_record.status = TransactionStatus.FAILED
        tx_record.error_message = f"Max retries exceeded: {last_error}"
        context.transactions.append(tx_record)
        raise ValueError(f"Max retries exceeded for step {step.step_id}")

    async def execute_plan(
        self,
        plan: RebalancePlan,
    ) -> ExecutionResult:
        """Execute a rebalance plan.

        Args:
            plan: Rebalance plan to execute

        Returns:
            Execution result
        """
        if plan.status != RebalanceStatus.APPROVED:
            raise ValueError(
                f"Plan {plan.plan_id} is not approved (status: {plan.status})"
            )

        execution_id = f"EXE-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)

        context = ExecutionContext(
            plan_id=plan.plan_id,
            execution_id=execution_id,
            status=ExecutionStatus.PENDING,
            current_step=0,
            total_steps=len(plan.steps),
            started_at=now,
        )
        self._executions[execution_id] = context

        logger.info(
            f"Starting execution {execution_id} for plan {plan.plan_id} "
            f"with {len(plan.steps)} steps"
        )

        completed_steps = 0
        total_gas = 0
        total_value = Decimal(0)

        try:
            context.status = ExecutionStatus.SIMULATING

            # Execute each step
            for i, step in enumerate(plan.steps):
                context.current_step = i + 1
                context.status = ExecutionStatus.EXECUTING

                try:
                    tx_record = await self._execute_step_with_retry(step, context)
                    context.transactions.append(tx_record)
                    completed_steps += 1
                    total_gas += tx_record.gas_used or 0
                    total_value += step.amount

                    logger.info(
                        f"Step {step.step_id} completed: {tx_record.tx_hash}"
                    )

                except Exception as e:
                    logger.error(f"Step {step.step_id} failed: {e}")
                    # Continue to next step or abort based on config
                    if not self.config.parallel_execution:
                        # Sequential execution - abort on failure
                        context.status = ExecutionStatus.PARTIALLY_COMPLETED
                        context.error_message = str(e)
                        break

            # Determine final status
            if completed_steps == len(plan.steps):
                context.status = ExecutionStatus.COMPLETED
            elif completed_steps > 0:
                context.status = ExecutionStatus.PARTIALLY_COMPLETED
            else:
                context.status = ExecutionStatus.FAILED

        except Exception as e:
            context.status = ExecutionStatus.FAILED
            context.error_message = str(e)
            logger.error(f"Execution {execution_id} failed: {e}")

        context.completed_at = datetime.now(timezone.utc)

        # Calculate duration
        duration = None
        if context.completed_at:
            duration = (context.completed_at - context.started_at).total_seconds()

        result = ExecutionResult(
            execution_id=execution_id,
            plan_id=plan.plan_id,
            status=context.status,
            completed_steps=completed_steps,
            total_steps=len(plan.steps),
            transactions=context.transactions,
            total_gas_used=total_gas,
            total_value_moved=total_value,
            started_at=context.started_at,
            completed_at=context.completed_at,
            duration_seconds=duration,
            error_message=context.error_message,
        )

        logger.info(
            f"Execution {execution_id} finished: {context.status.value}, "
            f"{completed_steps}/{len(plan.steps)} steps completed"
        )

        return result

    def get_execution(self, execution_id: str) -> ExecutionContext | None:
        """Get execution context by ID.

        Args:
            execution_id: Execution ID

        Returns:
            Execution context or None
        """
        return self._executions.get(execution_id)

    def get_execution_status(self, execution_id: str) -> ExecutionStatus | None:
        """Get execution status by ID.

        Args:
            execution_id: Execution ID

        Returns:
            Execution status or None
        """
        context = self._executions.get(execution_id)
        return context.status if context else None

    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel an ongoing execution.

        Args:
            execution_id: Execution ID

        Returns:
            True if cancelled
        """
        context = self._executions.get(execution_id)
        if not context:
            raise ValueError(f"Execution {execution_id} not found")

        if context.status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        ]:
            raise ValueError(
                f"Cannot cancel execution in {context.status.value} status"
            )

        context.status = ExecutionStatus.CANCELLED
        context.completed_at = datetime.now(timezone.utc)
        logger.info(f"Cancelled execution {execution_id}")
        return True

    def reset_daily_usage(self) -> None:
        """Reset daily usage counters for all wallets."""
        for tier in WalletTier:
            self._daily_usage[tier] = Decimal(0)
        logger.info("Reset daily usage counters")

    def get_daily_usage(self) -> dict[WalletTier, Decimal]:
        """Get current daily usage for all wallets.

        Returns:
            Daily usage by wallet tier
        """
        return self._daily_usage.copy()

    def set_wallet_active(self, tier: WalletTier, active: bool) -> None:
        """Set wallet active status.

        Args:
            tier: Wallet tier
            active: Whether wallet is active
        """
        if tier in self.wallets:
            self.wallets[tier].is_active = active
            logger.info(f"Wallet {tier.value} set to {'active' if active else 'inactive'}")


# Singleton instance
_executor: RebalanceExecutor | None = None


def get_rebalance_executor() -> RebalanceExecutor:
    """Get or create rebalance executor singleton."""
    global _executor
    if _executor is None:
        _executor = RebalanceExecutor()
    return _executor
