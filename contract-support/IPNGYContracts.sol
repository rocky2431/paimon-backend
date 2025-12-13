// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {PNGYTypes} from "./PNGYTypes.sol";

/// @title IPNGYVault
/// @notice 主 Vault 合约接口（自定义函数，ERC4626 标准函数使用 IERC4626）
interface IPNGYVault {
    // ========== 自定义查询函数 ==========
    function sharePrice() external view returns (uint256);
    function effectiveSupply() external view returns (uint256);

    // ========== 状态查询 ==========
    function totalRedemptionLiability() external view returns (uint256);
    function totalLockedShares() external view returns (uint256);
    function withdrawableRedemptionFees() external view returns (uint256);
    function emergencyMode() external view returns (bool);
    function lockedSharesOf(address owner) external view returns (uint256);
    function getVaultState() external view returns (PNGYTypes.VaultState memory);
    
    // ========== 流动性查询 ==========
    function getLayer1Liquidity() external view returns (uint256);
    function getLayer1Cash() external view returns (uint256);
    function getLayer1YieldAssets() external view returns (uint256);
    function getLayer2Liquidity() external view returns (uint256);
    function getLayer3Value() external view returns (uint256);
    function getAvailableLiquidity() external view returns (uint256);
    
    // ========== 供 OPERATOR 角色调用（RedemptionManager / AssetController）==========
    function lockShares(address owner, uint256 shares) external;
    function unlockShares(address owner, uint256 shares) external;
    function burnLockedShares(address owner, uint256 shares) external;
    function addRedemptionLiability(uint256 amount) external;
    function removeRedemptionLiability(uint256 amount) external;
    function addRedemptionFee(uint256 fee) external;
    function reduceRedemptionFee(uint256 fee) external;
    function transferAssetTo(address to, uint256 amount) external;
    function getAssetBalance(address token) external view returns (uint256);
    function approveAsset(address token, address spender, uint256 amount) external;
}

/// @title IRedemptionManager
/// @notice 赎回管理合约接口 - 用户直接调用
interface IRedemptionManager {
    // ========== 赎回请求（用户直接调用）==========
    function requestRedemption(uint256 shares, address receiver) external returns (uint256 requestId);
    function requestEmergencyRedemption(uint256 shares, address receiver) external returns (uint256 requestId);
    function cancelRedemption(uint256 requestId) external;
    
    // ========== 结算 ==========
    function settleRedemption(uint256 requestId) external;
    function settleScheduledRedemption(uint256 requestId) external;
    function batchSettleRedemptions(uint256 maxCount) external returns (uint256 settledCount);
    
    // ========== 审批（VIP_APPROVER 调用）==========
    function approveRedemption(uint256 requestId) external;
    function rejectRedemption(uint256 requestId, string calldata reason) external;
    
    // ========== 查询（用户直接调用）==========
    function previewRedemption(uint256 shares) external view returns (PNGYTypes.RedemptionPreview memory);
    function previewRedemptionFor(address owner, uint256 shares) external view returns (PNGYTypes.RedemptionPreview memory);
    function previewEmergencyRedemption(uint256 shares) external view returns (PNGYTypes.RedemptionPreview memory);
    function getRedemptionRequest(uint256 requestId) external view returns (PNGYTypes.RedemptionRequest memory);
    function getUserRedemptions(address user) external view returns (uint256[] memory);
    function getPendingApprovals() external view returns (uint256[] memory);
    function getTotalPendingApprovalAmount() external view returns (uint256);
    function getRequestCount() external view returns (uint256);
}

/// @title IAssetController
/// @notice 资产控制合约接口 - REBALANCER 角色调用
interface IAssetController {
    // ========== 资产配置（ADMIN 调用）==========
    function addAsset(
        address token,
        PNGYTypes.LiquidityTier tier,
        uint256 targetAllocation,
        address purchaseAdapter
    ) external;
    function addAssetSimple(
        address token,
        PNGYTypes.LiquidityTier tier,
        uint256 targetAllocation
    ) external;
    function removeAsset(address token) external;
    function updateAssetAllocation(address token, uint256 newAllocation) external;
    function setAssetAdapter(address token, address newAdapter) external;
    function setAssetPurchaseConfig(
        address token,
        PNGYTypes.PurchaseMethod method,
        uint256 maxSlippage,
        uint256 minPurchaseAmount,
        uint256 subscriptionStart,
        uint256 subscriptionEnd
    ) external;
    
