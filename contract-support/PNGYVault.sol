// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC4626} from "@openzeppelin/contracts/token/ERC20/extensions/ERC4626.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC20Metadata} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {PNGYTypes} from "./PNGYTypes.sol";
import {IPNGYVault, IAssetController} from "./IPNGYContracts.sol";

/// @title PNGYVault
/// @author Paimon Yield Protocol
/// @notice FoF (Fund of Funds) Vault - ERC4626 核心合约
/// @dev 赎回操作直接调用 RedemptionManager，资产操作直接调用 AssetController
contract PNGYVault is ERC4626, AccessControl, Pausable, ReentrancyGuard, IPNGYVault {
    using SafeERC20 for IERC20;

    // =============================================================================
    // Roles
    // =============================================================================
    
    bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");
    /// @notice 授权合约角色（RedemptionManager 和 AssetController）
    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");

    // =============================================================================
    // State Variables
    // =============================================================================
    
    /// @notice 资产控制器（用于计算资产价值）
    IAssetController public assetController;
    
    /// @notice 赎回负债总额
    uint256 public override totalRedemptionLiability;
    
    /// @notice 锁定份额总额
    uint256 public override totalLockedShares;
    
    /// @notice 可提取的赎回手续费
    uint256 public override withdrawableRedemptionFees;
    
    /// @notice 历史累计赎回手续费
    uint256 public totalAccumulatedRedemptionFees;
    
    /// @notice 紧急模式
    bool public override emergencyMode;
    
    /// @notice 每个用户的锁定份额
    mapping(address => uint256) public override lockedSharesOf;
    
    /// @notice 最后 NAV 更新时间
    uint256 public lastNavUpdate;

    // =============================================================================
    // Events
    // =============================================================================
    
    event DepositProcessed(address indexed sender, address indexed receiver, uint256 assets, uint256 shares);
    event AssetControllerUpdated(address indexed oldController, address indexed newController);
    event EmergencyModeChanged(bool enabled);
    event SharesLocked(address indexed owner, uint256 shares);
    event SharesUnlocked(address indexed owner, uint256 shares);
    event SharesBurned(address indexed owner, uint256 shares);
    event RedemptionFeeAdded(uint256 fee);
    event RedemptionFeeReduced(uint256 fee);
    event NavUpdated(uint256 oldNav, uint256 newNav, uint256 timestamp);

    // =============================================================================
    // Errors
    // =============================================================================
    
    error ZeroAddress();
    error ZeroAmount();
    error DepositBelowMinimum(uint256 amount, uint256 minimum);
    error InsufficientShares(uint256 available, uint256 required);
    error OnlyOperator();
    error AssetControllerNotSet();

    // =============================================================================
    // Modifiers
    // =============================================================================
    
    modifier onlyOperator() {
        if (!hasRole(OPERATOR_ROLE, msg.sender)) revert OnlyOperator();
        _;
    }

    // =============================================================================
    // Constructor
    // =============================================================================
    
    constructor(
        IERC20 asset_,
        address admin_
    ) ERC4626(asset_) ERC20("PPT  Token", "PPT") {
        if (admin_ == address(0)) revert ZeroAddress();
        
        _grantRole(DEFAULT_ADMIN_ROLE, admin_);
        _grantRole(ADMIN_ROLE, admin_);
        
        lastNavUpdate = block.timestamp;
    }

    // =============================================================================
    // ERC4626 Core - View Functions
    // =============================================================================
    
    /// @notice 计算总资产（扣除负债和手续费）
    function totalAssets() public view override returns (uint256) {
        uint256 grossValue = _getGrossAssets();
        
        // 扣除赎回负债
        if (totalRedemptionLiability >= grossValue) return 0;
        uint256 netValue = grossValue - totalRedemptionLiability;
        
        // 扣除待提取手续费
        if (withdrawableRedemptionFees >= netValue) return 0;
        return netValue - withdrawableRedemptionFees;
    }
    
    /// @notice 有效流通份额（排除锁定份额）
    function effectiveSupply() public view override returns (uint256) {
        uint256 total = totalSupply();
        if (totalLockedShares >= total) return 0;
        return total - totalLockedShares;
    }
    
    /// @notice 每份额价格
    function sharePrice() public view override returns (uint256) {
        uint256 supply = effectiveSupply();
        if (supply == 0) return PNGYTypes.PRECISION;
        return (totalAssets() * PNGYTypes.PRECISION) / supply;
    }
    
    /// @notice 总资产（不扣除负债）
    function grossAssets() public view returns (uint256) {
        return _getGrossAssets();
    }
    
    function _getGrossAssets() internal view returns (uint256) {
        uint256 cashValue = IERC20(asset()).balanceOf(address(this));
        uint256 assetValue = address(assetController) != address(0) 
            ? assetController.calculateAssetValue() 
            : 0;
        return cashValue + assetValue;
    }

    // =============================================================================
    // ERC4626 Core - Deposit Functions
    // =============================================================================
    
    function deposit(
        uint256 assets,
        address receiver
    ) public override nonReentrant whenNotPaused returns (uint256 shares) {
        if (assets == 0) revert ZeroAmount();
        if (assets < PNGYTypes.MIN_DEPOSIT) revert DepositBelowMinimum(assets, PNGYTypes.MIN_DEPOSIT);
        if (receiver == address(0)) revert ZeroAddress();
        
        shares = previewDeposit(assets);
        
        IERC20(asset()).safeTransferFrom(msg.sender, address(this), assets);
        _mint(receiver, shares);
        
        emit Deposit(msg.sender, receiver, assets, shares);
        emit DepositProcessed(msg.sender, receiver, assets, shares);
    }
    
    function mint(
        uint256 shares,
        address receiver
    ) public override nonReentrant whenNotPaused returns (uint256 assets) {
        if (shares == 0) revert ZeroAmount();
        if (receiver == address(0)) revert ZeroAddress();
        
        assets = previewMint(shares);
        if (assets < PNGYTypes.MIN_DEPOSIT) revert DepositBelowMinimum(assets, PNGYTypes.MIN_DEPOSIT);
        
        IERC20(asset()).safeTransferFrom(msg.sender, address(this), assets);
        _mint(receiver, shares);
        
        emit Deposit(msg.sender, receiver, assets, shares);
        emit DepositProcessed(msg.sender, receiver, assets, shares);
    }
    
    /// @notice 禁用直接 withdraw - 使用 RedemptionManager
    function withdraw(uint256, address, address) public pure override returns (uint256) {
        revert("Use Redemption");
    }
    
    /// @notice 禁用直接 redeem - 使用 RedemptionManager
    function redeem(uint256, address, address) public pure override returns (uint256) {
        revert("Use Redemption");
    }

    // =============================================================================
    // Liquidity View Functions
    // =============================================================================
    
    function getLayer1Liquidity() public view override returns (uint256) {
        return getLayer1Cash() + getLayer1YieldAssets();
    }
    
    function getLayer1Cash() public view override returns (uint256) {
        return IERC20(asset()).balanceOf(address(this));
    }
    
    function getLayer1YieldAssets() public view override returns (uint256) {
        if (address(assetController) == address(0)) return 0;
        uint256 l1Total = assetController.getLayerValue(PNGYTypes.LiquidityTier.TIER_1_CASH);
        uint256 cash = getLayer1Cash();
        return l1Total > cash ? l1Total - cash : 0;
    }
    
    function getLayer2Liquidity() public view override returns (uint256) {
        if (address(assetController) == address(0)) return 0;
        return assetController.getLayerValue(PNGYTypes.LiquidityTier.TIER_2_MMF);
    }
    
    function getLayer3Value() public view override returns (uint256) {
        if (address(assetController) == address(0)) return 0;
        return assetController.getLayerValue(PNGYTypes.LiquidityTier.TIER_3_HYD);
    }
    
    function getAvailableLiquidity() public view override returns (uint256) {
        return getLayer1Liquidity() + getLayer2Liquidity();
    }
    
    function getVaultState() external view override returns (PNGYTypes.VaultState memory state) {
        state.totalAssets = totalAssets();
        state.totalSupply = totalSupply();
        state.sharePrice = sharePrice();
        state.layer1Liquidity = getLayer1Liquidity();
        state.layer2Liquidity = getLayer2Liquidity();
        state.layer3Value = getLayer3Value();
        state.totalRedemptionLiability = totalRedemptionLiability;
        state.totalLockedShares = totalLockedShares;
        state.emergencyMode = emergencyMode;
    }
    
    function getLiquidityBreakdown() external view returns (
        uint256 layer1Cash,
        uint256 layer1Yield,
        uint256 layer2MMF,
        uint256 layer3HYD
    ) {
        layer1Cash = getLayer1Cash();
        layer1Yield = getLayer1YieldAssets();
        layer2MMF = getLayer2Liquidity();
        layer3HYD = getLayer3Value();
    }

    // =============================================================================
    // Operator Functions (供 RedemptionManager / AssetController 调用)
    // =============================================================================
    
    function lockShares(address owner, uint256 shares) external override onlyOperator {
        uint256 available = balanceOf(owner);
        if (available < shares) revert InsufficientShares(available, shares);
        
        _transfer(owner, address(this), shares);
        totalLockedShares += shares;
        lockedSharesOf[owner] += shares;
        
        emit SharesLocked(owner, shares);
    }
    
    function unlockShares(address owner, uint256 shares) external override onlyOperator {
        _transfer(address(this), owner, shares);
        totalLockedShares -= shares;
        lockedSharesOf[owner] -= shares;
        
        emit SharesUnlocked(owner, shares);
    }
    
    function burnLockedShares(address owner, uint256 shares) external override onlyOperator {
        _burn(address(this), shares);
        totalLockedShares -= shares;
        lockedSharesOf[owner] -= shares;
        
        emit SharesBurned(owner, shares);
    }
    
    function addRedemptionLiability(uint256 amount) external override onlyOperator {
        totalRedemptionLiability += amount;
    }
    
    function removeRedemptionLiability(uint256 amount) external override onlyOperator {
        totalRedemptionLiability -= amount;
    }
    
    function addRedemptionFee(uint256 fee) external override onlyOperator {
        totalAccumulatedRedemptionFees += fee;
        withdrawableRedemptionFees += fee;
        emit RedemptionFeeAdded(fee);
    }
    
    function reduceRedemptionFee(uint256 fee) external override onlyOperator {
        withdrawableRedemptionFees -= fee;
        emit RedemptionFeeReduced(fee);
    }
    
    function transferAssetTo(address to, uint256 amount) external override onlyOperator {
        IERC20(asset()).safeTransfer(to, amount);
    }
    
    function getAssetBalance(address token) external view override returns (uint256) {
        return IERC20(token).balanceOf(address(this));
    }
    
    function approveAsset(address token, address spender, uint256 amount) external override onlyOperator {
        IERC20(token).safeIncreaseAllowance(spender, amount);
    }

    // =============================================================================
    // Admin Functions
    // =============================================================================
    
    function setAssetController(address controller) external onlyRole(ADMIN_ROLE) {
        address old = address(assetController);
        assetController = IAssetController(controller);
        emit AssetControllerUpdated(old, controller);
    }
    
    /// @notice 授权 RedemptionManager 或 AssetController 操作 Vault
    function grantOperator(address operator) external onlyRole(ADMIN_ROLE) {
        _grantRole(OPERATOR_ROLE, operator);
    }
    
    /// @notice 撤销操作权限
    function revokeOperator(address operator) external onlyRole(ADMIN_ROLE) {
        _revokeRole(OPERATOR_ROLE, operator);
    }
    
    function setEmergencyMode(bool enabled) external onlyRole(ADMIN_ROLE) {
        emergencyMode = enabled;
        emit EmergencyModeChanged(enabled);
    }
    
    function pause() external onlyRole(ADMIN_ROLE) {
        _pause();
    }
    
    function unpause() external onlyRole(ADMIN_ROLE) {
        _unpause();
    }
    
    /// @notice 紧急提取（仅限紧急模式）
    function emergencyWithdraw(address token, address to, uint256 amount) external onlyRole(ADMIN_ROLE) {
        require(emergencyMode, "Not in emergency mode");
        IERC20(token).safeTransfer(to, amount);
    }
    
    /// @notice 更新 NAV（用于记录）
    function updateNav() external {
        uint256 oldNav = sharePrice();
        lastNavUpdate = block.timestamp;
        uint256 newNav = sharePrice();
        emit NavUpdated(oldNav, newNav, block.timestamp);
    }
}