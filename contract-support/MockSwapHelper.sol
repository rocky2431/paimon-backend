// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {ISwapHelper} from "../interfaces/ISwapHelper.sol";

/// @title MockSwapHelper
/// @author Paimon Yield Protocol
/// @notice Mock implementation of ISwapHelper for testing
/// @dev Simulates DEX swaps using configurable exchange rates, no real DEX needed
contract MockSwapHelper is ISwapHelper, AccessControl, ReentrancyGuard {
    using SafeERC20 for IERC20;

    // =============================================================================
    // Constants
    // =============================================================================

    bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");
    uint256 public constant MAX_ALLOWED_SLIPPAGE = 200;
    uint256 public constant BASIS_POINTS = 10000;
    uint256 public constant PRECISION = 1e18;

    // =============================================================================
    // State Variables
    // =============================================================================

    /// @notice Mock router address (not actually used, just for interface compliance)
    address public override router;

    /// @notice Default max slippage in basis points
    uint256 public override defaultMaxSlippage;

    /// @notice Exchange rates: tokenIn => tokenOut => rate (PRECISION = 1:1)
    /// @dev rate = how many tokenOut per 1 tokenIn (scaled by PRECISION)
    mapping(address => mapping(address => uint256)) public exchangeRates;

    /// @notice Default exchange rate if not configured (1:1)
    uint256 public defaultExchangeRate;

    /// @notice Mock: simulate slippage (basis points, 0 = no slippage)
    uint256 public mockSlippage;

    /// @notice Whether to fail swaps (for testing error cases)
    bool public shouldFail;

    // =============================================================================
    // Events (additional for testing)
    // =============================================================================

    event ExchangeRateSet(address indexed tokenIn, address indexed tokenOut, uint256 rate);
    event DefaultExchangeRateSet(uint256 rate);
    event MockSlippageSet(uint256 slippage);
    event ShouldFailSet(bool shouldFail);

    // =============================================================================
    // Constructor
    // =============================================================================

    constructor(address admin_) {
        if (admin_ == address(0)) revert ZeroAddress();

        _grantRole(DEFAULT_ADMIN_ROLE, admin_);
        _grantRole(ADMIN_ROLE, admin_);

        router = address(this); // Self as mock router
        defaultMaxSlippage = 100; // 1% default
        defaultExchangeRate = PRECISION; // 1:1 default
        mockSlippage = 0; // No simulated slippage by default
        shouldFail = false;
    }

    // =============================================================================
    // ISwapHelper Implementation
    // =============================================================================

    /// @inheritdoc ISwapHelper
    function buyRWAAsset(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 maxSlippage
    ) external override nonReentrant returns (uint256 amountOut) {
        return _swap(tokenIn, tokenOut, amountIn, maxSlippage, msg.sender);
    }

    /// @inheritdoc ISwapHelper
    function sellRWAAsset(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 maxSlippage
    ) external override nonReentrant returns (uint256 amountOut) {
        return _swap(tokenIn, tokenOut, amountIn, maxSlippage, msg.sender);
    }

    /// @inheritdoc ISwapHelper
    function getAmountOut(
        address tokenIn,
        address tokenOut,
        uint256 amountIn
    ) public view override returns (uint256 amountOut) {
        if (amountIn == 0) return 0;

        uint256 rate = exchangeRates[tokenIn][tokenOut];
        if (rate == 0) {
            rate = defaultExchangeRate;
        }

        // Calculate output: amountIn * rate / PRECISION
        amountOut = (amountIn * rate) / PRECISION;
    }

    // =============================================================================
    // Internal Functions
    // =============================================================================

    function _swap(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 maxSlippage,
        address recipient
    ) internal returns (uint256 amountOut) {
        // Revert if shouldFail is set
        require(!shouldFail, "MockSwapHelper: swap failed");

        // Validate inputs
        if (tokenIn == address(0) || tokenOut == address(0)) revert ZeroAddress();
        if (amountIn == 0) revert ZeroInputAmount();
        if (maxSlippage > MAX_ALLOWED_SLIPPAGE) {
            revert SlippageTooHigh(maxSlippage, MAX_ALLOWED_SLIPPAGE);
        }

        if (maxSlippage == 0) {
            maxSlippage = defaultMaxSlippage;
        }

        // Calculate expected output
        uint256 expectedOut = getAmountOut(tokenIn, tokenOut, amountIn);
        if (expectedOut == 0) revert ZeroOutputAmount();

        // Apply mock slippage
        amountOut = expectedOut;
        if (mockSlippage > 0) {
            amountOut = (expectedOut * (BASIS_POINTS - mockSlippage)) / BASIS_POINTS;
        }

        // Check slippage tolerance
        uint256 minAmountOut = (expectedOut * (BASIS_POINTS - maxSlippage)) / BASIS_POINTS;
        if (amountOut < minAmountOut) {
            revert SlippageExceeded(expectedOut, amountOut, maxSlippage);
        }

        // Transfer tokens
        IERC20(tokenIn).safeTransferFrom(msg.sender, address(this), amountIn);
        
        // Check if we have enough tokenOut to send
        uint256 balance = IERC20(tokenOut).balanceOf(address(this));
        require(balance >= amountOut, "MockSwapHelper: insufficient output token balance");
        
        IERC20(tokenOut).safeTransfer(recipient, amountOut);

        emit TokensSwapped(tokenIn, tokenOut, amountIn, amountOut, recipient);
    }

    // =============================================================================
    // Admin Functions
    // =============================================================================

    /// @notice Set exchange rate between two tokens
    /// @param tokenIn Input token address
    /// @param tokenOut Output token address
    /// @param rate Exchange rate (PRECISION = 1:1)
    function setExchangeRate(address tokenIn, address tokenOut, uint256 rate) external onlyRole(ADMIN_ROLE) {
        exchangeRates[tokenIn][tokenOut] = rate;
        emit ExchangeRateSet(tokenIn, tokenOut, rate);
    }

    /// @notice Set exchange rates for multiple pairs
    /// @param tokensIn Array of input tokens
    /// @param tokensOut Array of output tokens
    /// @param rates Array of exchange rates
    function setExchangeRates(
        address[] calldata tokensIn,
        address[] calldata tokensOut,
        uint256[] calldata rates
    ) external onlyRole(ADMIN_ROLE) {
        require(tokensIn.length == tokensOut.length && tokensOut.length == rates.length, "Length mismatch");
        
        for (uint256 i = 0; i < tokensIn.length; i++) {
            exchangeRates[tokensIn[i]][tokensOut[i]] = rates[i];
            emit ExchangeRateSet(tokensIn[i], tokensOut[i], rates[i]);
        }
    }

    /// @notice Set bidirectional exchange rate (A->B and B->A)
    /// @param tokenA First token
    /// @param tokenB Second token
    /// @param rateAtoB Rate from A to B (PRECISION = 1:1)
    function setBidirectionalRate(address tokenA, address tokenB, uint256 rateAtoB) external onlyRole(ADMIN_ROLE) {
        exchangeRates[tokenA][tokenB] = rateAtoB;
        // Inverse rate: B to A = PRECISION^2 / rateAtoB
        uint256 rateBtoA = (PRECISION * PRECISION) / rateAtoB;
        exchangeRates[tokenB][tokenA] = rateBtoA;
        
        emit ExchangeRateSet(tokenA, tokenB, rateAtoB);
        emit ExchangeRateSet(tokenB, tokenA, rateBtoA);
    }

    /// @notice Set default exchange rate
    function setDefaultExchangeRate(uint256 rate) external onlyRole(ADMIN_ROLE) {
        defaultExchangeRate = rate;
        emit DefaultExchangeRateSet(rate);
    }

    /// @notice Set mock slippage for testing
    function setMockSlippage(uint256 slippage) external onlyRole(ADMIN_ROLE) {
        require(slippage <= MAX_ALLOWED_SLIPPAGE, "Slippage too high");
        mockSlippage = slippage;
        emit MockSlippageSet(slippage);
    }

    /// @notice Set whether swaps should fail
    function setShouldFail(bool fail) external onlyRole(ADMIN_ROLE) {
        shouldFail = fail;
        emit ShouldFailSet(fail);
    }

    /// @notice Update default max slippage
    function setDefaultMaxSlippage(uint256 newSlippage) external onlyRole(ADMIN_ROLE) {
        if (newSlippage > MAX_ALLOWED_SLIPPAGE) {
            revert SlippageTooHigh(newSlippage, MAX_ALLOWED_SLIPPAGE);
        }

        uint256 oldSlippage = defaultMaxSlippage;
        defaultMaxSlippage = newSlippage;

        emit MaxSlippageUpdated(oldSlippage, newSlippage);
    }

    /// @notice Update router address (for interface compliance)
    function setRouter(address newRouter) external onlyRole(ADMIN_ROLE) {
        if (newRouter == address(0)) revert ZeroAddress();

        address oldRouter = router;
        router = newRouter;

        emit RouterUpdated(oldRouter, newRouter);
    }

    /// @notice Deposit tokens for swap output (admin funds the mock)
    /// @param token Token to deposit
    /// @param amount Amount to deposit
    function depositToken(address token, uint256 amount) external {
        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);
    }

    /// @notice Withdraw tokens from the mock
    function withdrawToken(address token, uint256 amount) external onlyRole(ADMIN_ROLE) {
        IERC20(token).safeTransfer(msg.sender, amount);
    }

    /// @notice Withdraw all of a token
    function withdrawAllToken(address token) external onlyRole(ADMIN_ROLE) {
        uint256 balance = IERC20(token).balanceOf(address(this));
        if (balance > 0) {
            IERC20(token).safeTransfer(msg.sender, balance);
        }
    }
}
