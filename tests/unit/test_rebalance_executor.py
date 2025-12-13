"""Tests for rebalance execution service."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.rebalance import (
    ExecutionConfig,
    ExecutionStatus,
    LiquidityTier,
    RebalanceAction,
    RebalanceExecutor,
    RebalancePlan,
    RebalancePlanStep,
    RebalanceStatus,
    RetryPolicy,
    SimulationResult,
    TierDeviation,
    TierState,
    TransactionStatus,
    WalletConfig,
    WalletTier,
)
from datetime import datetime, timezone


class TestWalletSelection:
    """Tests for wallet selection logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = RebalanceExecutor()

    def test_select_hot_wallet_for_small_amount(self):
        """Test selecting hot wallet for small transactions."""
        wallet = self.executor.select_wallet(Decimal("5000"))

        assert wallet is not None
        assert wallet.tier == WalletTier.HOT

    def test_select_warm_wallet_for_medium_amount(self):
        """Test selecting warm wallet for medium transactions."""
        wallet = self.executor.select_wallet(Decimal("50000"))

        assert wallet is not None
        assert wallet.tier == WalletTier.WARM

    def test_select_cold_wallet_for_large_amount(self):
        """Test selecting cold wallet for large transactions."""
        wallet = self.executor.select_wallet(Decimal("500000"))

        assert wallet is not None
        assert wallet.tier == WalletTier.COLD

    def test_no_wallet_for_excessive_amount(self):
        """Test no wallet available for excessive amounts."""
        wallet = self.executor.select_wallet(Decimal("50000000"))

        assert wallet is None

    def test_wallet_daily_limit(self):
        """Test daily limit enforcement."""
        # Use up hot wallet daily limit
        self.executor._daily_usage[WalletTier.HOT] = Decimal("95000")

        # Should skip hot wallet and use warm
        wallet = self.executor.select_wallet(Decimal("8000"))
        assert wallet is not None
        assert wallet.tier == WalletTier.WARM

    def test_inactive_wallet_skipped(self):
        """Test inactive wallet is skipped."""
        self.executor.set_wallet_active(WalletTier.HOT, False)

        wallet = self.executor.select_wallet(Decimal("5000"))
        assert wallet is not None
        assert wallet.tier == WalletTier.WARM


class TestSimulation:
    """Tests for transaction simulation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = RebalanceExecutor()

    @pytest.mark.asyncio
    async def test_default_simulation_succeeds(self):
        """Test default simulation returns success."""
        from app.services.rebalance import TransactionRequest

        request = TransactionRequest(
            step_id=1,
            from_address="0x" + "1" * 40,
            to_address="0x" + "a" * 40,
            data="0x1234",
            gas_limit=200000,
        )

        result = await self.executor.simulate_transaction(request)

        assert result.success is True
        assert result.gas_estimate > 0

    @pytest.mark.asyncio
    async def test_custom_simulator(self):
        """Test custom simulator function."""
        def custom_simulator(request):
            return SimulationResult(
                success=False,
                gas_estimate=0,
                error_message="Custom failure",
                simulated_at=datetime.now(timezone.utc),
            )

        executor = RebalanceExecutor(simulator=custom_simulator)

        from app.services.rebalance import TransactionRequest

        request = TransactionRequest(
            step_id=1,
            from_address="0x" + "1" * 40,
            to_address="0x" + "a" * 40,
            data="0x1234",
            gas_limit=200000,
        )

        result = await executor.simulate_transaction(request)

        assert result.success is False
        assert result.error_message == "Custom failure"


class TestTransactionSubmission:
    """Tests for transaction submission."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = RebalanceExecutor()

    @pytest.mark.asyncio
    async def test_default_submission_returns_hash(self):
        """Test default submission returns transaction hash."""
        from app.services.rebalance import TransactionRequest

        request = TransactionRequest(
            step_id=1,
            from_address="0x" + "1" * 40,
            to_address="0x" + "a" * 40,
            data="0x1234",
            gas_limit=200000,
        )

        tx_hash = await self.executor.submit_transaction(request, WalletTier.HOT)

        assert tx_hash is not None
        assert tx_hash.startswith("0x")
        assert len(tx_hash) == 66  # 0x + 64 hex chars

    @pytest.mark.asyncio
    async def test_custom_submitter(self):
        """Test custom submitter function."""
        def custom_submitter(request, tier):
            return "0x" + "abcd" * 16

        executor = RebalanceExecutor(submitter=custom_submitter)

        from app.services.rebalance import TransactionRequest

        request = TransactionRequest(
            step_id=1,
            from_address="0x" + "1" * 40,
            to_address="0x" + "a" * 40,
            data="0x1234",
            gas_limit=200000,
        )

        tx_hash = await executor.submit_transaction(request, WalletTier.HOT)

        assert tx_hash == "0x" + "abcd" * 16


