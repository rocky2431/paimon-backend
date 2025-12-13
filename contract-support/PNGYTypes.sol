// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title PNGYTypes
/// @notice 共享的枚举、结构体和常量定义
library PNGYTypes {
    // =============================================================================
    // Constants
    // =============================================================================
    
    uint256 constant PRECISION = 1e18;
    uint256 constant BASIS_POINTS = 10000;
    uint256 constant MIN_DEPOSIT = 500e18;
    
    // 赎回延迟
    uint256 constant STANDARD_REDEMPTION_DELAY = 7 days;
    uint256 constant EMERGENCY_REDEMPTION_DELAY = 1 days;
    uint256 constant SCHEDULED_ADVANCE_DAYS = 15 days;
    
    // 费用相关
    uint256 constant BASE_REDEMPTION_FEE = 10;      // 0.1%
    uint256 constant MAX_REDEMPTION_FEE = 50;       // 0.5%
    uint256 constant EMERGENCY_FEE_PREMIUM = 100;   // 1%
    uint256 constant MANAGEMENT_FEE_BPS = 50;       // 0.5%
    uint256 constant PERFORMANCE_FEE_BPS = 1000;    // 10%
    uint256 constant SECONDS_PER_YEAR = 365 days;
    
    // 流动性阈值
    uint256 constant LOW_LIQUIDITY_THRESHOLD = 1500;      // 15%
    uint256 constant CRITICAL_LIQUIDITY_THRESHOLD = 1000; // 10%
    
    // 赎回审批阈值
    uint256 constant EMERGENCY_APPROVAL_AMOUNT = 30_000e18;   // 3万U
    uint256 constant EMERGENCY_APPROVAL_L1_RATIO = 1000;      // 10%
    uint256 constant STANDARD_APPROVAL_AMOUNT = 100_000e18;   // 10万U
    uint256 constant STANDARD_APPROVAL_LIQUIDITY_RATIO = 500; // 5%
    uint256 constant LARGE_REDEMPTION_THRESHOLD = 200;        // 2%
    
    // 层级默认配置
    uint256 constant DEFAULT_LAYER1_RATIO = 1000;  // 10%
    uint256 constant DEFAULT_LAYER2_RATIO = 3000;  // 30%
    uint256 constant DEFAULT_LAYER3_RATIO = 6000;  // 60%
    uint256 constant MIN_LAYER1_RATIO = 500;       // 5%
    uint256 constant MAX_LAYER3_RATIO = 8000;      // 80%
    
    // 其他
    uint256 constant CACHE_DURATION = 5 minutes;
    uint256 constant MAX_SLIPPAGE_BPS = 200;       // 2%

    // =============================================================================
    // Enums
    // =============================================================================
    
    enum LiquidityTier {
        TIER_1_CASH,  // Layer1: 现金 + 即时生息
        TIER_2_MMF,   // Layer2: 货币市场基金类
        TIER_3_HYD    // Layer3: 高收益资产
    }
    
    enum PurchaseMethod {
        OTC,    // 场外交易
        SWAP,   // DEX 交换
        AUTO    // 自动选择
    }
    
    enum RedemptionStatus {
        PENDING,           // 等待结算
        PENDING_APPROVAL,  // 等待审批
        APPROVED,          // 已审批
        SETTLED,           // 已结算
        CANCELLED          // 已取消
    }
    
    enum RedemptionChannel {
        STANDARD,   // 标准通道 (T+7)
        EMERGENCY,  // 紧急通道 (T+1)
        SCHEDULED   // 大额定期通道
    }

    // =============================================================================
    // Structs
    // =============================================================================
    
    struct RedemptionRequest {
        uint256 requestId;
        address owner;
        address receiver;
        uint256 shares;
        uint256 grossAmount;
        uint256 lockedNav;
        uint256 estimatedFee;
        uint256 requestTime;
        uint256 settlementTime;
        RedemptionStatus status;
        RedemptionChannel channel;
        bool requiresApproval;
        uint256 windowId;
    }
    
    struct RedemptionPreview {
        uint256 grossAmount;
        uint256 fee;
        uint256 netAmount;
        RedemptionChannel channel;
        bool requiresApproval;
        uint256 settlementDelay;
        uint256 estimatedSettlementTime;
        uint256 windowId;
        bool canProcess;
        string channelReason;
    }
    
    struct AssetConfig {
        address tokenAddress;
        LiquidityTier tier;
        uint256 targetAllocation;
        bool isActive;
        address purchaseAdapter;
        uint8 decimals;
        PurchaseMethod purchaseMethod;
        uint256 maxSlippage;
        uint256 minPurchaseAmount;
        uint256 subscriptionStart;
        uint256 subscriptionEnd;
    }
    
    struct LayerConfig {
        uint256 targetRatio;
        uint256 minRatio;
        uint256 maxRatio;
    }
    
    struct BufferPoolInfo {
        uint256 cashBalance;
        uint256 yieldBalance;
        uint256 totalBuffer;
        uint256 targetBuffer;
        uint256 bufferRatio;
        bool needsRebalance;
    }
    
    struct VaultState {
        uint256 totalAssets;
        uint256 totalSupply;
        uint256 sharePrice;
        uint256 layer1Liquidity;
        uint256 layer2Liquidity;
        uint256 layer3Value;
        uint256 totalRedemptionLiability;
        uint256 totalLockedShares;
        bool emergencyMode;
    }
    
    struct FeeInfo {
        uint256 pendingManagementFee;
        uint256 pendingPerformanceFee;
        uint256 totalPending;
        uint256 lastCollectionTime;
        uint256 layer3HighWaterMark;
    }
    
    struct RedemptionFeeInfo {
        uint256 totalFees;
        uint256 withdrawableFees;
        uint256 alreadyWithdrawn;
    }
}