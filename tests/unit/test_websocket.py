"""Tests for WebSocket service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.websocket import (
    ConnectionManager,
    MessageType,
    SubscriptionType,
    WebSocketClient,
    WebSocketMessage,
    get_connection_manager,
)


class TestWebSocketMessage:
    """Tests for WebSocket message schema."""

    def test_message_creation(self):
        """Test creating a message."""
        message = WebSocketMessage(
            type=MessageType.CONNECTED,
            data={"client_id": "test123"},
        )

        assert message.type == MessageType.CONNECTED
        assert message.data["client_id"] == "test123"
        assert message.timestamp is not None

    def test_message_with_error(self):
        """Test message with error."""
        message = WebSocketMessage(
            type=MessageType.ERROR,
            error="Something went wrong",
        )

        assert message.type == MessageType.ERROR
        assert message.error == "Something went wrong"

    def test_message_json_serialization(self):
        """Test message JSON serialization."""
        message = WebSocketMessage(
            type=MessageType.NAV_UPDATE,
            data={"nav": "1.0523"},
        )

        json_str = message.model_dump_json()
        assert "NAV_UPDATE" in json_str
        assert "1.0523" in json_str


class TestSubscriptionType:
    """Tests for subscription types."""

    def test_subscription_types(self):
        """Test subscription types exist."""
        assert SubscriptionType.NAV.value == "NAV"
        assert SubscriptionType.RISK.value == "RISK"
        assert SubscriptionType.ALERTS.value == "ALERTS"
        assert SubscriptionType.ALL.value == "ALL"


class TestWebSocketClient:
    """Tests for WebSocket client."""

    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket."""
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_client_creation(self, mock_websocket):
        """Test creating a client."""
        client = WebSocketClient(mock_websocket, "test-id")

        assert client.client_id == "test-id"
        assert client.subscriptions == set()
        assert client.connected_at is not None

    @pytest.mark.asyncio
    async def test_client_auto_id(self, mock_websocket):
        """Test client auto-generates ID."""
        client = WebSocketClient(mock_websocket)

        assert client.client_id is not None
        assert len(client.client_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_send_message(self, mock_websocket):
        """Test sending message to client."""
        client = WebSocketClient(mock_websocket)
        message = WebSocketMessage(type=MessageType.PING)

        result = await client.send_message(message)

        assert result is True
        mock_websocket.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_failure(self, mock_websocket):
        """Test handling send failure."""
        mock_websocket.send_text.side_effect = Exception("Connection lost")
        client = WebSocketClient(mock_websocket)
        message = WebSocketMessage(type=MessageType.PING)

        result = await client.send_message(message)

        assert result is False

    @pytest.mark.asyncio
    async def test_subscribe(self, mock_websocket):
        """Test subscribing to updates."""
        client = WebSocketClient(mock_websocket)

        client.subscribe(SubscriptionType.NAV)
        client.subscribe(SubscriptionType.RISK)

        assert SubscriptionType.NAV in client.subscriptions
        assert SubscriptionType.RISK in client.subscriptions
        assert len(client.subscriptions) == 2

    @pytest.mark.asyncio
    async def test_subscribe_all(self, mock_websocket):
        """Test subscribing to all updates."""
        client = WebSocketClient(mock_websocket)

        client.subscribe(SubscriptionType.ALL)

        assert SubscriptionType.NAV in client.subscriptions
        assert SubscriptionType.RISK in client.subscriptions
        assert SubscriptionType.ALERTS in client.subscriptions

    @pytest.mark.asyncio
    async def test_unsubscribe(self, mock_websocket):
        """Test unsubscribing from updates."""
        client = WebSocketClient(mock_websocket)
        client.subscribe(SubscriptionType.NAV)
        client.subscribe(SubscriptionType.RISK)

        client.unsubscribe(SubscriptionType.NAV)

        assert SubscriptionType.NAV not in client.subscriptions
        assert SubscriptionType.RISK in client.subscriptions

    @pytest.mark.asyncio
    async def test_unsubscribe_all(self, mock_websocket):
        """Test unsubscribing from all."""
        client = WebSocketClient(mock_websocket)
        client.subscribe(SubscriptionType.NAV)
        client.subscribe(SubscriptionType.RISK)

        client.unsubscribe(SubscriptionType.ALL)

        assert len(client.subscriptions) == 0

    @pytest.mark.asyncio
    async def test_is_subscribed(self, mock_websocket):
        """Test checking subscription status."""
        client = WebSocketClient(mock_websocket)
        client.subscribe(SubscriptionType.NAV)

        assert client.is_subscribed(SubscriptionType.NAV) is True
        assert client.is_subscribed(SubscriptionType.RISK) is False


class TestConnectionManager:
    """Tests for connection manager."""

    @pytest.fixture
    def manager(self):
        """Create fresh manager."""
        return ConnectionManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_connect(self, manager, mock_websocket):
        """Test connecting a client."""
        client = await manager.connect(mock_websocket)

        assert client is not None
        assert manager.active_connections == 1
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_id(self, manager, mock_websocket):
        """Test connecting with custom ID."""
        client = await manager.connect(mock_websocket, "custom-id")

        assert client.client_id == "custom-id"

    @pytest.mark.asyncio
    async def test_disconnect(self, manager, mock_websocket):
        """Test disconnecting a client."""
        client = await manager.connect(mock_websocket)

        await manager.disconnect(client.client_id)

        assert manager.active_connections == 0

    @pytest.mark.asyncio
    async def test_broadcast(self, manager, mock_websocket):
        """Test broadcasting to all clients."""
        await manager.connect(mock_websocket, "client1")

        mock_websocket2 = AsyncMock()
        mock_websocket2.accept = AsyncMock()
        mock_websocket2.send_text = AsyncMock()
        await manager.connect(mock_websocket2, "client2")

        message = WebSocketMessage(
            type=MessageType.SYSTEM_ANNOUNCEMENT,
            data={"message": "Hello everyone"},
        )

        count = await manager.broadcast(message)

        assert count == 2

    @pytest.mark.asyncio
    async def test_broadcast_with_subscription_filter(self, manager, mock_websocket):
        """Test broadcasting with subscription filter."""
        client1 = await manager.connect(mock_websocket, "client1")
        client1.subscribe(SubscriptionType.NAV)

        mock_websocket2 = AsyncMock()
        mock_websocket2.accept = AsyncMock()
        mock_websocket2.send_text = AsyncMock()
        client2 = await manager.connect(mock_websocket2, "client2")
        # client2 not subscribed to NAV

        # Reset call counts after connection messages
        mock_websocket.send_text.reset_mock()
        mock_websocket2.send_text.reset_mock()

        message = WebSocketMessage(type=MessageType.NAV_UPDATE, data={"nav": "1.0"})
        count = await manager.broadcast(message, SubscriptionType.NAV)

        assert count == 1
        mock_websocket.send_text.assert_called_once()
        mock_websocket2.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_nav_update(self, manager, mock_websocket):
        """Test broadcasting NAV update."""
        client = await manager.connect(mock_websocket, "client1")
        client.subscribe(SubscriptionType.NAV)

        count = await manager.broadcast_nav_update({"nav": "1.05"})

        assert count == 1

    @pytest.mark.asyncio
    async def test_broadcast_risk_update(self, manager, mock_websocket):
        """Test broadcasting risk update."""
        client = await manager.connect(mock_websocket, "client1")
        client.subscribe(SubscriptionType.RISK)

        count = await manager.broadcast_risk_update({"risk_score": 45})

        assert count == 1

    @pytest.mark.asyncio
    async def test_broadcast_alert(self, manager, mock_websocket):
        """Test broadcasting alert."""
        client = await manager.connect(mock_websocket, "client1")
        client.subscribe(SubscriptionType.ALERTS)

        count = await manager.broadcast_alert({"alert_id": "A001"})

        assert count == 1

    @pytest.mark.asyncio
    async def test_broadcast_emergency(self, manager, mock_websocket):
        """Test broadcasting emergency (ignores subscriptions)."""
        client = await manager.connect(mock_websocket, "client1")
        # Not subscribed to anything

        count = await manager.broadcast_emergency({"message": "Emergency!"})

        assert count == 1  # Should still receive emergency

    @pytest.mark.asyncio
    async def test_send_to_client(self, manager, mock_websocket):
        """Test sending to specific client."""
        client = await manager.connect(mock_websocket, "client1")
        message = WebSocketMessage(type=MessageType.PING)

        result = await manager.send_to_client("client1", message)

        assert result is True

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_client(self, manager):
        """Test sending to nonexistent client."""
        message = WebSocketMessage(type=MessageType.PING)

        result = await manager.send_to_client("nonexistent", message)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_client(self, manager, mock_websocket):
        """Test getting client by ID."""
        await manager.connect(mock_websocket, "client1")

        client = manager.get_client("client1")

        assert client is not None
        assert client.client_id == "client1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_client(self, manager):
        """Test getting nonexistent client."""
        client = manager.get_client("nonexistent")

        assert client is None

    @pytest.mark.asyncio
    async def test_get_subscribed_clients(self, manager, mock_websocket):
        """Test getting subscribed clients."""
        client1 = await manager.connect(mock_websocket, "client1")
        client1.subscribe(SubscriptionType.NAV)

        mock_websocket2 = AsyncMock()
        mock_websocket2.accept = AsyncMock()
        client2 = await manager.connect(mock_websocket2, "client2")
        client2.subscribe(SubscriptionType.RISK)

        nav_clients = manager.get_subscribed_clients(SubscriptionType.NAV)
        risk_clients = manager.get_subscribed_clients(SubscriptionType.RISK)

        assert "client1" in nav_clients
        assert "client2" in risk_clients

    @pytest.mark.asyncio
    async def test_get_stats(self, manager, mock_websocket):
        """Test getting connection stats."""
        client = await manager.connect(mock_websocket, "client1")
        client.subscribe(SubscriptionType.NAV)
        client.subscribe(SubscriptionType.RISK)

        stats = manager.get_stats()

        assert stats["active_connections"] == 1
        assert stats["subscription_counts"]["NAV"] == 1
        assert stats["subscription_counts"]["RISK"] == 1


class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_connection_manager_singleton(self):
        """Test singleton returns same instance."""
        # Reset singleton for test
        import app.services.websocket.manager as manager_module

        manager_module._connection_manager = None

        manager1 = get_connection_manager()
        manager2 = get_connection_manager()

        assert manager1 is manager2
