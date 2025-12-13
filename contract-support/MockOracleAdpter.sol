// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IOracleAdapter} from "../interfaces/IOracleAdapter.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title MockOracleAdapter
/// @notice Mock oracle adapter for testing purposes
/// @dev Allows setting prices for different assets to simulate oracle behavior
contract MockOracleAdapter is IOracleAdapter, AccessControl {
    // =============================================================================
    // State Variables
    // =============================================================================

    bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");

    /// @notice Price data for each asset
    struct PriceData {
        uint256 price;          // Price in USD with 18 decimals
        uint256 updatedAt;      // Timestamp of last update
        OracleSource source;    // Oracle source used
        bool isStale;           // Whether price is marked as stale
    }

    /// @notice Mapping from asset address to price data
    mapping(address => PriceData) private _prices;

    /// @notice Default price for assets not explicitly set (18 decimals)
    uint256 public defaultPrice;

    /// @notice Default staleness threshold in seconds (default: 1 hour)
    uint256 public stalenessThreshold;

    /// @notice Default oracle source
    OracleSource public defaultSource;

    // =============================================================================
    // Events
    // =============================================================================

    event PriceSet(address indexed asset, uint256 price, uint256 timestamp, OracleSource source);
    event DefaultPriceSet(uint256 price);
    event StalenessThresholdSet(uint256 threshold);
    event DefaultSourceSet(OracleSource source);

    // =============================================================================
    // Errors
    // =============================================================================

    error ZeroAddress();
    error ZeroPrice();

    // =============================================================================
    // Constructor
    // =============================================================================

    constructor(address admin_) {
        if (admin_ == address(0)) revert ZeroAddress();

        _grantRole(DEFAULT_ADMIN_ROLE, admin_);
        _grantRole(ADMIN_ROLE, admin_);

        // Default: 1 USD per token (18 decimals)
        defaultPrice = 1e18;
        stalenessThreshold = 1 hours;
        defaultSource = OracleSource.PRIMARY;
    }

    // =============================================================================
    // IOracleAdapter Implementation
    // =============================================================================

    /// @notice Get the price of an asset in USD (18 decimals)
    /// @param asset The token address to get price for
    /// @return price The price in USD with 18 decimals
    function getPrice(address asset) external view override returns (uint256 price) {
        PriceData memory data = _prices[asset];
        if (data.price != 0) {
            return data.price;
        }
        return defaultPrice;
    }

    /// @notice Get the price and timestamp of last update
    /// @param asset The token address to get price for
    /// @return price The price in USD with 18 decimals
    /// @return updatedAt Timestamp of last price update
    function getPriceWithTimestamp(address asset) external view override returns (uint256 price, uint256 updatedAt) {
        PriceData memory data = _prices[asset];
        if (data.price != 0) {
            return (data.price, data.updatedAt);
        }
        return (defaultPrice, block.timestamp);
    }

    /// @notice Get the price with full source information
    /// @param asset The token address to get price for
    /// @return price The price in USD with 18 decimals
    /// @return updatedAt Timestamp of last price update
    /// @return source The oracle source used
    function getPriceWithSource(address asset) external view override returns (uint256 price, uint256 updatedAt, OracleSource source) {
        PriceData memory data = _prices[asset];
        if (data.price != 0) {
            return (data.price, data.updatedAt, data.source);
        }
        return (defaultPrice, block.timestamp, defaultSource);
    }

    /// @notice Check if price data is stale
    /// @param asset The token address to check
    /// @return isStale True if price data is older than staleness threshold
    function isPriceStale(address asset) external view override returns (bool isStale) {
        PriceData memory data = _prices[asset];
        
        // If explicitly marked as stale, return true
        if (data.isStale) {
            return true;
        }

        // Check if timestamp is older than threshold
        uint256 timestamp = data.updatedAt != 0 ? data.updatedAt : block.timestamp;
        if (block.timestamp > timestamp && block.timestamp - timestamp > stalenessThreshold) {
            return true;
        }

        return false;
    }

    // =============================================================================
    // Admin Functions - Price Management
    // =============================================================================

    /// @notice Set price for a specific asset
    /// @param asset The token address
    /// @param price The price in USD with 18 decimals
    function setPrice(address asset, uint256 price) external onlyRole(ADMIN_ROLE) {
        if (asset == address(0)) revert ZeroAddress();
        if (price == 0) revert ZeroPrice();

        _prices[asset] = PriceData({
            price: price,
            updatedAt: block.timestamp,
            source: defaultSource,
            isStale: false
        });

        emit PriceSet(asset, price, block.timestamp, defaultSource);
    }

    /// @notice Set price with custom timestamp and source
    /// @param asset The token address
    /// @param price The price in USD with 18 decimals
    /// @param timestamp Custom timestamp for the price update
    /// @param source Custom oracle source
    function setPriceWithDetails(
        address asset,
        uint256 price,
        uint256 timestamp,
        OracleSource source
    ) external onlyRole(ADMIN_ROLE) {
        if (asset == address(0)) revert ZeroAddress();
        if (price == 0) revert ZeroPrice();

        _prices[asset] = PriceData({
            price: price,
            updatedAt: timestamp,
            source: source,
            isStale: false
        });

        emit PriceSet(asset, price, timestamp, source);
    }

    /// @notice Set multiple prices at once (batch operation)
    /// @param assets Array of token addresses
    /// @param prices Array of prices (18 decimals)
    function setPrices(address[] calldata assets, uint256[] calldata prices) external onlyRole(ADMIN_ROLE) {
        if (assets.length != prices.length) revert("Arrays length mismatch");

        for (uint256 i = 0; i < assets.length;) {
            if (assets[i] == address(0)) revert ZeroAddress();
            if (prices[i] == 0) revert ZeroPrice();

            _prices[assets[i]] = PriceData({
                price: prices[i],
                updatedAt: block.timestamp,
                source: defaultSource,
                isStale: false
            });

            emit PriceSet(assets[i], prices[i], block.timestamp, defaultSource);

            unchecked { ++i; }
        }
    }

    /// @notice Mark a price as stale
    /// @param asset The token address
    /// @param stale Whether the price should be marked as stale
    function setPriceStale(address asset, bool stale) external onlyRole(ADMIN_ROLE) {
        if (asset == address(0)) revert ZeroAddress();

        PriceData storage data = _prices[asset];
        if (data.price == 0) {
            // If price not set, use default
            data.price = defaultPrice;
            data.updatedAt = block.timestamp;
            data.source = defaultSource;
        }
        data.isStale = stale;
    }

    /// @notice Remove price for an asset (will use default price)
    /// @param asset The token address
    function removePrice(address asset) external onlyRole(ADMIN_ROLE) {
        if (asset == address(0)) revert ZeroAddress();
        delete _prices[asset];
    }

    /// @notice Set default price for assets not explicitly configured
    /// @param price The default price in USD with 18 decimals
    function setDefaultPrice(uint256 price) external onlyRole(ADMIN_ROLE) {
        if (price == 0) revert ZeroPrice();
        defaultPrice = price;
        emit DefaultPriceSet(price);
    }

    /// @notice Set staleness threshold
    /// @param threshold The staleness threshold in seconds
    function setStalenessThreshold(uint256 threshold) external onlyRole(ADMIN_ROLE) {
        stalenessThreshold = threshold;
        emit StalenessThresholdSet(threshold);
    }

    /// @notice Set default oracle source
    /// @param source The default oracle source
    function setDefaultSource(OracleSource source) external onlyRole(ADMIN_ROLE) {
        defaultSource = source;
        emit DefaultSourceSet(source);
    }

    // =============================================================================
    // View Functions
    // =============================================================================

    /// @notice Get full price data for an asset
    /// @param asset The token address
    /// @return data The complete price data structure
    function getPriceData(address asset) external view returns (PriceData memory data) {
        data = _prices[asset];
        if (data.price == 0) {
            data.price = defaultPrice;
            data.updatedAt = block.timestamp;
            data.source = defaultSource;
            data.isStale = false;
        }
    }
}