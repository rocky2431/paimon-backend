// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {IOTCManager} from "../interfaces/IOTCManager.sol";

/// @title MockOTCManager
/// @notice Mock implementation of IOTCManager for testing
/// @dev Simulates OTC order lifecycle: create -> pay -> deliver
contract MockOTCManager is IOTCManager, AccessControl {
    using SafeERC20 for IERC20;

    // =============================================================================
    // Constants
    // =============================================================================

    bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");

    // =============================================================================
    // State Variables
    // =============================================================================

    /// @notice The vault address that can create orders
    address public override vault;

    /// @notice USDT token address
    address public usdt;

    /// @notice Order counter
    uint256 private _orderIdCounter;

    /// @notice All orders
    mapping(uint256 => OTCOrder) private _orders;

    /// @notice Pending orders by token
    mapping(address => uint256[]) private _pendingOrdersByToken;

    /// @notice Whitelisted counterparties
    mapping(address => bool) private _whitelisted;

    /// @notice Auto-deliver mode: if true, orders are auto-delivered after payment
    bool public autoDeliverMode;

    // =============================================================================
    // Events (additional for testing)
    // =============================================================================

    event VaultUpdated(address indexed oldVault, address indexed newVault);
    event AutoDeliverModeChanged(bool enabled);

    // =============================================================================
    // Constructor
    // =============================================================================

    constructor(address admin_, address usdt_, address vault_) {
        if (admin_ == address(0)) revert ZeroAddress();
        if (usdt_ == address(0)) revert ZeroAddress();

        _grantRole(DEFAULT_ADMIN_ROLE, admin_);
        _grantRole(ADMIN_ROLE, admin_);

        usdt = usdt_;
        vault = vault_;
        autoDeliverMode = true; // Default: auto-deliver for easier testing
    }

    // =============================================================================
    // Modifiers
    // =============================================================================

    modifier onlyVaultOrAdmin() {
        require(msg.sender == vault || hasRole(ADMIN_ROLE, msg.sender), "Not authorized");
        _;
    }

    // =============================================================================
    // IOTCManager Implementation
    // =============================================================================

    /// @inheritdoc IOTCManager
    function createOrder(
        address rwaToken,
        uint256 usdtAmount,
        uint256 expectedTokens,
        address counterparty,
        uint256 expiresIn
    ) external override onlyVaultOrAdmin returns (uint256 orderId) {
        if (rwaToken == address(0)) revert ZeroAddress();
        if (counterparty == address(0)) revert ZeroAddress();
        if (usdtAmount == 0) revert ZeroAmount();
        if (expectedTokens == 0) revert ZeroAmount();
        if (!_whitelisted[counterparty]) revert CounterpartyNotWhitelisted(counterparty);

        orderId = ++_orderIdCounter;

        _orders[orderId] = OTCOrder({
            orderId: orderId,
            rwaToken: rwaToken,
            usdtAmount: usdtAmount,
            expectedTokens: expectedTokens,
            counterparty: counterparty,
            createdAt: block.timestamp,
            expiresAt: block.timestamp + expiresIn,
            status: OrderStatus.PENDING
        });

        _pendingOrdersByToken[rwaToken].push(orderId);

        emit OrderCreated(orderId, rwaToken, usdtAmount, expectedTokens, counterparty);
    }

    /// @inheritdoc IOTCManager
    function executePayment(uint256 orderId) external override onlyVaultOrAdmin {
        OTCOrder storage order = _orders[orderId];
        if (order.orderId == 0) revert OrderNotFound(orderId);
        if (order.status != OrderStatus.PENDING) {
            revert InvalidOrderStatus(orderId, order.status, OrderStatus.PENDING);
        }
        if (block.timestamp > order.expiresAt) revert OrderExpired(orderId);

        // Transfer USDT from vault to counterparty
        IERC20(usdt).safeTransferFrom(vault, order.counterparty, order.usdtAmount);

        order.status = OrderStatus.PAID;
        emit OrderPaid(orderId, order.usdtAmount);

        // Auto-deliver if enabled (for testing convenience)
        if (autoDeliverMode) {
            _autoDeliver(orderId);
        }
    }

    /// @inheritdoc IOTCManager
    function confirmDelivery(uint256 orderId, uint256 actualTokens) external override onlyVaultOrAdmin {
        OTCOrder storage order = _orders[orderId];
        if (order.orderId == 0) revert OrderNotFound(orderId);
        if (order.status != OrderStatus.PAID) {
            revert InvalidOrderStatus(orderId, order.status, OrderStatus.PAID);
        }

        order.status = OrderStatus.DELIVERED;
        _removeFromPending(order.rwaToken, orderId);

        emit OrderDelivered(orderId, actualTokens);
    }

    /// @inheritdoc IOTCManager
    function cancelOrder(uint256 orderId) external override onlyVaultOrAdmin {
        OTCOrder storage order = _orders[orderId];
        if (order.orderId == 0) revert OrderNotFound(orderId);
        if (order.status != OrderStatus.PENDING) {
            revert InvalidOrderStatus(orderId, order.status, OrderStatus.PENDING);
        }

        order.status = OrderStatus.CANCELLED;
        _removeFromPending(order.rwaToken, orderId);

        emit OrderCancelled(orderId);
    }

    /// @inheritdoc IOTCManager
    function getOrder(uint256 orderId) external view override returns (OTCOrder memory) {
        return _orders[orderId];
    }

    /// @inheritdoc IOTCManager
    function getPendingOrders(address rwaToken) external view override returns (uint256[] memory) {
        return _pendingOrdersByToken[rwaToken];
    }

    /// @inheritdoc IOTCManager
    function isWhitelisted(address counterparty) external view override returns (bool) {
        return _whitelisted[counterparty];
    }

    /// @inheritdoc IOTCManager
    function setWhitelist(address counterparty, bool status) external override onlyRole(ADMIN_ROLE) {
        if (counterparty == address(0)) revert ZeroAddress();
        _whitelisted[counterparty] = status;
        emit CounterpartyWhitelisted(counterparty, status);
    }

    // =============================================================================
    // Internal Functions
    // =============================================================================

    function _removeFromPending(address rwaToken, uint256 orderId) internal {
        uint256[] storage pending = _pendingOrdersByToken[rwaToken];
        for (uint256 i = 0; i < pending.length; i++) {
            if (pending[i] == orderId) {
                pending[i] = pending[pending.length - 1];
                pending.pop();
                break;
            }
        }
    }

    /// @notice Auto-deliver tokens from counterparty to vault
    function _autoDeliver(uint256 orderId) internal {
        OTCOrder storage order = _orders[orderId];
        
        // Transfer RWA tokens from counterparty to vault
        uint256 counterpartyBalance = IERC20(order.rwaToken).balanceOf(order.counterparty);
        uint256 toDeliver = order.expectedTokens;
        
        if (counterpartyBalance >= toDeliver) {
            // Only transfer if counterparty has approved this contract
            uint256 allowance = IERC20(order.rwaToken).allowance(order.counterparty, address(this));
            if (allowance >= toDeliver) {
                IERC20(order.rwaToken).safeTransferFrom(order.counterparty, vault, toDeliver);
                order.status = OrderStatus.DELIVERED;
                _removeFromPending(order.rwaToken, orderId);
                emit OrderDelivered(orderId, toDeliver);
            }
        }
    }

    // =============================================================================
    // Admin Functions
    // =============================================================================

    /// @notice Set vault address
    function setVault(address newVault) external onlyRole(ADMIN_ROLE) {
        if (newVault == address(0)) revert ZeroAddress();
        address oldVault = vault;
        vault = newVault;
        emit VaultUpdated(oldVault, newVault);
    }

    /// @notice Set auto-deliver mode
    function setAutoDeliverMode(bool enabled) external onlyRole(ADMIN_ROLE) {
        autoDeliverMode = enabled;
        emit AutoDeliverModeChanged(enabled);
    }

    /// @notice Batch whitelist counterparties
    function batchWhitelist(address[] calldata counterparties, bool status) external onlyRole(ADMIN_ROLE) {
        for (uint256 i = 0; i < counterparties.length; i++) {
            if (counterparties[i] != address(0)) {
                _whitelisted[counterparties[i]] = status;
                emit CounterpartyWhitelisted(counterparties[i], status);
            }
        }
    }

    /// @notice Manual deliver for testing (admin can trigger delivery manually)
    function manualDeliver(uint256 orderId, uint256 actualTokens) external onlyRole(ADMIN_ROLE) {
        OTCOrder storage order = _orders[orderId];
        if (order.orderId == 0) revert OrderNotFound(orderId);
        if (order.status != OrderStatus.PAID) {
            revert InvalidOrderStatus(orderId, order.status, OrderStatus.PAID);
        }

        // Admin directly transfers tokens to vault (for testing without counterparty)
        IERC20(order.rwaToken).safeTransferFrom(msg.sender, vault, actualTokens);

        order.status = OrderStatus.DELIVERED;
        _removeFromPending(order.rwaToken, orderId);

        emit OrderDelivered(orderId, actualTokens);
    }

    /// @notice Get order count
    function orderCount() external view returns (uint256) {
        return _orderIdCounter;
    }
}