class TestPlanExecution:
    """Tests for plan execution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = RebalanceExecutor()

    def _create_test_plan(self, num_steps: int = 2) -> RebalancePlan:
        """Create a test plan with approved status."""
        steps = [
            RebalancePlanStep(
                step_id=i + 1,
                action=RebalanceAction.SWAP,
                from_tier=LiquidityTier.L3,
                to_tier=LiquidityTier.L1,
                amount=Decimal("5000"),
                priority=1,
            )
            for i in range(num_steps)
        ]

        return RebalancePlan(
            plan_id="RBL-TEST1234",
            status=RebalanceStatus.APPROVED,
            trigger_reason="Test",
            initial_state=[
                TierState(
                    tier=LiquidityTier.L1,
                    value=Decimal("10000"),
                    ratio=Decimal("0.10"),
                    assets=[],
                ),
                TierState(
                    tier=LiquidityTier.L3,
                    value=Decimal("90000"),
                    ratio=Decimal("0.90"),
                    assets=[],
                ),
            ],
            deviations=[],
            steps=steps,
            total_amount=Decimal(str(5000 * num_steps)),
            created_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_execute_plan_success(self):
        """Test successful plan execution."""
        plan = self._create_test_plan(num_steps=2)

        result = await self.executor.execute_plan(plan)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.completed_steps == 2
        assert result.total_steps == 2
        assert len(result.transactions) == 2
        assert all(
            tx.status == TransactionStatus.CONFIRMED
            for tx in result.transactions
        )

    @pytest.mark.asyncio
    async def test_execute_plan_not_approved(self):
        """Test execution fails for non-approved plan."""
        plan = self._create_test_plan()
        plan.status = RebalanceStatus.DRAFT

        with pytest.raises(ValueError, match="not approved"):
            await self.executor.execute_plan(plan)

    @pytest.mark.asyncio
    async def test_execute_plan_tracks_gas(self):
        """Test execution tracks gas usage."""
        plan = self._create_test_plan(num_steps=3)

        result = await self.executor.execute_plan(plan)

        assert result.total_gas_used > 0

    @pytest.mark.asyncio
    async def test_execute_plan_tracks_value(self):
        """Test execution tracks value moved."""
        plan = self._create_test_plan(num_steps=2)

        result = await self.executor.execute_plan(plan)

        assert result.total_value_moved == Decimal("10000")  # 5000 * 2

    @pytest.mark.asyncio
    async def test_execute_plan_calculates_duration(self):
        """Test execution calculates duration."""
        plan = self._create_test_plan()

        result = await self.executor.execute_plan(plan)

        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0


class TestRetryLogic:
    """Tests for transaction retry logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.call_count = 0

    @pytest.mark.asyncio
    async def test_retry_on_simulation_failure(self):
        """Test retry when simulation fails then succeeds."""
        self.call_count = 0

        def flaky_simulator(request):
            self.call_count += 1
            if self.call_count < 2:
                return SimulationResult(
                    success=False,
                    error_message="Temporary failure",
                    simulated_at=datetime.now(timezone.utc),
                )
            return SimulationResult(
                success=True,
                gas_estimate=200000,
                simulated_at=datetime.now(timezone.utc),
            )

        config = ExecutionConfig(
            retry_policy=RetryPolicy(
                max_retries=3,
                base_delay_seconds=0.01,
            )
        )
        executor = RebalanceExecutor(config=config, simulator=flaky_simulator)

        plan = RebalancePlan(
            plan_id="RBL-RETRY123",
            status=RebalanceStatus.APPROVED,
            trigger_reason="Test retry",
            initial_state=[],
            deviations=[],
            steps=[
                RebalancePlanStep(
                    step_id=1,
                    action=RebalanceAction.SWAP,
                    from_tier=LiquidityTier.L2,
                    to_tier=LiquidityTier.L1,
                    amount=Decimal("5000"),
                    priority=1,
                )
            ],
            total_amount=Decimal("5000"),
            created_at=datetime.now(timezone.utc),
        )

        result = await executor.execute_plan(plan)

        assert result.status == ExecutionStatus.COMPLETED
        assert self.call_count >= 2

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test failure when max retries exceeded."""
        def always_fail_simulator(request):
            return SimulationResult(
                success=False,
                error_message="Always fails",
                simulated_at=datetime.now(timezone.utc),
            )

        config = ExecutionConfig(
            retry_policy=RetryPolicy(
                max_retries=2,
                base_delay_seconds=0.01,
            )
        )
        executor = RebalanceExecutor(config=config, simulator=always_fail_simulator)

        plan = RebalancePlan(
            plan_id="RBL-FAIL1234",
            status=RebalanceStatus.APPROVED,
            trigger_reason="Test failure",
            initial_state=[],
            deviations=[],
            steps=[
                RebalancePlanStep(
                    step_id=1,
                    action=RebalanceAction.SWAP,
                    from_tier=LiquidityTier.L2,
                    to_tier=LiquidityTier.L1,
                    amount=Decimal("5000"),
                    priority=1,
                )
            ],
            total_amount=Decimal("5000"),
            created_at=datetime.now(timezone.utc),
        )

        result = await executor.execute_plan(plan)

        # Should fail or be partially completed
        assert result.status in [
            ExecutionStatus.FAILED,
            ExecutionStatus.PARTIALLY_COMPLETED,
        ]


class TestExecutionManagement:
    """Tests for execution lifecycle management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = RebalanceExecutor()

    @pytest.mark.asyncio
    async def test_get_execution(self):
        """Test getting execution context."""
        plan = RebalancePlan(
            plan_id="RBL-GET12345",
            status=RebalanceStatus.APPROVED,
            trigger_reason="Test",
            initial_state=[],
            deviations=[],
            steps=[],
            total_amount=Decimal(0),
            created_at=datetime.now(timezone.utc),
        )

        result = await self.executor.execute_plan(plan)

        context = self.executor.get_execution(result.execution_id)
        assert context is not None
        assert context.plan_id == "RBL-GET12345"

    @pytest.mark.asyncio
    async def test_get_execution_not_found(self):
        """Test getting non-existent execution."""
        context = self.executor.get_execution("EXE-NOTFOUND")
        assert context is None

    @pytest.mark.asyncio
    async def test_get_execution_status(self):
        """Test getting execution status."""
        plan = RebalancePlan(
            plan_id="RBL-STATUS12",
            status=RebalanceStatus.APPROVED,
            trigger_reason="Test",
            initial_state=[],
            deviations=[],
            steps=[],
            total_amount=Decimal(0),
            created_at=datetime.now(timezone.utc),
        )

        result = await self.executor.execute_plan(plan)

        status = self.executor.get_execution_status(result.execution_id)
        assert status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cancel_execution_not_found(self):
        """Test cancelling non-existent execution."""
        with pytest.raises(ValueError, match="not found"):
            await self.executor.cancel_execution("EXE-NOTFOUND")

    @pytest.mark.asyncio
    async def test_cancel_completed_execution_fails(self):
        """Test cannot cancel completed execution."""
        plan = RebalancePlan(
            plan_id="RBL-CANCEL12",
            status=RebalanceStatus.APPROVED,
            trigger_reason="Test",
            initial_state=[],
            deviations=[],
            steps=[],
            total_amount=Decimal(0),
            created_at=datetime.now(timezone.utc),
        )

        result = await self.executor.execute_plan(plan)

        with pytest.raises(ValueError, match="Cannot cancel"):
            await self.executor.cancel_execution(result.execution_id)


