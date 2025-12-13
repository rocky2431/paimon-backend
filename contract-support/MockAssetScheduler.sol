// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {IAssetScheduler} from "../interfaces/IAssetScheduler.sol";

/// @title MockAssetScheduler
/// @notice Mock implementation of IAssetScheduler for testing
/// @dev Simulates quarterly redemption windows for large redemptions
contract MockAssetScheduler is IAssetScheduler, AccessControl {
    // =============================================================================
    // Constants
    // =============================================================================

    bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");

    // =============================================================================
    // State Variables
    // =============================================================================

    /// @notice The vault address
    address public override vault;

    /// @notice Window counter
    uint256 private _windowIdCounter;

    /// @notice Request counter
    uint256 private _requestIdCounter;

    /// @notice All windows by ID
    mapping(uint256 => RedemptionWindow) private _windows;

    /// @notice All requests by ID
    mapping(uint256 => ScheduledRequest) private _requests;

    /// @notice User's request IDs
    mapping(address => uint256[]) private _userRequests;

    /// @notice Window's request IDs
    mapping(uint256 => uint256[]) private _windowRequests;

    /// @notice Current window ID
    uint256 public currentWindowId;

    /// @notice Window configuration: months [3, 6, 9, 12] = quarterly
    uint8[4] private _windowMonths;

    /// @notice Day of month for settlement
    uint8 public settlementDayOfMonth;

    /// @notice Window duration before settlement (how long the window is open)
    uint256 public windowDuration;

    /// @notice Mock: configurable settlement delay for testing
    uint256 public mockSettlementDelay;

    // =============================================================================
    // Events (additional for testing)
    // =============================================================================

    event VaultUpdated(address indexed oldVault, address indexed newVault);
    event MockSettlementDelayUpdated(uint256 oldDelay, uint256 newDelay);

    // =============================================================================
    // Constructor
    // =============================================================================

    constructor(address admin_, address vault_) {
        if (admin_ == address(0)) revert ZeroAddress();

        _grantRole(DEFAULT_ADMIN_ROLE, admin_);
        _grantRole(ADMIN_ROLE, admin_);

        vault = vault_;
        
        // Default: quarterly windows (March, June, September, December)
        _windowMonths = [3, 6, 9, 12];
        settlementDayOfMonth = 15;
        windowDuration = 14 days;
        mockSettlementDelay = 30 days; // Default 30 days for testing

        // Create initial window
        _createInitialWindow();
    }

    // =============================================================================
    // Modifiers
    // =============================================================================

    modifier onlyVaultOrAdmin() {
        require(msg.sender == vault || hasRole(ADMIN_ROLE, msg.sender), "Not authorized");
        _;
    }

    // =============================================================================
    // IAssetScheduler Implementation - Core Functions
    // =============================================================================

    /// @inheritdoc IAssetScheduler
    function scheduleRedemption(
        address owner,
        address receiver,
        uint256 shares,
        uint256 lockedAmount,
        uint256 lockedNav
    ) external override onlyVaultOrAdmin returns (uint256 requestId, uint256 windowId) {
        if (owner == address(0)) revert ZeroAddress();
        if (receiver == address(0)) revert ZeroAddress();
        if (shares == 0) revert ZeroAmount();

        windowId = currentWindowId;
        RedemptionWindow storage window = _windows[windowId];

        if (window.status != WindowStatus.OPEN && window.status != WindowStatus.UPCOMING) {
            // Get or create next window
            windowId = _getOrCreateNextWindowId();
            window = _windows[windowId];
        }

        requestId = ++_requestIdCounter;

        _requests[requestId] = ScheduledRequest({
            requestId: requestId,
            windowId: windowId,
            owner: owner,
            receiver: receiver,
            shares: shares,
            lockedAmount: lockedAmount,
            lockedNav: lockedNav,
            scheduledAt: block.timestamp,
            settled: false
        });

        _userRequests[owner].push(requestId);
        _windowRequests[windowId].push(requestId);

        window.totalScheduled += lockedAmount;

        emit RedemptionScheduled(requestId, windowId, owner, shares, lockedAmount);
    }

    /// @inheritdoc IAssetScheduler
    function scheduleRedemptionWithAdvance(
        address owner,
        address receiver,
        uint256 shares,
        uint256 lockedAmount,
        uint256 lockedNav,
        uint256 minAdvanceDays
    ) external override onlyVaultOrAdmin returns (uint256 requestId, uint256 windowId) {
        if (owner == address(0)) revert ZeroAddress();
        if (receiver == address(0)) revert ZeroAddress();
        if (shares == 0) revert ZeroAmount();

        // Check if current window has enough advance time
        RedemptionWindow storage currentWindow = _windows[currentWindowId];
        
        if (currentWindow.settlementDate > 0 && 
            block.timestamp + minAdvanceDays > currentWindow.settlementDate) {
            // Not enough advance time, schedule to next window
            windowId = _getOrCreateNextWindowId();
        } else {
            windowId = currentWindowId;
        }

        RedemptionWindow storage window = _windows[windowId];

        requestId = ++_requestIdCounter;

        _requests[requestId] = ScheduledRequest({
            requestId: requestId,
            windowId: windowId,
            owner: owner,
            receiver: receiver,
            shares: shares,
            lockedAmount: lockedAmount,
            lockedNav: lockedNav,
            scheduledAt: block.timestamp,
            settled: false
        });

        _userRequests[owner].push(requestId);
        _windowRequests[windowId].push(requestId);

        window.totalScheduled += lockedAmount;

        emit RedemptionScheduled(requestId, windowId, owner, shares, lockedAmount);
    }

    /// @inheritdoc IAssetScheduler
    function markSettled(uint256 requestId) external override onlyVaultOrAdmin {
        ScheduledRequest storage request = _requests[requestId];
        if (request.requestId == 0) revert RequestNotFound(requestId);
        if (request.settled) revert RequestAlreadySettled(requestId);

        request.settled = true;

        RedemptionWindow storage window = _windows[request.windowId];
        window.totalSettled += request.lockedAmount;

        emit RedemptionSettled(requestId, request.windowId, request.receiver, request.lockedAmount);
    }

    // =============================================================================
    // IAssetScheduler Implementation - View Functions
    // =============================================================================

    /// @inheritdoc IAssetScheduler
    function getCurrentWindow() external view override returns (RedemptionWindow memory) {
        return _windows[currentWindowId];
    }

    /// @inheritdoc IAssetScheduler
    function getOrCreateNextWindow() external override onlyVaultOrAdmin returns (RedemptionWindow memory) {
        uint256 nextWindowId = _getOrCreateNextWindowId();
        return _windows[nextWindowId];
    }

    /// @inheritdoc IAssetScheduler
    function getWindow(uint256 windowId) external view override returns (RedemptionWindow memory) {
        return _windows[windowId];
    }

    /// @inheritdoc IAssetScheduler
    function getRequest(uint256 requestId) external view override returns (ScheduledRequest memory) {
        return _requests[requestId];
    }

    /// @inheritdoc IAssetScheduler
    function getUserRequests(address user) external view override returns (uint256[] memory) {
        return _userRequests[user];
    }

    /// @inheritdoc IAssetScheduler
    function getWindowRequests(uint256 windowId) external view override returns (uint256[] memory) {
        return _windowRequests[windowId];
    }

    /// @inheritdoc IAssetScheduler
    function getWindowSettlementTime(uint256 windowId) external view override returns (uint256 settlementTime) {
        RedemptionWindow memory window = _windows[windowId];
        if (window.windowId == 0) revert WindowNotFound(windowId);
        return window.settlementDate;
    }

    /// @inheritdoc IAssetScheduler
    function calculateNextWindowDate() external view override returns (uint256 windowStart, uint256 settlementDate) {
        // For mock: use simple calculation based on mockSettlementDelay
        windowStart = block.timestamp + mockSettlementDelay - windowDuration;
        settlementDate = block.timestamp + mockSettlementDelay;
    }

    /// @inheritdoc IAssetScheduler
    function getWindowMonths() external view override returns (uint8[4] memory) {
        return _windowMonths;
    }

    // =============================================================================
    // IAssetScheduler Implementation - Admin Functions
    // =============================================================================

    /// @inheritdoc IAssetScheduler
    function processWindow(uint256 windowId) external override onlyRole(ADMIN_ROLE) {
        RedemptionWindow storage window = _windows[windowId];
        if (window.windowId == 0) revert WindowNotFound(windowId);
        if (window.status == WindowStatus.PROCESSING || window.status == WindowStatus.SETTLED) {
            revert WindowAlreadyProcessed(windowId);
        }

        window.status = WindowStatus.PROCESSING;
        emit WindowStatusChanged(windowId, WindowStatus.PROCESSING);
    }

    /// @inheritdoc IAssetScheduler
    function finalizeWindow(uint256 windowId) external override onlyRole(ADMIN_ROLE) {
        RedemptionWindow storage window = _windows[windowId];
        if (window.windowId == 0) revert WindowNotFound(windowId);
        if (window.status == WindowStatus.SETTLED) {
            revert WindowAlreadyProcessed(windowId);
        }

        window.status = WindowStatus.SETTLED;
        emit WindowStatusChanged(windowId, WindowStatus.SETTLED);

        // Advance to next window
        _advanceToNextWindow();
    }

    /// @inheritdoc IAssetScheduler
    function setWindowConfig(uint8[4] calldata months, uint8 dayOfMonth) external override onlyRole(ADMIN_ROLE) {
        _windowMonths = months;
        settlementDayOfMonth = dayOfMonth;
        emit WindowConfigUpdated(months, dayOfMonth);
    }

    // =============================================================================
    // Internal Functions
    // =============================================================================

    function _createInitialWindow() internal {
        uint256 windowId = ++_windowIdCounter;
        currentWindowId = windowId;

        uint256 settlementDate = block.timestamp + mockSettlementDelay;
        uint256 windowStart = block.timestamp;
        uint256 windowEnd = settlementDate - 1 days;

        _windows[windowId] = RedemptionWindow({
            windowId: windowId,
            windowStart: windowStart,
            windowEnd: windowEnd,
            settlementDate: settlementDate,
            totalScheduled: 0,
            totalSettled: 0,
            status: WindowStatus.OPEN
        });

        emit WindowCreated(windowId, windowStart, windowEnd, settlementDate);
        emit WindowStatusChanged(windowId, WindowStatus.OPEN);
    }

    function _getOrCreateNextWindowId() internal returns (uint256) {
        uint256 nextId = currentWindowId + 1;
        
        if (_windows[nextId].windowId == 0) {
            // Create next window
            RedemptionWindow memory currentWindow = _windows[currentWindowId];
            
            uint256 settlementDate = currentWindow.settlementDate + mockSettlementDelay;
            uint256 windowStart = currentWindow.settlementDate;
            uint256 windowEnd = settlementDate - 1 days;

            _windows[nextId] = RedemptionWindow({
                windowId: nextId,
                windowStart: windowStart,
                windowEnd: windowEnd,
                settlementDate: settlementDate,
                totalScheduled: 0,
                totalSettled: 0,
                status: WindowStatus.UPCOMING
            });

            _windowIdCounter = nextId;

            emit WindowCreated(nextId, windowStart, windowEnd, settlementDate);
        }

        return nextId;
    }

    function _advanceToNextWindow() internal {
        uint256 nextId = _getOrCreateNextWindowId();
        currentWindowId = nextId;
        
        RedemptionWindow storage nextWindow = _windows[nextId];
        if (nextWindow.status == WindowStatus.UPCOMING) {
            nextWindow.status = WindowStatus.OPEN;
            emit WindowStatusChanged(nextId, WindowStatus.OPEN);
        }
    }

    // =============================================================================
    // Mock Helper Functions (for testing)
    // =============================================================================

    /// @notice Set vault address
    function setVault(address newVault) external onlyRole(ADMIN_ROLE) {
        if (newVault == address(0)) revert ZeroAddress();
        address oldVault = vault;
        vault = newVault;
        emit VaultUpdated(oldVault, newVault);
    }

    /// @notice Set mock settlement delay (for testing)
    function setMockSettlementDelay(uint256 delay) external onlyRole(ADMIN_ROLE) {
        uint256 oldDelay = mockSettlementDelay;
        mockSettlementDelay = delay;
        emit MockSettlementDelayUpdated(oldDelay, delay);
    }

    /// @notice Set window duration
    function setWindowDuration(uint256 duration) external onlyRole(ADMIN_ROLE) {
        windowDuration = duration;
    }

    /// @notice Force open current window (for testing)
    function forceOpenWindow(uint256 windowId) external onlyRole(ADMIN_ROLE) {
        RedemptionWindow storage window = _windows[windowId];
        if (window.windowId == 0) revert WindowNotFound(windowId);
        window.status = WindowStatus.OPEN;
        emit WindowStatusChanged(windowId, WindowStatus.OPEN);
    }

    /// @notice Force set settlement time (for testing time-sensitive logic)
    function forceSetSettlementTime(uint256 windowId, uint256 settlementTime) external onlyRole(ADMIN_ROLE) {
        RedemptionWindow storage window = _windows[windowId];
        if (window.windowId == 0) revert WindowNotFound(windowId);
        window.settlementDate = settlementTime;
    }

    /// @notice Create a new window manually (for testing)
    function createWindow(
        uint256 windowStart,
        uint256 windowEnd,
        uint256 settlementDate
    ) external onlyRole(ADMIN_ROLE) returns (uint256 windowId) {
        windowId = ++_windowIdCounter;

        _windows[windowId] = RedemptionWindow({
            windowId: windowId,
            windowStart: windowStart,
            windowEnd: windowEnd,
            settlementDate: settlementDate,
            totalScheduled: 0,
            totalSettled: 0,
            status: WindowStatus.UPCOMING
        });

        emit WindowCreated(windowId, windowStart, windowEnd, settlementDate);
    }

    /// @notice Set current window ID (for testing)
    function setCurrentWindowId(uint256 windowId) external onlyRole(ADMIN_ROLE) {
        if (_windows[windowId].windowId == 0) revert WindowNotFound(windowId);
        currentWindowId = windowId;
    }

    /// @notice Get total window count
    function windowCount() external view returns (uint256) {
        return _windowIdCounter;
    }

    /// @notice Get total request count
    function requestCount() external view returns (uint256) {
        return _requestIdCounter;
    }
}


