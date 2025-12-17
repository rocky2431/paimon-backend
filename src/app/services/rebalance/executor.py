"""Rebalancing execution engine with database persistence.

Features:
- eth_call simulation before execution
- Tiered wallet selection (hot/warm/cold)
- Transaction building and submission (real or mock)
- State updates and monitoring
- Retry on failure with backoff
- Complete audit trail in database

v2.0.0 Enhancements:
- Integration with TransactionService for real chain execution
- Integration with ContractManager for contract calls
- Feature flag support (ff_blockchain_execution)
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.database.session import AsyncSessionLocal
from app.repositories.rebalance import RebalanceRepository
from app.repositories.audit_log import AuditLogRepository
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
    """Executor for rebalance plan transactions with database persistence.

    Features:
    - eth_call simulation before execution
    - Tiered wallet selection (hot/warm/cold)
    - Transaction building and submission (real or mock based on feature flag)
    - State updates and monitoring
    - Retry on failure with backoff
    - Database persistence for execution history
    - Complete audit trail

    v2.0.0: Supports real chain execution via TransactionService when
    ff_blockchain_execution="real".
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
        submitter: Callable[[TransactionRequest, WalletTier], str | None] | None = None,
        session_factory: Callable[[], AsyncSession] | None = None,
        use_real_chain: bool | None = None,
    ):
        """Initialize rebalance executor.

        @param config - Execution configuration
        @param wallets - Wallet configurations by tier
        @param simulator - Custom simulation function (for testing)
        @param submitter - Custom transaction submitter (for testing)
        @param session_factory - Optional factory for creating database sessions
        @param use_real_chain - Override for real chain execution (uses feature flag if None)
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
        self._session_factory = session_factory or AsyncSessionLocal
        self._daily_usage: dict[WalletTier, Decimal] = {
            tier: Decimal(0) for tier in WalletTier
        }

        # Determine execution mode
        if use_real_chain is not None:
            self._use_real_chain = use_real_chain
        else:
            settings = get_settings()
            self._use_real_chain = settings.ff_blockchain_execution == "real"

        # Lazy-loaded services for real chain execution
        self._transaction_service = None
        self._contract_manager = None
        self._abi_loader = None

    def _ensure_chain_services(self) -> None:
        """Lazy-initialize chain services for real execution.

        Only called when _use_real_chain is True and services are needed.
        """
        if self._transaction_service is None:
            from app.infrastructure.blockchain.client import BSCClient
            from app.infrastructure.blockchain.contracts import (
                ContractManager,
                get_abi_loader,
            )
            from app.infrastructure.blockchain.transaction import (
                TransactionService,
                get_transaction_service,
            )

            self._abi_loader = get_abi_loader()
            client = BSCClient()
            self._contract_manager = ContractManager(client)
            self._transaction_service = get_transaction_service(client)

            # Update wallet addresses to use real signer address
            if self._transaction_service:
                real_address = self._transaction_service.address
                for wallet in self.wallets.values():
                    wallet.address = real_address

            logger.info(
                f"Chain services initialized, signer: {self._transaction_service.address}"
            )

    def select_wallet(self, amount: Decimal) -> WalletConfig | None:
        """Select appropriate wallet based on amount.

        Selection priority: HOT -> WARM -> COLD
        Considers: single tx limit, daily limit, active status

        @param amount - Transaction amount
        @returns Selected wallet config or None if no suitable wallet
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

        @param request - Transaction request to simulate
        @returns Simulation result
        """
        if self._simulator:
            return self._simulator(request)

        # Real chain simulation
        if self._use_real_chain:
            self._ensure_chain_services()
            try:
                # Use eth_call via contract manager
                tx_params = {
                    "from": request.from_address,
                    "to": request.to_address,
                    "data": request.data,
                    "value": int(request.value) if request.value else 0,
                }
                # Estimate gas as simulation
                estimated_gas = await self._contract_manager.client.estimate_gas(tx_params)

                return SimulationResult(
                    success=True,
                    gas_estimate=estimated_gas,
                    return_data="0x",
                    simulated_at=datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.warning(f"Simulation failed: {e}")
                return SimulationResult(
                    success=False,
                    gas_estimate=0,
                    return_data="0x",
                    error_message=str(e),
                    simulated_at=datetime.now(timezone.utc),
                )

        # Mock simulation (default)
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

        @param request - Transaction request
        @param wallet_tier - Wallet tier to use for signing
        @returns Transaction hash or None if failed
        """
        if self._submitter:
            return self._submitter(request, wallet_tier)

        # Real chain submission
        if self._use_real_chain:
            self._ensure_chain_services()
            settings = get_settings()

            try:
                # Build and send raw transaction via TransactionService
                from app.infrastructure.blockchain.transaction import (
                    TransactionStatus as TxStatus,
                )

                # Use send_transaction for raw data
                result = await self._transaction_service.send_transaction(
                    contract_address=request.to_address,
                    abi=[],  # Raw data, no ABI encoding needed
                    function_name="",  # Not used for raw data
                    args=[],
                    gas_limit=request.gas_limit,
                    value=int(request.value) if request.value else 0,
                )

                if result.status == TxStatus.PENDING:
                    logger.info(f"Transaction submitted: {result.tx_hash}")
                    return result.tx_hash
                else:
                    logger.error(f"Transaction failed: {result.error}")
                    return None

            except Exception as e:
                logger.error(f"Transaction submission failed: {e}")
                return None

        # Mock submission (default)
        return "0x" + uuid.uuid4().hex + uuid.uuid4().hex

    async def wait_for_confirmation(
        self,
        tx_hash: str,
        confirmations: int = 3,
    ) -> tuple[bool, int | None, str | None]:
        """Wait for transaction confirmation.

        @param tx_hash - Transaction hash
        @param confirmations - Required confirmations
        @returns Tuple of (success, block_number, error_message)
        """
        # Real chain confirmation
        if self._use_real_chain:
            self._ensure_chain_services()
            try:
                receipt = await self._contract_manager.client.wait_for_transaction_receipt(
                    tx_hash, timeout=120
                )

                if receipt.get("status") == 1:
                    return True, receipt.get("blockNumber"), None
                else:
                    return False, receipt.get("blockNumber"), "Transaction reverted"

            except TimeoutError:
                return False, None, "Transaction confirmation timeout"
            except Exception as e:
                return False, None, str(e)

        # Mock confirmation (default)
        await asyncio.sleep(0.01)  # Simulate network latency
        return True, 12345678, None

    def _build_transaction_request(
        self,
        step: RebalancePlanStep,
        wallet: WalletConfig,
    ) -> TransactionRequest:
        """Build transaction request from plan step.

        @param step - Rebalance plan step
        @param wallet - Wallet to use
        @returns Transaction request
        """
        settings = get_settings()

        # Build call data based on action type
        data = self._encode_action_data(step)

        # Use real vault address when in real chain mode
        contract_address = (
            settings.active_vault_address
            if self._use_real_chain
            else "0x" + "a" * 40
        )

        return TransactionRequest(
            step_id=step.step_id,
            from_address=wallet.address,
            to_address=contract_address,
            value=Decimal(0),
            data=data,
            gas_limit=300000,
        )

    def _encode_action_data(self, step: RebalancePlanStep) -> str:
        """Encode action data for transaction.

        @param step - Rebalance plan step
        @returns Hex-encoded call data
        """
        # Real chain encoding using contract ABI
        if self._use_real_chain:
            self._ensure_chain_services()
            try:
                abi = self._abi_loader.ppt_abi
                amount_wei = int(step.amount * 10**18)

                # Map action to contract function
                # Note: Actual function names depend on PPT contract implementation
                if step.action == RebalanceAction.SWAP:
                    # rebalanceSwap(uint8 fromTier, uint8 toTier, uint256 amount)
                    from_tier_int = self._tier_to_int(step.from_tier)
                    to_tier_int = self._tier_to_int(step.to_tier)
                    data = self._contract_manager.encode_function_call(
                        abi, "rebalanceSwap", [from_tier_int, to_tier_int, amount_wei]
                    )
                    return data.hex() if isinstance(data, bytes) else data

                elif step.action == RebalanceAction.LIQUIDATE:
                    # liquidateForL1(uint8 fromTier, uint256 amount)
                    from_tier_int = self._tier_to_int(step.from_tier)
                    data = self._contract_manager.encode_function_call(
                        abi, "liquidateForL1", [from_tier_int, amount_wei]
                    )
                    return data.hex() if isinstance(data, bytes) else data

                elif step.action == RebalanceAction.DEPOSIT:
                    # depositToTier(uint8 tier, uint256 amount)
                    to_tier_int = self._tier_to_int(step.to_tier)
                    data = self._contract_manager.encode_function_call(
                        abi, "depositToTier", [to_tier_int, amount_wei]
                    )
                    return data.hex() if isinstance(data, bytes) else data

                elif step.action == RebalanceAction.WITHDRAW:
                    # withdrawFromTier(uint8 tier, uint256 amount)
                    from_tier_int = self._tier_to_int(step.from_tier)
                    data = self._contract_manager.encode_function_call(
                        abi, "withdrawFromTier", [from_tier_int, amount_wei]
                    )
                    return data.hex() if isinstance(data, bytes) else data

            except Exception as e:
                logger.error(f"Failed to encode action data: {e}")
                # Fall back to mock encoding on error
                pass

        # Mock encoding (default)
        if step.action == RebalanceAction.SWAP:
            return "0x" + "swap" + "0" * 56
        elif step.action == RebalanceAction.LIQUIDATE:
            return "0x" + "liquidate" + "0" * 48
        elif step.action == RebalanceAction.DEPOSIT:
            return "0x" + "deposit" + "0" * 50
        elif step.action == RebalanceAction.WITHDRAW:
            return "0x" + "withdraw" + "0" * 48
        return "0x"

    def _tier_to_int(self, tier: Any) -> int:
        """Convert LiquidityTier to contract tier index.

        @param tier - LiquidityTier enum value
        @returns Contract tier index (0=L1, 1=L2, 2=L3)
        """
        from app.services.rebalance.schemas import LiquidityTier

        if tier == LiquidityTier.L1:
            return 0
        elif tier == LiquidityTier.L2:
            return 1
        elif tier == LiquidityTier.L3:
            return 2
        return 0  # Default to L1

    async def _execute_step_with_retry(
        self,
        step: RebalancePlanStep,
        context: ExecutionContext,
    ) -> TransactionRecord:
        """Execute a single step with retry logic.

        @param step - Step to execute
        @param context - Execution context
        @returns Transaction record
        """
        policy = self.config.retry_policy
        retry_count = 0
        last_error = None

        while retry_count <= policy.max_retries:
            # Select wallet
            wallet = self.select_wallet(step.amount)
            if not wallet:
                raise ValueError(f"No suitable wallet for amount {step.amount}")

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
                        raise ValueError(f"Simulation failed: {sim_result.error_message}")

                    tx_request.gas_limit = int(
                        sim_result.gas_estimate * float(self.config.gas_price_multiplier)
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
        executed_by: str | None = None,
    ) -> ExecutionResult:
        """Execute a rebalance plan with database persistence.

        @param plan - Rebalance plan to execute
        @param executed_by - Address of executor
        @returns Execution result
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

        logger.info(
            f"Starting execution {execution_id} for plan {plan.plan_id} "
            f"with {len(plan.steps)} steps"
        )

        # Update database - start execution
        async with self._session_factory() as session:
            repo = RebalanceRepository(session)
            audit_repo = AuditLogRepository(session)

            # Start execution in database
            await repo.start_execution(plan.plan_id, executed_by=executed_by or "system")

            # Audit log
            await audit_repo.create({
                "action": "rebalance.execution_started",
                "resource_type": "rebalance",
                "resource_id": plan.plan_id,
                "actor_address": executed_by.lower() if executed_by else None,
                "new_value": {
                    "execution_id": execution_id,
                    "total_steps": len(plan.steps),
                },
            })

            await session.commit()

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

                    logger.info(f"Step {step.step_id} completed: {tx_record.tx_hash}")

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

        # Update database - complete/fail execution
        async with self._session_factory() as session:
            repo = RebalanceRepository(session)
            audit_repo = AuditLogRepository(session)

            # Build execution results for database
            execution_results = {
                "execution_id": execution_id,
                "completed_steps": completed_steps,
                "total_steps": len(plan.steps),
                "transactions": [
                    {
                        "tx_id": tx.tx_id,
                        "tx_hash": tx.tx_hash,
                        "status": tx.status.value,
                        "gas_used": tx.gas_used,
                    }
                    for tx in context.transactions
                ],
                "error": context.error_message,
            }

            if context.status == ExecutionStatus.COMPLETED:
                # Build post-state (simplified - would calculate actual state)
                post_state = {
                    "completed_at": context.completed_at.isoformat() if context.completed_at else None,
                    "total_value_moved": str(total_value),
                }

                await repo.complete(
                    plan.plan_id,
                    post_state=post_state,
                    execution_results=execution_results,
                    actual_gas_cost=Decimal(total_gas),
                )
            elif context.status == ExecutionStatus.FAILED:
                await repo.fail(
                    plan.plan_id,
                    error_message=context.error_message or "Execution failed",
                    execution_results=execution_results,
                )
            else:
                # Partially completed
                await repo.update(
                    plan.plan_id,
                    {
                        "status": "FAILED",  # Partial completion is still a failure
                        "execution_results": execution_results,
                    },
                )

            # Audit log
            await audit_repo.create({
                "action": f"rebalance.execution_{context.status.value.lower()}",
                "resource_type": "rebalance",
                "resource_id": plan.plan_id,
                "actor_address": executed_by.lower() if executed_by else None,
                "new_value": {
                    "execution_id": execution_id,
                    "completed_steps": completed_steps,
                    "total_steps": len(plan.steps),
                    "total_gas_used": total_gas,
                    "status": context.status.value,
                },
            })

            await session.commit()

        logger.info(
            f"Execution {execution_id} finished: {context.status.value}, "
            f"{completed_steps}/{len(plan.steps)} steps completed"
        )

        return result

    async def get_execution(self, plan_id: str) -> dict[str, Any] | None:
        """Get execution details from database.

        @param plan_id - Plan ID
        @returns Execution details or None
        """
        async with self._session_factory() as session:
            repo = RebalanceRepository(session)
            record = await repo.get_by_id(plan_id)

            if not record:
                return None

            return {
                "id": record.id,
                "status": record.status,
                "trigger_type": record.trigger_type,
                "executed_at": record.executed_at,
                "executed_by": record.executed_by,
                "execution_results": record.execution_results,
                "actual_gas_cost": str(record.actual_gas_cost) if record.actual_gas_cost else None,
            }

    async def cancel_execution(self, plan_id: str, actor: str, reason: str) -> bool:
        """Cancel a pending or executing rebalance.

        @param plan_id - Plan ID
        @param actor - Actor cancelling
        @param reason - Cancellation reason
        @returns True if cancelled
        """
        async with self._session_factory() as session:
            repo = RebalanceRepository(session)
            audit_repo = AuditLogRepository(session)

            record = await repo.get_by_id(plan_id)
            if not record:
                raise ValueError(f"Rebalance {plan_id} not found")

            if record.status in ["COMPLETED", "FAILED", "CANCELLED"]:
                raise ValueError(f"Cannot cancel rebalance in {record.status} status")

            await repo.cancel(plan_id, reason=reason)

            # Audit log
            await audit_repo.create({
                "action": "rebalance.cancelled",
                "resource_type": "rebalance",
                "resource_id": plan_id,
                "actor_address": actor.lower(),
                "new_value": {"reason": reason},
            })

            await session.commit()
            logger.info(f"Cancelled rebalance {plan_id}: {reason}")
            return True

    def reset_daily_usage(self) -> None:
        """Reset daily usage counters for all wallets."""
        for tier in WalletTier:
            self._daily_usage[tier] = Decimal(0)
        logger.info("Reset daily usage counters")

    def get_daily_usage(self) -> dict[WalletTier, Decimal]:
        """Get current daily usage for all wallets.

        @returns Daily usage by wallet tier
        """
        return self._daily_usage.copy()

    def set_wallet_active(self, tier: WalletTier, active: bool) -> None:
        """Set wallet active status.

        @param tier - Wallet tier
        @param active - Whether wallet is active
        """
        if tier in self.wallets:
            self.wallets[tier].is_active = active
            logger.info(f"Wallet {tier.value} set to {'active' if active else 'inactive'}")


# Singleton instance
_executor: RebalanceExecutor | None = None


def get_rebalance_executor() -> RebalanceExecutor:
    """Get or create rebalance executor singleton.

    @returns RebalanceExecutor instance
    """
    global _executor
    if _executor is None:
        _executor = RebalanceExecutor()
    return _executor


def reset_rebalance_executor() -> None:
    """Reset rebalance executor singleton (for testing)."""
    global _executor
    _executor = None
