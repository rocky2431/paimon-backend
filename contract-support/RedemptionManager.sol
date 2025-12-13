// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC4626} from "@openzeppelin/contracts/interfaces/IERC4626.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {PNGYTypes} from "./PNGYTypes.sol";
import {IPNGYVault, IRedemptionManager, IAssetScheduler, IAssetController} from "./IPNGYContracts.sol";

/// @title RedemptionManager
/// @author Paimon Yield Protocol
/// @notice 赎回管理合约 - 用户直接调用进行赎回操作
/// @dev 赎回通道说明：
///      1. 标准通道 (T+7): 金额 < 总资产2%
///         - 审批条件: >=10万U 或 >=(Layer1+Layer2)的5%
///      2. 大额定期通道: 金额 >= 总资产2%
///         - 需提前15天预约本期，否则预约下一期
///      3. 紧急通道 (T+1): 需开启emergencyMode，额外1%费用
///         - 审批条件: >3万U 或 >Layer1的10%
contract RedemptionManager is IRedemptionManager, AccessControl, ReentrancyGuard, Pausable {
    
    // =============================================================================
    // Roles
    // =============================================================================
    
    bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");
    bytes32 public constant VIP_APPROVER_ROLE = keccak256("VIP_APPROVER_ROLE");

    // =============================================================================
    // External Contracts
    // =============================================================================
    
    IPNGYVault public immutable vault;
    IAssetScheduler public assetScheduler;
    IAssetController public assetController;

    // =============================================================================
    // State Variables
    // =============================================================================
    
    mapping(uint256 => PNGYTypes.RedemptionRequest) private _requests;
    mapping(address => uint256[]) private _userRequests;
    uint256 private _requestIdCounter;
    
    uint256[] private _pendingApprovals;
    uint256 public  totalPendingApprovalAmount;
    
    uint256 private _lastLiquidityAlertTime;

    // =============================================================================
    // Events
    // =============================================================================
    
    event RedemptionRequested(
        uint256 indexed requestId,
        address indexed owner,
        address receiver,
        uint256 shares,
        uint256 lockedAmount,
        uint256 estimatedFee,
        PNGYTypes.RedemptionChannel channel,
        bool requiresApproval,
        uint256 settlementTime,
        uint256 windowId
    );
    
    event RedemptionSettled(
        uint256 indexed requestId,
        address indexed owner,
        address receiver,
        uint256 grossAmount,
        uint256 fee,
        uint256 netAmount,
        PNGYTypes.RedemptionChannel channel
    );
    
    event RedemptionApproved(uint256 indexed requestId, address indexed approver, uint256 settlementTime);
    event RedemptionRejected(uint256 indexed requestId, address indexed rejector, string reason);
    event RedemptionCancelled(uint256 indexed requestId, address indexed owner);
    event LowLiquidityAlert(uint256 currentRatio, uint256 threshold, uint256 available, uint256 total);
    event CriticalLiquidityAlert(uint256 currentRatio, uint256 threshold, uint256 available);
    event AssetSchedulerUpdated(address indexed oldScheduler, address indexed newScheduler);
    event AssetControllerUpdated(address indexed oldController, address indexed newController);

    // =============================================================================
    // Errors
    // =============================================================================
    
    error ZeroAddress();
    error ZeroAmount();
    error InsufficientShares(uint256 available, uint256 required);
    error InsufficientLiquidity(uint256 available, uint256 required);
    error RequestNotFound(uint256 requestId);
    error InvalidRequestStatus(uint256 requestId);
    error SettlementTimeNotReached(uint256 settlementTime, uint256 currentTime);
    error NotPendingApproval(uint256 requestId);
    error EmergencyModeNotActive();
    error SchedulerNotConfigured();
    error NotRequestOwner();

    // =============================================================================
    // Constructor
    // =============================================================================
    
    constructor(address vault_, address admin_) {
        if (vault_ == address(0) || admin_ == address(0)) revert ZeroAddress();
        vault = IPNGYVault(vault_);
        _grantRole(DEFAULT_ADMIN_ROLE, admin_);
        _grantRole(ADMIN_ROLE, admin_);
        _grantRole(VIP_APPROVER_ROLE, admin_);
    }

    // =============================================================================
    // User Functions - 用户直接调用
    // =============================================================================
    
    /// @notice 请求赎回（用户直接调用）
    /// @param shares 要赎回的份额
    /// @param receiver 接收 USDT 的地址
    /// @return requestId 赎回请求 ID
    function requestRedemption(
        uint256 shares,
        address receiver
    ) external override nonReentrant whenNotPaused returns (uint256 requestId) {
        if (shares == 0) revert ZeroAmount();
        if (receiver == address(0)) revert ZeroAddress();
        
        address owner = msg.sender;
        uint256 userBalance = _balanceOf(owner);
        uint256 lockedShares = vault.lockedSharesOf(owner);
        uint256 availableShares = userBalance > lockedShares ? userBalance - lockedShares : 0;
        
        if (availableShares < shares) revert InsufficientShares(availableShares, shares);
        
        uint256 nav = vault.sharePrice();
        uint256 grossAmount = (shares * nav) / PNGYTypes.PRECISION;
        
        // 判断通道
        if (_isLargeRedemption(grossAmount)) {
            return _processScheduledRedemption(owner, shares, receiver, grossAmount, nav);
        } else {
            return _processStandardRedemption(owner, shares, receiver, grossAmount, nav);
        }
    }
    
    /// @notice 请求紧急赎回（用户直接调用）
    /// @param shares 要赎回的份额
    /// @param receiver 接收 USDT 的地址
    /// @return requestId 赎回请求 ID
    function requestEmergencyRedemption(
        uint256 shares,
        address receiver
    ) external override nonReentrant returns (uint256 requestId) {
        if (!vault.emergencyMode()) revert EmergencyModeNotActive();
        if (shares == 0) revert ZeroAmount();
        if (receiver == address(0)) revert ZeroAddress();
        
        address owner = msg.sender;
        uint256 userBalance = _balanceOf(owner);
        uint256 lockedShares = vault.lockedSharesOf(owner);
        uint256 availableShares = userBalance > lockedShares ? userBalance - lockedShares : 0;
        
        if (availableShares < shares) revert InsufficientShares(availableShares, shares);
        
        uint256 nav = vault.sharePrice();
        uint256 grossAmount = (shares * nav) / PNGYTypes.PRECISION;
        
        return _processEmergencyRedemption(owner, shares, receiver, grossAmount, nav);
    }
    
    /// @notice 结算赎回（任何人可调用，但只有到期的请求才能结算）
    function settleRedemption(uint256 requestId) external override nonReentrant {
        PNGYTypes.RedemptionRequest storage request = _requests[requestId];
        
        if (request.requestId == 0) revert RequestNotFound(requestId);
        if (request.channel == PNGYTypes.RedemptionChannel.SCHEDULED) {
            revert InvalidRequestStatus(requestId);
        }
        if (request.status != PNGYTypes.RedemptionStatus.PENDING && 
            request.status != PNGYTypes.RedemptionStatus.APPROVED) {
            revert InvalidRequestStatus(requestId);
        }
        if (block.timestamp < request.settlementTime) {
            revert SettlementTimeNotReached(request.settlementTime, block.timestamp);
        }
        
        _executeSettlement(request);
    }
    
    /// @notice 结算大额定期赎回
    function settleScheduledRedemption(uint256 requestId) external override nonReentrant {
        PNGYTypes.RedemptionRequest storage request = _requests[requestId];
        
        if (request.requestId == 0) revert RequestNotFound(requestId);
        if (request.channel != PNGYTypes.RedemptionChannel.SCHEDULED) {
            revert InvalidRequestStatus(requestId);
        }
        if (request.status != PNGYTypes.RedemptionStatus.PENDING) {
            revert InvalidRequestStatus(requestId);
        }
        
        // 检查窗口结算时间
        if (address(assetScheduler) != address(0)) {
            uint256 windowTime = assetScheduler.getWindowSettlementTime(request.windowId);
            if (block.timestamp < windowTime) {
                revert SettlementTimeNotReached(windowTime, block.timestamp);
            }
        }
        
        _executeSettlement(request);
    }
    
    /// @notice 批量结算
    function batchSettleRedemptions(uint256 maxCount) external override nonReentrant returns (uint256 settled) {
        for (uint256 i = 1; i <= _requestIdCounter && settled < maxCount; i++) {
            PNGYTypes.RedemptionRequest storage request = _requests[i];
            
            if (request.channel == PNGYTypes.RedemptionChannel.SCHEDULED) continue;
            
            bool isSettleable = (
                request.status == PNGYTypes.RedemptionStatus.PENDING || 
                request.status == PNGYTypes.RedemptionStatus.APPROVED
            ) && request.settlementTime > 0 && block.timestamp >= request.settlementTime;
            
            if (isSettleable) {
                // 尝试结算，失败则跳过
                try this.settleRedemptionInternal(i) {
                    settled++;
                } catch {}
            }
        }
    }
    
    /// @dev 内部结算（供 batch 调用）
    function settleRedemptionInternal(uint256 requestId) external {
        require(msg.sender == address(this), "Internal only");
        _executeSettlement(_requests[requestId]);
    }
    
    /// @notice 用户取消待审批的赎回请求
    function cancelRedemption(uint256 requestId) external override nonReentrant {
        PNGYTypes.RedemptionRequest storage request = _requests[requestId];
        
        if (request.requestId == 0) revert RequestNotFound(requestId);
        if (request.owner != msg.sender) revert NotRequestOwner();
        if (request.status != PNGYTypes.RedemptionStatus.PENDING_APPROVAL) {
            revert InvalidRequestStatus(requestId);
        }
        
        request.status = PNGYTypes.RedemptionStatus.CANCELLED;
        
        // 解锁份额
        vault.unlockShares(request.owner, request.shares);
        vault.removeRedemptionLiability(request.grossAmount);
        
        _removeFromPendingApprovals(requestId);
        totalPendingApprovalAmount -= request.grossAmount;
        
        emit RedemptionCancelled(requestId, msg.sender);
    }

    // =============================================================================
    // Preview Functions - 用户直接调用
    // =============================================================================
    
    /// @notice 预览赎回（用户直接调用）
    function previewRedemption(uint256 shares) external view override returns (PNGYTypes.RedemptionPreview memory preview) {
        return _previewRedemption(msg.sender, shares);
    }
    
    /// @notice 预览指定用户的赎回
    function previewRedemptionFor(address owner, uint256 shares) external view override returns (PNGYTypes.RedemptionPreview memory preview) {
        return _previewRedemption(owner, shares);
    }
    
    function _previewRedemption(address owner, uint256 shares) internal view returns (PNGYTypes.RedemptionPreview memory preview) {
        if (shares == 0) {
            preview.canProcess = false;
            preview.channelReason = "Shares cannot be zero";
            return preview;
        }
        
        uint256 userBalance = _balanceOf(owner);
        uint256 lockedShares = vault.lockedSharesOf(owner);
        uint256 availableShares = userBalance > lockedShares ? userBalance - lockedShares : 0;
        
        if (availableShares < shares) {
            preview.canProcess = false;
            preview.channelReason = "Insufficient available shares";
            return preview;
        }
        
        uint256 nav = vault.sharePrice();
        preview.grossAmount = (shares * nav) / PNGYTypes.PRECISION;
        preview.fee = _calculateRedemptionFee(preview.grossAmount, false);
        preview.netAmount = preview.grossAmount - preview.fee;
        
        if (_isLargeRedemption(preview.grossAmount)) {
            preview.channel = PNGYTypes.RedemptionChannel.SCHEDULED;
            preview.requiresApproval = false;
            
            if (address(assetScheduler) == address(0)) {
                preview.canProcess = false;
                preview.channelReason = "Large redemption: AssetScheduler not configured";
                return preview;
            }
            
            IAssetScheduler.RedemptionWindow memory window = assetScheduler.getCurrentWindow();
            
            if (block.timestamp + PNGYTypes.SCHEDULED_ADVANCE_DAYS > window.settlementDate) {
                (, uint256 nextSettlement) = assetScheduler.calculateNextWindowDate();
                preview.settlementDelay = nextSettlement - block.timestamp;
                preview.estimatedSettlementTime = nextSettlement;
                preview.channelReason = "Large redemption (>=2% AUM): Scheduled to next window (less than 15 days to current)";
            } else {
                preview.settlementDelay = window.settlementDate - block.timestamp;
                preview.estimatedSettlementTime = window.settlementDate;
                preview.windowId = window.windowId;
                preview.channelReason = "Large redemption (>=2% AUM): Scheduled to current window";
            }
            preview.canProcess = true;
        } else {
            preview.channel = PNGYTypes.RedemptionChannel.STANDARD;
            preview.requiresApproval = _requiresStandardApproval(preview.grossAmount);
            preview.settlementDelay = PNGYTypes.STANDARD_REDEMPTION_DELAY;
            preview.estimatedSettlementTime = block.timestamp + PNGYTypes.STANDARD_REDEMPTION_DELAY;
            
            uint256 available = vault.getAvailableLiquidity();
            if (preview.netAmount > available) {
                preview.canProcess = false;
                preview.channelReason = "Standard channel: Insufficient liquidity";
            } else {
                preview.canProcess = true;
                preview.channelReason = preview.requiresApproval
                    ? "Standard channel (T+7): Requires approval (>=100K or >=5% L1+L2)"
                    : "Standard channel (T+7): No approval required";
            }
        }
    }
    
    /// @notice 预览紧急赎回
    function previewEmergencyRedemption(uint256 shares) external view override returns (PNGYTypes.RedemptionPreview memory preview) {
        if (!vault.emergencyMode()) {
            preview.canProcess = false;
            preview.channelReason = "Emergency mode not active";
            return preview;
        }
        
        address owner = msg.sender;
        if (shares == 0) {
            preview.canProcess = false;
            preview.channelReason = "Shares cannot be zero";
            return preview;
        }
        
        uint256 userBalance = _balanceOf(owner);
        uint256 lockedShares = vault.lockedSharesOf(owner);
        uint256 availableShares = userBalance > lockedShares ? userBalance - lockedShares : 0;
        
        if (availableShares < shares) {
            preview.canProcess = false;
            preview.channelReason = "Insufficient available shares";
            return preview;
        }
        
        uint256 nav = vault.sharePrice();
        preview.grossAmount = (shares * nav) / PNGYTypes.PRECISION;
        preview.fee = _calculateRedemptionFee(preview.grossAmount, true);
        preview.netAmount = preview.grossAmount - preview.fee;
        preview.channel = PNGYTypes.RedemptionChannel.EMERGENCY;
        preview.requiresApproval = _requiresEmergencyApproval(preview.grossAmount);
        preview.settlementDelay = PNGYTypes.EMERGENCY_REDEMPTION_DELAY;
        preview.estimatedSettlementTime = block.timestamp + PNGYTypes.EMERGENCY_REDEMPTION_DELAY;
        
        uint256 available = vault.getAvailableLiquidity();
        if (preview.netAmount > available) {
            preview.canProcess = false;
            preview.channelReason = "Emergency channel: Insufficient liquidity";
        } else {
            preview.canProcess = true;
            preview.channelReason = preview.requiresApproval
                ? "Emergency channel (T+1): Requires approval (>30K or >10% L1), +1% fee"
                : "Emergency channel (T+1): No approval required, +1% fee";
        }
    }

    // =============================================================================
    // Approval Functions - VIP Approver 调用
    // =============================================================================
    
    function approveRedemption(uint256 requestId) external override onlyRole(VIP_APPROVER_ROLE) {
        PNGYTypes.RedemptionRequest storage request = _requests[requestId];
        
        if (request.requestId == 0) revert RequestNotFound(requestId);
        if (!request.requiresApproval) revert NotPendingApproval(requestId);
        if (request.status != PNGYTypes.RedemptionStatus.PENDING_APPROVAL) {
            revert NotPendingApproval(requestId);
        }
        
        uint256 delay = request.channel == PNGYTypes.RedemptionChannel.EMERGENCY
            ? PNGYTypes.EMERGENCY_REDEMPTION_DELAY
            : PNGYTypes.STANDARD_REDEMPTION_DELAY;
        
        request.settlementTime = block.timestamp + delay;
        request.status = PNGYTypes.RedemptionStatus.APPROVED;
        
        _removeFromPendingApprovals(requestId);
        totalPendingApprovalAmount -= request.grossAmount;
        
        emit RedemptionApproved(requestId, msg.sender, request.settlementTime);
    }
    
    function rejectRedemption(uint256 requestId, string calldata reason) external override onlyRole(VIP_APPROVER_ROLE) {
        PNGYTypes.RedemptionRequest storage request = _requests[requestId];
        
        if (request.requestId == 0) revert RequestNotFound(requestId);
        if (!request.requiresApproval) revert NotPendingApproval(requestId);
        if (request.status != PNGYTypes.RedemptionStatus.PENDING_APPROVAL) {
            revert NotPendingApproval(requestId);
        }
        
        request.status = PNGYTypes.RedemptionStatus.CANCELLED;
        
        vault.unlockShares(request.owner, request.shares);
        vault.removeRedemptionLiability(request.grossAmount);
        
        _removeFromPendingApprovals(requestId);
        totalPendingApprovalAmount -= request.grossAmount;
        
        emit RedemptionRejected(requestId, msg.sender, reason);
    }

    // =============================================================================
    // Internal Processing
    // =============================================================================
    
    function _processStandardRedemption(
        address owner,
        uint256 shares,
        address receiver,
        uint256 grossAmount,
        uint256 nav
    ) internal returns (uint256 requestId) {
        bool requiresApproval = _requiresStandardApproval(grossAmount);
        uint256 estimatedFee = _calculateRedemptionFee(grossAmount, false);
        uint256 estimatedNet = grossAmount - estimatedFee;
        
        uint256 available = vault.getAvailableLiquidity();
        if (estimatedNet > available) {
            _checkLiquidityAndAlert();
            revert InsufficientLiquidity(available, estimatedNet);
        }
        
        vault.lockShares(owner, shares);
        vault.addRedemptionLiability(grossAmount);
        
        requestId = ++_requestIdCounter;
        
        PNGYTypes.RedemptionStatus status = requiresApproval 
            ? PNGYTypes.RedemptionStatus.PENDING_APPROVAL 
            : PNGYTypes.RedemptionStatus.PENDING;
        uint256 settlementTime = requiresApproval ? 0 : block.timestamp + PNGYTypes.STANDARD_REDEMPTION_DELAY;
        
        _requests[requestId] = PNGYTypes.RedemptionRequest({
            requestId: requestId,
            owner: owner,
            receiver: receiver,
            shares: shares,
            grossAmount: grossAmount,
            lockedNav: nav,
            estimatedFee: estimatedFee,
            requestTime: block.timestamp,
            settlementTime: settlementTime,
            status: status,
            channel: PNGYTypes.RedemptionChannel.STANDARD,
            requiresApproval: requiresApproval,
            windowId: 0
        });
        
        _userRequests[owner].push(requestId);
        
        if (requiresApproval) {
            _pendingApprovals.push(requestId);
            totalPendingApprovalAmount += grossAmount;
        }
        
        emit RedemptionRequested(
            requestId, owner, receiver, shares, grossAmount, estimatedFee,
            PNGYTypes.RedemptionChannel.STANDARD, requiresApproval, settlementTime, 0
        );
        
        _checkLiquidityAndAlert();
    }
    
    function _processEmergencyRedemption(
        address owner,
        uint256 shares,
        address receiver,
        uint256 grossAmount,
        uint256 nav
    ) internal returns (uint256 requestId) {
        bool requiresApproval = _requiresEmergencyApproval(grossAmount);
        uint256 estimatedFee = _calculateRedemptionFee(grossAmount, true);
        uint256 estimatedNet = grossAmount - estimatedFee;
        
        uint256 available = vault.getAvailableLiquidity();
        if (estimatedNet > available) {
            revert InsufficientLiquidity(available, estimatedNet);
        }
        
        vault.lockShares(owner, shares);
        vault.addRedemptionLiability(grossAmount);
        
        requestId = ++_requestIdCounter;
        
        PNGYTypes.RedemptionStatus status = requiresApproval 
            ? PNGYTypes.RedemptionStatus.PENDING_APPROVAL 
            : PNGYTypes.RedemptionStatus.PENDING;
        uint256 settlementTime = requiresApproval ? 0 : block.timestamp + PNGYTypes.EMERGENCY_REDEMPTION_DELAY;
        
        _requests[requestId] = PNGYTypes.RedemptionRequest({
            requestId: requestId,
            owner: owner,
            receiver: receiver,
            shares: shares,
            grossAmount: grossAmount,
            lockedNav: nav,
            estimatedFee: estimatedFee,
            requestTime: block.timestamp,
            settlementTime: settlementTime,
            status: status,
            channel: PNGYTypes.RedemptionChannel.EMERGENCY,
            requiresApproval: requiresApproval,
            windowId: 0
        });
        
        _userRequests[owner].push(requestId);
        
        if (requiresApproval) {
            _pendingApprovals.push(requestId);
            totalPendingApprovalAmount += grossAmount;
        }
        
        emit RedemptionRequested(
            requestId, owner, receiver, shares, grossAmount, estimatedFee,
            PNGYTypes.RedemptionChannel.EMERGENCY, requiresApproval, settlementTime, 0
        );
    }
    
    function _processScheduledRedemption(
        address owner,
        uint256 shares,
        address receiver,
        uint256 grossAmount,
        uint256 nav
    ) internal returns (uint256 requestId) {
        if (address(assetScheduler) == address(0)) revert SchedulerNotConfigured();
        
        uint256 estimatedFee = _calculateRedemptionFee(grossAmount, false);
        
        vault.lockShares(owner, shares);
        vault.addRedemptionLiability(grossAmount);
        
        (, uint256 windowId) = assetScheduler.scheduleRedemptionWithAdvance(
            owner, receiver, shares, grossAmount, nav, PNGYTypes.SCHEDULED_ADVANCE_DAYS
        );
        
        uint256 settlementTime = assetScheduler.getWindowSettlementTime(windowId);
        
        requestId = ++_requestIdCounter;
        
        _requests[requestId] = PNGYTypes.RedemptionRequest({
            requestId: requestId,
            owner: owner,
            receiver: receiver,
            shares: shares,
            grossAmount: grossAmount,
            lockedNav: nav,
            estimatedFee: estimatedFee,
            requestTime: block.timestamp,
            settlementTime: settlementTime,
            status: PNGYTypes.RedemptionStatus.PENDING,
            channel: PNGYTypes.RedemptionChannel.SCHEDULED,
            requiresApproval: false,
            windowId: windowId
        });
        
        _userRequests[owner].push(requestId);
        
        emit RedemptionRequested(
            requestId, owner, receiver, shares, grossAmount, estimatedFee,
            PNGYTypes.RedemptionChannel.SCHEDULED, false, settlementTime, windowId
        );
    }
    
    function _executeSettlement(PNGYTypes.RedemptionRequest storage request) internal {
        bool isEmergency = request.channel == PNGYTypes.RedemptionChannel.EMERGENCY;
        uint256 actualFee = _calculateRedemptionFee(request.grossAmount, isEmergency);
        uint256 payoutAmount = request.grossAmount - actualFee;
        
        // 检查现金余额，必要时触发瀑布清算
        uint256 availableCash = IERC20(_asset()).balanceOf(address(vault));
        if (availableCash < payoutAmount) {
            // 尝试瀑布清算
            if (address(assetController) != address(0)) {
                uint256 deficit = payoutAmount - availableCash;
                assetController.executeWaterfallLiquidation(deficit, PNGYTypes.LiquidityTier.TIER_2_MMF);
                availableCash = IERC20(_asset()).balanceOf(address(vault));
            }
        }
        
        if (availableCash < payoutAmount) {
            revert InsufficientLiquidity(availableCash, payoutAmount);
        }
        
        vault.burnLockedShares(request.owner, request.shares);
        vault.removeRedemptionLiability(request.grossAmount);
        vault.addRedemptionFee(actualFee);
        vault.transferAssetTo(request.receiver, payoutAmount);
        
        request.status = PNGYTypes.RedemptionStatus.SETTLED;
        
        emit RedemptionSettled(
            request.requestId,
            request.owner,
            request.receiver,
            request.grossAmount,
            actualFee,
            payoutAmount,
            request.channel
        );
    }

    // =============================================================================
    // Channel Detection
    // =============================================================================
    
    function _isLargeRedemption(uint256 amount) internal view returns (bool) {
        uint256 total = _totalAssets();
        if (total == 0) return false;
        return amount >= (total * PNGYTypes.LARGE_REDEMPTION_THRESHOLD) / PNGYTypes.BASIS_POINTS;
    }
    
    function _requiresStandardApproval(uint256 amount) internal view returns (bool) {
        uint256 totalLiquidity = vault.getLayer1Liquidity() + vault.getLayer2Liquidity();
        uint256 threshold = (totalLiquidity * PNGYTypes.STANDARD_APPROVAL_LIQUIDITY_RATIO) / PNGYTypes.BASIS_POINTS;
        return amount >= PNGYTypes.STANDARD_APPROVAL_AMOUNT || amount >= threshold;
    }
    
    function _requiresEmergencyApproval(uint256 amount) internal view returns (bool) {
        uint256 layer1 = vault.getLayer1Liquidity();
        uint256 threshold = (layer1 * PNGYTypes.EMERGENCY_APPROVAL_L1_RATIO) / PNGYTypes.BASIS_POINTS;
        return amount > PNGYTypes.EMERGENCY_APPROVAL_AMOUNT || amount > threshold;
    }
    
    function _calculateRedemptionFee(uint256 amount, bool isEmergency) internal view returns (uint256) {
        uint256 feeBps = PNGYTypes.BASE_REDEMPTION_FEE;
        
        if (amount > 50000e18) feeBps += 20;
        if (amount > 100000e18) feeBps += 20;
        
        uint256 available = vault.getAvailableLiquidity();
        uint256 gross = _totalAssets() + vault.totalRedemptionLiability();
        
        if (gross > 0) {
            uint256 ratio = (available * PNGYTypes.BASIS_POINTS) / gross;
            if (ratio < PNGYTypes.LOW_LIQUIDITY_THRESHOLD) feeBps += 30;
            else if (ratio < 2000) feeBps += 15;
        }
        
        if (isEmergency) feeBps += PNGYTypes.EMERGENCY_FEE_PREMIUM;
        
        uint256 maxFee = PNGYTypes.MAX_REDEMPTION_FEE + (isEmergency ? PNGYTypes.EMERGENCY_FEE_PREMIUM : 0);
        if (feeBps > maxFee) feeBps = maxFee;
        
        return (amount * feeBps) / PNGYTypes.BASIS_POINTS;
    }

    // =============================================================================
    // ERC4626 Helpers
    // =============================================================================

    /// @dev 获取用户 Vault 份额余额
    function _balanceOf(address owner) internal view returns (uint256) {
        return IERC4626(address(vault)).balanceOf(owner);
    }

    /// @dev 获取底层资产地址
    function _asset() internal view returns (address) {
        return IERC4626(address(vault)).asset();
    }

    /// @dev 获取 Vault 总资产
    function _totalAssets() internal view returns (uint256) {
        return IERC4626(address(vault)).totalAssets();
    }

    // =============================================================================
    // Internal Helpers
    // =============================================================================

    function _removeFromPendingApprovals(uint256 requestId) internal {
        uint256 len = _pendingApprovals.length;
        for (uint256 i = 0; i < len; i++) {
            if (_pendingApprovals[i] == requestId) {
                _pendingApprovals[i] = _pendingApprovals[len - 1];
                _pendingApprovals.pop();
                return;
            }
        }
    }
    
    function _checkLiquidityAndAlert() internal {
        if (block.timestamp < _lastLiquidityAlertTime + 1 hours) return;
        
        uint256 available = vault.getAvailableLiquidity();
        uint256 gross = _totalAssets() + vault.totalRedemptionLiability();
        if (gross == 0) return;
        
        uint256 ratio = (available * PNGYTypes.BASIS_POINTS) / gross;
        
        if (ratio < PNGYTypes.CRITICAL_LIQUIDITY_THRESHOLD) {
            emit CriticalLiquidityAlert(ratio, PNGYTypes.CRITICAL_LIQUIDITY_THRESHOLD, available);
            _lastLiquidityAlertTime = block.timestamp;
        } else if (ratio < PNGYTypes.LOW_LIQUIDITY_THRESHOLD) {
            emit LowLiquidityAlert(ratio, PNGYTypes.LOW_LIQUIDITY_THRESHOLD, available, gross);
            _lastLiquidityAlertTime = block.timestamp;
        }
    }

    // =============================================================================
    // View Functions
    // =============================================================================
    
    function getRedemptionRequest(uint256 requestId) external view override returns (PNGYTypes.RedemptionRequest memory) {
        return _requests[requestId];
    }
    
    function getUserRedemptions(address user) external view override returns (uint256[] memory) {
        return _userRequests[user];
    }
    
    function getPendingApprovals() external view override returns (uint256[] memory) {
        return _pendingApprovals;
    }
    
    function getTotalPendingApprovalAmount() external view override returns (uint256) {
        return totalPendingApprovalAmount;
    }
    
    function getRequestCount() external view override returns (uint256) {
        return _requestIdCounter;
    }

    // =============================================================================
    // Admin Functions
    // =============================================================================
    
    function setAssetScheduler(address scheduler) external onlyRole(ADMIN_ROLE) {
        address old = address(assetScheduler);
        assetScheduler = IAssetScheduler(scheduler);
        emit AssetSchedulerUpdated(old, scheduler);
    }
    
    function setAssetController(address controller) external onlyRole(ADMIN_ROLE) {
        address old = address(assetController);
        assetController = IAssetController(controller);
        emit AssetControllerUpdated(old, controller);
    }
    
    function pause() external onlyRole(ADMIN_ROLE) {
        _pause();
    }
    
    function unpause() external onlyRole(ADMIN_ROLE) {
        _unpause();
    }
}