class TestDailyUsage:
    """Tests for daily usage tracking."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = RebalanceExecutor()

    def test_reset_daily_usage(self):
        """Test resetting daily usage."""
        self.executor._daily_usage[WalletTier.HOT] = Decimal("50000")

        self.executor.reset_daily_usage()

        usage = self.executor.get_daily_usage()
        assert usage[WalletTier.HOT] == Decimal(0)
        assert usage[WalletTier.WARM] == Decimal(0)
        assert usage[WalletTier.COLD] == Decimal(0)

    def test_get_daily_usage(self):
        """Test getting daily usage."""
        self.executor._daily_usage[WalletTier.HOT] = Decimal("25000")
        self.executor._daily_usage[WalletTier.WARM] = Decimal("100000")

        usage = self.executor.get_daily_usage()

        assert usage[WalletTier.HOT] == Decimal("25000")
        assert usage[WalletTier.WARM] == Decimal("100000")

    @pytest.mark.asyncio
    async def test_execution_updates_daily_usage(self):
        """Test that execution updates daily usage."""
        plan = RebalancePlan(
            plan_id="RBL-USAGE123",
            status=RebalanceStatus.APPROVED,
            trigger_reason="Test",
            initial_state=[],
            deviations=[],
            steps=[
                RebalancePlanStep(
                    step_id=1,
                    action=RebalanceAction.SWAP,
                    from_tier=LiquidityTier.L2,
                    to_tier=LiquidityTier.L1,
                    amount=Decimal("5000"),
                    priority=1,
                )
            ],
            total_amount=Decimal("5000"),
            created_at=datetime.now(timezone.utc),
        )

        result = await self.executor.execute_plan(plan)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.completed_steps == 1

        usage = self.executor.get_daily_usage()
        assert usage[WalletTier.HOT] == Decimal("5000")


class TestCustomConfig:
    """Tests for custom configuration."""

    def test_custom_execution_config(self):
        """Test custom execution config."""
        config = ExecutionConfig(
            simulation_enabled=False,
            confirmation_blocks=5,
            parallel_execution=True,
            max_parallel_txs=5,
        )
        executor = RebalanceExecutor(config=config)

        assert executor.config.simulation_enabled is False
        assert executor.config.confirmation_blocks == 5
        assert executor.config.parallel_execution is True
        assert executor.config.max_parallel_txs == 5

    def test_custom_wallets(self):
        """Test custom wallet configuration."""
        custom_wallets = {
            WalletTier.HOT: WalletConfig(
                address="0x" + "a" * 40,
                tier=WalletTier.HOT,
                max_single_tx=Decimal("20000"),
                daily_limit=Decimal("200000"),
            ),
        }
        executor = RebalanceExecutor(wallets=custom_wallets)

        wallet = executor.select_wallet(Decimal("15000"))
        assert wallet is not None
        assert wallet.address == "0x" + "a" * 40

    def test_custom_retry_policy(self):
        """Test custom retry policy."""
        config = ExecutionConfig(
            retry_policy=RetryPolicy(
                max_retries=5,
                base_delay_seconds=1.0,
                exponential_backoff=False,
                max_delay_seconds=10.0,
            )
        )
        executor = RebalanceExecutor(config=config)

        assert executor.config.retry_policy.max_retries == 5
        assert executor.config.retry_policy.exponential_backoff is False
