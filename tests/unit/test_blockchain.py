"""Tests for blockchain client layer."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.blockchain.client import BSCClient, ChainClient
from app.infrastructure.blockchain.contracts import ContractManager, VAULT_ABI
from app.infrastructure.blockchain.events import EventParser, EventType, ParsedEvent


class TestBSCClient:
    """Tests for BSCClient."""

    def test_client_initialization(self):
        """Test BSC client initializes with default settings."""
        with patch("app.infrastructure.blockchain.client.get_settings") as mock_settings:
            mock_settings.return_value.bsc_rpc_url = "https://bsc-dataseed.binance.org/"
            mock_settings.return_value.bsc_rpc_backup_urls = [
                "https://bsc-dataseed1.binance.org/"
            ]

            client = BSCClient()

            assert len(client.rpc_urls) == 2
            assert client.chain_id == 56
            assert client.max_retries == 3

    def test_client_with_custom_rpc(self):
        """Test BSC client with custom RPC URLs."""
        custom_rpcs = [
            "https://custom-rpc-1.example.com/",
            "https://custom-rpc-2.example.com/",
        ]

        with patch("app.infrastructure.blockchain.client.get_settings"):
            client = BSCClient(rpc_urls=custom_rpcs, chain_id=97)

            assert client.rpc_urls == custom_rpcs
            assert client.chain_id == 97

    def test_client_is_chain_client_subclass(self):
        """Test BSCClient is subclass of ChainClient."""
        assert issubclass(BSCClient, ChainClient)

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test health check returns True when RPC is healthy."""
        with patch("app.infrastructure.blockchain.client.get_settings") as mock_settings:
            mock_settings.return_value.bsc_rpc_url = "https://bsc-dataseed.binance.org/"
            mock_settings.return_value.bsc_rpc_backup_urls = []

            client = BSCClient()

            # Mock the _execute_with_failover method
            client._execute_with_failover = AsyncMock(return_value=12345678)

            result = await client.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check returns False when RPC fails."""
        with patch("app.infrastructure.blockchain.client.get_settings") as mock_settings:
            mock_settings.return_value.bsc_rpc_url = "https://bsc-dataseed.binance.org/"
            mock_settings.return_value.bsc_rpc_backup_urls = []

            client = BSCClient()

            # Mock failure
            client._execute_with_failover = AsyncMock(side_effect=Exception("RPC Error"))

            result = await client.health_check()

            assert result is False

    @pytest.mark.asyncio
    async def test_get_block_number(self):
        """Test get_block_number calls correct method."""
        with patch("app.infrastructure.blockchain.client.get_settings") as mock_settings:
            mock_settings.return_value.bsc_rpc_url = "https://bsc-dataseed.binance.org/"
            mock_settings.return_value.bsc_rpc_backup_urls = []

            client = BSCClient()
            client._execute_with_failover = AsyncMock(return_value=12345678)

            result = await client.get_block_number()

            assert result == 12345678
            client._execute_with_failover.assert_called_once_with("get_block_number")

    @pytest.mark.asyncio
    async def test_get_logs(self):
        """Test get_logs with filter parameters."""
        with patch("app.infrastructure.blockchain.client.get_settings") as mock_settings:
            mock_settings.return_value.bsc_rpc_url = "https://bsc-dataseed.binance.org/"
            mock_settings.return_value.bsc_rpc_backup_urls = []

            client = BSCClient()
            mock_logs = [{"blockNumber": 100, "data": "0x123"}]
            client._execute_with_failover = AsyncMock(return_value=mock_logs)

            result = await client.get_logs(
                from_block=100,
                to_block=200,
                address="0x1234567890123456789012345678901234567890",
            )

            assert result == mock_logs


class TestContractManager:
    """Tests for ContractManager."""

    def test_contract_manager_initialization(self):
        """Test contract manager initializes correctly."""
        mock_client = MagicMock()
        manager = ContractManager(mock_client)

        assert manager.client == mock_client
        assert manager.w3 is not None

    def test_encode_function_call(self):
        """Test encoding function call data."""
        mock_client = MagicMock()
        manager = ContractManager(mock_client)

        # Encode a simple function call
        data = manager.encode_function_call(VAULT_ABI, "sharePrice", [])

        # Should return bytes (function selector)
        assert isinstance(data, (bytes, str))

    def test_decode_function_result(self):
        """Test decoding function result."""
        mock_client = MagicMock()
        manager = ContractManager(mock_client)

        # Encode a uint256 value (1000000000000000000 = 1e18)
        # uint256 is encoded as 32 bytes
        encoded_value = (1000000000000000000).to_bytes(32, "big")

        result = manager.decode_function_result(VAULT_ABI, "sharePrice", encoded_value)

        assert result == 1000000000000000000

    def test_decode_function_not_found(self):
        """Test decoding with unknown function raises error."""
        mock_client = MagicMock()
        manager = ContractManager(mock_client)

        with pytest.raises(ValueError, match="Function unknown not found"):
            manager.decode_function_result(VAULT_ABI, "unknown", b"")

    @pytest.mark.asyncio
    async def test_call_contract(self):
        """Test calling contract function."""
        mock_client = AsyncMock()
        mock_client.eth_call = AsyncMock(
            return_value=(1000000000000000000).to_bytes(32, "big")
        )

        manager = ContractManager(mock_client)

        result = await manager.call_contract(
            "0x1234567890123456789012345678901234567890",
            VAULT_ABI,
            "sharePrice",
        )

        assert result == 1000000000000000000

    @pytest.mark.asyncio
    async def test_get_vault_state(self):
        """Test getting complete vault state."""
        mock_client = AsyncMock()

        # Mock responses for all vault functions
        responses = [
            (1000000000000000000).to_bytes(32, "big"),  # sharePrice
            (5000000000000000000000).to_bytes(32, "big"),  # effectiveSupply
            (100000000000000000000).to_bytes(32, "big"),  # totalRedemptionLiability
            (50000000000000000000).to_bytes(32, "big"),  # totalLockedShares
            (0).to_bytes(32, "big"),  # emergencyMode (false)
            (1000000000000000000000).to_bytes(32, "big"),  # layer1Liquidity
            (500000000000000000000).to_bytes(32, "big"),  # layer2Liquidity
            (2000000000000000000000).to_bytes(32, "big"),  # layer3Value
            (3500000000000000000000).to_bytes(32, "big"),  # totalAssets
            (5000000000000000000000).to_bytes(32, "big"),  # totalSupply
        ]

        mock_client.eth_call = AsyncMock(side_effect=responses)

        manager = ContractManager(mock_client)
        state = await manager.get_vault_state(
            "0x1234567890123456789012345678901234567890"
        )

        assert "share_price" in state
        assert "emergency_mode" in state
        assert "total_assets" in state
        assert state["share_price"] == 1000000000000000000


class TestEventParser:
    """Tests for EventParser."""

    def test_event_parser_initialization(self):
        """Test event parser initializes with topic map."""
        parser = EventParser()

        assert hasattr(parser, "topic_to_event")
        assert len(parser.topic_to_event) > 0

    def test_topic_map_contains_all_events(self):
        """Test topic map contains all defined event types."""
        parser = EventParser()

        # Check that we have topics for main event types
        event_types_found = set(parser.topic_to_event.values())

        assert EventType.DEPOSIT in event_types_found
        assert EventType.REDEMPTION_REQUESTED in event_types_found
        assert EventType.EMERGENCY_MODE_CHANGED in event_types_found

    def test_parse_log_unknown_topic(self):
        """Test parsing log with unknown topic returns None."""
        parser = EventParser()

        log = {
            "topics": [bytes.fromhex("0" * 64)],
            "data": b"",
            "blockNumber": 100,
            "logIndex": 0,
        }

        result = parser.parse_log(log)

        assert result is None

    def test_parse_log_empty_topics(self):
        """Test parsing log with empty topics returns None."""
        parser = EventParser()

        log = {"topics": [], "data": b"", "blockNumber": 100}

        result = parser.parse_log(log)

        assert result is None

    def test_decode_address_from_topic(self):
        """Test decoding address from indexed topic."""
        parser = EventParser()

        # Address padded to 32 bytes
        topic = bytes.fromhex(
            "0000000000000000000000001234567890123456789012345678901234567890"
        )

        result = parser._decode_address(topic)

        assert result == "0x1234567890123456789012345678901234567890"

    def test_decode_address_from_hex_string(self):
        """Test decoding address from hex string topic."""
        parser = EventParser()

        topic = "0x0000000000000000000000001234567890123456789012345678901234567890"

        result = parser._decode_address(topic)

        assert result == "0x1234567890123456789012345678901234567890"

    def test_parse_logs_multiple(self):
        """Test parsing multiple logs."""
        parser = EventParser()

        # Create mock logs (will return None since topics don't match known events)
        logs = [
            {"topics": [bytes.fromhex("0" * 64)], "data": b"", "blockNumber": 100},
            {"topics": [bytes.fromhex("1" * 64)], "data": b"", "blockNumber": 101},
        ]

        result = parser.parse_logs(logs)

        # Both should be filtered out as unknown events
        assert isinstance(result, list)

    def test_event_type_enum_values(self):
        """Test EventType enum has expected values."""
        assert EventType.DEPOSIT.value == "Deposit"
        assert EventType.WITHDRAW.value == "Withdraw"
        assert EventType.REDEMPTION_REQUESTED.value == "RedemptionRequested"
        assert EventType.REDEMPTION_APPROVED.value == "RedemptionApproved"
        assert EventType.EMERGENCY_MODE_CHANGED.value == "EmergencyModeChanged"

    def test_parsed_event_dataclass(self):
        """Test ParsedEvent dataclass creation."""
        event = ParsedEvent(
            event_type=EventType.DEPOSIT,
            tx_hash="0x123",
            block_number=100,
            log_index=0,
            block_timestamp=datetime.now(timezone.utc),
            contract_address="0x456",
            args={"sender": "0x789", "amount": 1000},
            raw_data={},
        )

        assert event.event_type == EventType.DEPOSIT
        assert event.block_number == 100
        assert event.args["sender"] == "0x789"


class TestEventDecoding:
    """Tests for specific event decoding functions."""

    def test_decode_deposit_event(self):
        """Test decoding Deposit event arguments."""
        parser = EventParser()

        # Simulate Deposit event topics and data
        # topics[0] = event signature (handled elsewhere)
        # topics[1] = indexed sender address
        # topics[2] = indexed owner address
        # data = assets (uint256) + shares (uint256)

        topics = [
            bytes.fromhex("0" * 64),  # event signature placeholder
            bytes.fromhex(
                "0000000000000000000000001111111111111111111111111111111111111111"
            ),  # sender
            bytes.fromhex(
                "0000000000000000000000002222222222222222222222222222222222222222"
            ),  # owner
        ]

        # assets = 1000, shares = 500 (each as uint256 = 32 bytes)
        data = (1000).to_bytes(32, "big") + (500).to_bytes(32, "big")

        result = parser._decode_deposit(topics, data)

        assert result["sender"] == "0x1111111111111111111111111111111111111111"
        assert result["owner"] == "0x2222222222222222222222222222222222222222"
        assert result["assets"] == 1000
        assert result["shares"] == 500

    def test_decode_deposit_event_empty_data(self):
        """Test decoding Deposit event with empty data."""
        parser = EventParser()

        topics = [
            bytes.fromhex("0" * 64),
            bytes.fromhex(
                "0000000000000000000000001111111111111111111111111111111111111111"
            ),
        ]

        result = parser._decode_deposit(topics, b"")

        assert result["assets"] == 0
        assert result["shares"] == 0

    def test_decode_emergency_mode_changed(self):
        """Test decoding EmergencyModeChanged event."""
        parser = EventParser()

        topics = []

        # enabled (bool) = true, triggeredBy (address)
        # bool is padded to 32 bytes, address is also 32 bytes
        data = (1).to_bytes(32, "big") + bytes.fromhex(
            "0000000000000000000000003333333333333333333333333333333333333333"
        )

        result = parser._decode_emergency_mode_changed(topics, data)

        assert result["enabled"] is True
        assert result["triggered_by"] == "0x3333333333333333333333333333333333333333"

    def test_decode_redemption_requested(self):
        """Test decoding RedemptionRequested event."""
        parser = EventParser()

        # topics[1] = indexed requestId
        # topics[2] = indexed owner
        topics = [
            bytes.fromhex("0" * 64),  # event signature
            (12345).to_bytes(32, "big"),  # requestId
            bytes.fromhex(
                "0000000000000000000000004444444444444444444444444444444444444444"
            ),  # owner
        ]

        # data = receiver (address) + shares (uint256) + grossAmount (uint256) + channel (uint8)
        # Note: uint8 is still padded to 32 bytes in ABI encoding
        data = (
            bytes.fromhex(
                "0000000000000000000000005555555555555555555555555555555555555555"
            )  # receiver
            + (1000).to_bytes(32, "big")  # shares
            + (2000).to_bytes(32, "big")  # grossAmount
            + (1).to_bytes(32, "big")  # channel
        )

        result = parser._decode_redemption_requested(topics, data)

        assert result["request_id"] == 12345
        assert result["owner"] == "0x4444444444444444444444444444444444444444"
        assert result["receiver"] == "0x5555555555555555555555555555555555555555"
        assert result["shares"] == 1000
        assert result["gross_amount"] == 2000
        assert result["channel"] == 1

    def test_decode_redemption_settled(self):
        """Test decoding RedemptionSettled event."""
        parser = EventParser()

        topics = [
            bytes.fromhex("0" * 64),  # event signature
            (99999).to_bytes(32, "big"),  # requestId
            bytes.fromhex(
                "0000000000000000000000006666666666666666666666666666666666666666"
            ),  # receiver
        ]

        # data = netAmount (uint256) + fee (uint256)
        data = (1500).to_bytes(32, "big") + (50).to_bytes(32, "big")

        result = parser._decode_redemption_settled(topics, data)

        assert result["request_id"] == 99999
        assert result["receiver"] == "0x6666666666666666666666666666666666666666"
        assert result["net_amount"] == 1500
        assert result["fee"] == 50
