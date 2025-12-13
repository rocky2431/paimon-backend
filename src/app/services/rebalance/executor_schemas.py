"""Rebalancing execution schemas."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WalletTier(str, Enum):
    """Wallet tier for transaction signing."""

    HOT = "HOT"  # Frequent operations, lower limits
    WARM = "WARM"  # Medium operations, medium limits
    COLD = "COLD"  # Rare operations, highest limits


class TransactionStatus(str, Enum):
    """Status of a transaction."""

    PENDING = "PENDING"
    SIMULATING = "SIMULATING"
    SIMULATION_FAILED = "SIMULATION_FAILED"
    BUILDING = "BUILDING"
    SIGNING = "SIGNING"
    SUBMITTED = "SUBMITTED"
    CONFIRMING = "CONFIRMING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    REVERTED = "REVERTED"


class ExecutionStatus(str, Enum):
    """Status of rebalance execution."""

    PENDING = "PENDING"
    SIMULATING = "SIMULATING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WalletConfig(BaseModel):
    """Configuration for a wallet."""

    address: str = Field(..., description="Wallet address")
    tier: WalletTier = Field(..., description="Wallet tier")
    max_single_tx: Decimal = Field(..., ge=0, description="Max single tx amount")
    daily_limit: Decimal = Field(..., ge=0, description="Daily transaction limit")
    is_active: bool = Field(default=True, description="Whether wallet is active")


class SimulationResult(BaseModel):
    """Result of eth_call simulation."""

    success: bool = Field(..., description="Whether simulation succeeded")
    gas_estimate: int = Field(default=0, ge=0, description="Estimated gas")
    return_data: str | None = Field(None, description="Returned data")
    error_message: str | None = Field(None, description="Error message if failed")
    simulated_at: datetime = Field(..., description="Simulation timestamp")


class TransactionRequest(BaseModel):
    """Request to build and submit a transaction."""

    step_id: int = Field(..., description="Rebalance step ID")
    from_address: str = Field(..., description="Sender address")
    to_address: str = Field(..., description="Target contract address")
    value: Decimal = Field(default=Decimal(0), description="ETH value to send")
    data: str = Field(..., description="Transaction data (hex)")
    gas_limit: int = Field(..., gt=0, description="Gas limit")
    gas_price: int | None = Field(None, description="Gas price in wei")
    max_fee_per_gas: int | None = Field(None, description="Max fee per gas (EIP-1559)")
    max_priority_fee: int | None = Field(
        None, description="Max priority fee (EIP-1559)"
    )
    nonce: int | None = Field(None, description="Nonce (auto if None)")


class TransactionRecord(BaseModel):
    """Record of a submitted transaction."""

    tx_id: str = Field(..., description="Internal transaction ID")
    step_id: int = Field(..., description="Rebalance step ID")
    tx_hash: str | None = Field(None, description="On-chain transaction hash")
    status: TransactionStatus = Field(..., description="Transaction status")
    wallet_tier: WalletTier = Field(..., description="Wallet tier used")
    from_address: str = Field(..., description="Sender address")
    to_address: str = Field(..., description="Target address")
    value: Decimal = Field(..., description="ETH value sent")
    gas_used: int | None = Field(None, description="Gas used")
    gas_price: int | None = Field(None, description="Gas price used")
    block_number: int | None = Field(None, description="Block number")
    error_message: str | None = Field(None, description="Error if failed")
    retry_count: int = Field(default=0, description="Number of retries")
    created_at: datetime = Field(..., description="Creation timestamp")
    submitted_at: datetime | None = Field(None, description="Submission timestamp")
    confirmed_at: datetime | None = Field(None, description="Confirmation timestamp")


class ExecutionContext(BaseModel):
    """Context for rebalance execution."""

    plan_id: str = Field(..., description="Rebalance plan ID")
    execution_id: str = Field(..., description="Execution ID")
    status: ExecutionStatus = Field(..., description="Execution status")
    current_step: int = Field(default=0, description="Current step index")
    total_steps: int = Field(..., description="Total number of steps")
    transactions: list[TransactionRecord] = Field(
        default_factory=list, description="Transaction records"
    )
    started_at: datetime = Field(..., description="Start timestamp")
    completed_at: datetime | None = Field(None, description="Completion timestamp")
    error_message: str | None = Field(None, description="Error if failed")


class ExecutionResult(BaseModel):
    """Result of rebalance execution."""

    execution_id: str = Field(..., description="Execution ID")
    plan_id: str = Field(..., description="Rebalance plan ID")
    status: ExecutionStatus = Field(..., description="Final status")
    completed_steps: int = Field(..., description="Number of completed steps")
    total_steps: int = Field(..., description="Total steps")
    transactions: list[TransactionRecord] = Field(..., description="All transactions")
    total_gas_used: int = Field(default=0, description="Total gas used")
    total_value_moved: Decimal = Field(
        default=Decimal(0), description="Total value moved"
    )
    started_at: datetime = Field(..., description="Start timestamp")
    completed_at: datetime | None = Field(None, description="Completion timestamp")
    duration_seconds: float | None = Field(None, description="Execution duration")
    error_message: str | None = Field(None, description="Error if failed")


class RetryPolicy(BaseModel):
    """Policy for transaction retries."""

    max_retries: int = Field(default=3, ge=0, le=10, description="Max retry attempts")
    base_delay_seconds: float = Field(
        default=5.0, ge=0, description="Base delay between retries"
    )
    exponential_backoff: bool = Field(
        default=True, description="Use exponential backoff"
    )
    max_delay_seconds: float = Field(
        default=60.0, ge=0, description="Max delay between retries"
    )
    retry_on_statuses: list[TransactionStatus] = Field(
        default_factory=lambda: [
            TransactionStatus.FAILED,
            TransactionStatus.SIMULATION_FAILED,
        ],
        description="Statuses that trigger retry",
    )


class ExecutionConfig(BaseModel):
    """Configuration for rebalance execution."""

    simulation_enabled: bool = Field(
        default=True, description="Enable eth_call simulation"
    )
    confirmation_blocks: int = Field(
        default=3, ge=1, le=100, description="Blocks to wait for confirmation"
    )
    gas_price_multiplier: Decimal = Field(
        default=Decimal("1.1"),
        ge=Decimal("1.0"),
        le=Decimal("2.0"),
        description="Gas price safety multiplier",
    )
    retry_policy: RetryPolicy = Field(
        default_factory=RetryPolicy, description="Retry policy"
    )
    parallel_execution: bool = Field(
        default=False, description="Execute independent steps in parallel"
    )
    max_parallel_txs: int = Field(
        default=3, ge=1, le=10, description="Max parallel transactions"
    )