    // ========== 资产操作（REBALANCER 调用）==========
    function allocateToLayer(PNGYTypes.LiquidityTier tier, uint256 amount) external returns (uint256 allocated);
    function purchaseAsset(address token, uint256 usdtAmount) external returns (uint256 tokensReceived);
    function redeemAsset(address token, uint256 tokenAmount) external returns (uint256 usdtReceived);
    function executeWaterfallLiquidation(uint256 amountNeeded, PNGYTypes.LiquidityTier maxTier) external returns (uint256 funded);
    function rebalanceBuffer() external;
    
    // ========== 层级配置（ADMIN 调用）==========
    function setLayerConfig(
        PNGYTypes.LiquidityTier tier,
        uint256 targetRatio,
        uint256 minRatio,
        uint256 maxRatio
    ) external;
    function getLayerConfigs() external view returns (
        PNGYTypes.LayerConfig memory layer1,
        PNGYTypes.LayerConfig memory layer2,
        PNGYTypes.LayerConfig memory layer3
    );
    function validateLayerRatios() external view returns (bool valid, uint256 totalRatio);
    
    // ========== 费用管理（ADMIN 调用）==========
    function accrueManagementFee() external;
    function accruePerformanceFee() external;
    function collectFees() external;
    function withdrawRedemptionFees(uint256 amount) external;
    function setFeeRecipient(address recipient) external;
    function setLayer3HighWaterMark(uint256 value) external;
    function getPendingFees() external view returns (PNGYTypes.FeeInfo memory);
    function getRedemptionFeeInfo() external view returns (PNGYTypes.RedemptionFeeInfo memory);
    
    // ========== OTC 管理 ==========
    function createOTCOrder(
        address rwaToken,
        uint256 usdtAmount,
        uint256 expectedTokens,
        address counterparty,
        uint256 expiresIn
    ) external returns (uint256 orderId);
    function executeOTCPayment(uint256 orderId) external;
    function confirmOTCDelivery(uint256 orderId, uint256 actualTokens) external;
    
    // ========== 查询 ==========
    function getAssetConfigs() external view returns (PNGYTypes.AssetConfig[] memory);
    function getLayerAssets(PNGYTypes.LiquidityTier tier) external view returns (address[] memory);
    function getLayerValue(PNGYTypes.LiquidityTier tier) external view returns (uint256);
    function getBufferPoolInfo() external view returns (PNGYTypes.BufferPoolInfo memory);
    function calculateAssetValue() external view returns (uint256);
    
    // ========== 外部合约设置（ADMIN 调用）==========
    function setOracleAdapter(address oracle) external;
    function setSwapHelper(address helper) external;
    function setOTCManager(address manager) external;
    function setAssetScheduler(address scheduler) external;
    function setDefaultSwapSlippage(uint256 slippage) external;
    function refreshCache() external;
}

/// @title IOracleAdapter
interface IOracleAdapter {
    function getPrice(address token) external view returns (uint256);
}

/// @title ISwapHelper
interface ISwapHelper {
    function buyRWAAsset(address tokenIn, address tokenOut, uint256 amountIn, uint256 slippageBps) external returns (uint256);
    function sellRWAAsset(address tokenIn, address tokenOut, uint256 amountIn, uint256 slippageBps) external returns (uint256);
}

/// @title IOTCManager
interface IOTCManager {
    function createOrder(address rwaToken, uint256 usdtAmount, uint256 expectedTokens, address counterparty, uint256 expiresIn) external returns (uint256);
    function executePayment(uint256 orderId) external;
    function confirmDelivery(uint256 orderId, uint256 actualTokens) external;
}

/// @title IAssetScheduler
interface IAssetScheduler {
    struct RedemptionWindow {
        uint256 windowId;
        uint256 startDate;
        uint256 endDate;
        uint256 settlementDate;
        uint256 totalScheduledAmount;
        bool isActive;
    }
    
    function getCurrentWindow() external view returns (RedemptionWindow memory);
    function calculateNextWindowDate() external view returns (uint256 nextStart, uint256 nextSettlement);
    function getWindowSettlementTime(uint256 windowId) external view returns (uint256);
    function scheduleRedemptionWithAdvance(
        address owner,
        address receiver,
        uint256 shares,
        uint256 grossAmount,
        uint256 lockedNav,
        uint256 advanceDays
    ) external returns (uint256 schedulerRequestId, uint256 windowId);
}