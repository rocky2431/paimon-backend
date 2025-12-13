"""WebSocket connection manager for real-time updates."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

from app.services.websocket.schemas import (
    MessageType,
    SubscriptionType,
    WebSocketMessage,
)

logger = logging.getLogger(__name__)


class WebSocketClient:
    """Represents a connected WebSocket client."""

    def __init__(self, websocket: WebSocket, client_id: str | None = None):
        """Initialize client.

        Args:
            websocket: The WebSocket connection
            client_id: Optional client identifier
        """
        self.websocket = websocket
        self.client_id = client_id or str(uuid4())
        self.subscriptions: set[SubscriptionType] = set()
        self.connected_at = datetime.now()
        self.last_activity = datetime.now()
        self._lock = asyncio.Lock()

    async def send_message(self, message: WebSocketMessage) -> bool:
        """Send message to client.

        Args:
            message: Message to send

        Returns:
            True if sent successfully
        """
        try:
            async with self._lock:
                await self.websocket.send_text(message.model_dump_json())
                self.last_activity = datetime.now()
                return True
        except Exception as e:
            logger.warning(f"Failed to send to {self.client_id}: {e}")
            return False

    async def send_json(self, data: dict[str, Any]) -> bool:
        """Send JSON data to client.

        Args:
            data: Dictionary to send

        Returns:
            True if sent successfully
        """
        try:
            async with self._lock:
                await self.websocket.send_json(data)
                self.last_activity = datetime.now()
                return True
        except Exception as e:
            logger.warning(f"Failed to send JSON to {self.client_id}: {e}")
            return False

    def subscribe(self, subscription_type: SubscriptionType) -> None:
        """Subscribe to updates.

        Args:
            subscription_type: Type to subscribe to
        """
        if subscription_type == SubscriptionType.ALL:
            self.subscriptions = set(SubscriptionType)
            self.subscriptions.discard(SubscriptionType.ALL)
        else:
            self.subscriptions.add(subscription_type)

    def unsubscribe(self, subscription_type: SubscriptionType) -> None:
        """Unsubscribe from updates.

        Args:
            subscription_type: Type to unsubscribe from
        """
        if subscription_type == SubscriptionType.ALL:
            self.subscriptions.clear()
        else:
            self.subscriptions.discard(subscription_type)

    def is_subscribed(self, subscription_type: SubscriptionType) -> bool:
        """Check if subscribed to type.

        Args:
            subscription_type: Type to check

        Returns:
            True if subscribed
        """
        return subscription_type in self.subscriptions


class ConnectionManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self):
        """Initialize connection manager."""
        self._clients: dict[str, WebSocketClient] = {}
        self._lock = asyncio.Lock()

    @property
    def active_connections(self) -> int:
        """Get number of active connections."""
        return len(self._clients)

    async def connect(self, websocket: WebSocket, client_id: str | None = None) -> WebSocketClient:
        """Accept new WebSocket connection.

        Args:
            websocket: The WebSocket connection
            client_id: Optional client identifier

        Returns:
            The connected client
        """
        await websocket.accept()

        client = WebSocketClient(websocket, client_id)

        async with self._lock:
            self._clients[client.client_id] = client

        logger.info(f"Client {client.client_id} connected. Active: {self.active_connections}")

        # Send welcome message
        await client.send_message(
            WebSocketMessage(
                type=MessageType.CONNECTED,
                data={"client_id": client.client_id, "message": "Connected successfully"},
            )
        )

        return client

    async def disconnect(self, client_id: str) -> None:
        """Disconnect a client.

        Args:
            client_id: Client to disconnect
        """
        async with self._lock:
            if client_id in self._clients:
                del self._clients[client_id]
                logger.info(f"Client {client_id} disconnected. Active: {self.active_connections}")

    async def broadcast(
        self,
        message: WebSocketMessage,
        subscription_type: SubscriptionType | None = None,
    ) -> int:
        """Broadcast message to all clients.

        Args:
            message: Message to broadcast
            subscription_type: Only send to subscribed clients

        Returns:
            Number of clients that received the message
        """
        sent_count = 0
        disconnected = []

        async with self._lock:
            clients = list(self._clients.values())

        for client in clients:
            # Check subscription if specified
            if subscription_type and not client.is_subscribed(subscription_type):
                continue

            success = await client.send_message(message)
            if success:
                sent_count += 1
            else:
                disconnected.append(client.client_id)

        # Clean up disconnected clients
        for client_id in disconnected:
            await self.disconnect(client_id)

        return sent_count

    async def broadcast_nav_update(self, data: dict[str, Any]) -> int:
        """Broadcast NAV update.

        Args:
            data: NAV update data

        Returns:
            Number of clients notified
        """
        message = WebSocketMessage(
            type=MessageType.NAV_UPDATE,
            data=data,
        )
        return await self.broadcast(message, SubscriptionType.NAV)

    async def broadcast_risk_update(self, data: dict[str, Any]) -> int:
        """Broadcast risk update.

        Args:
            data: Risk update data

        Returns:
            Number of clients notified
        """
        message = WebSocketMessage(
            type=MessageType.RISK_UPDATE,
            data=data,
        )
        return await self.broadcast(message, SubscriptionType.RISK)

    async def broadcast_alert(self, data: dict[str, Any]) -> int:
        """Broadcast alert.

        Args:
            data: Alert data

        Returns:
            Number of clients notified
        """
        message = WebSocketMessage(
            type=MessageType.ALERT_UPDATE,
            data=data,
        )
        return await self.broadcast(message, SubscriptionType.ALERTS)

    async def broadcast_flow_update(self, data: dict[str, Any]) -> int:
        """Broadcast flow update.

        Args:
            data: Flow update data

        Returns:
            Number of clients notified
        """
        message = WebSocketMessage(
            type=MessageType.FLOW_UPDATE,
            data=data,
        )
        return await self.broadcast(message, SubscriptionType.FLOWS)

    async def broadcast_rebalance_update(self, data: dict[str, Any]) -> int:
        """Broadcast rebalance update.

        Args:
            data: Rebalance update data

        Returns:
            Number of clients notified
        """
        message = WebSocketMessage(
            type=MessageType.REBALANCE_UPDATE,
            data=data,
        )
        return await self.broadcast(message, SubscriptionType.REBALANCE)

    async def broadcast_redemption_update(self, data: dict[str, Any]) -> int:
        """Broadcast redemption update.

        Args:
            data: Redemption update data

        Returns:
            Number of clients notified
        """
        message = WebSocketMessage(
            type=MessageType.REDEMPTION_UPDATE,
            data=data,
        )
        return await self.broadcast(message, SubscriptionType.REDEMPTIONS)

    async def broadcast_emergency(self, data: dict[str, Any]) -> int:
        """Broadcast emergency alert to all clients.

        Args:
            data: Emergency data

        Returns:
            Number of clients notified
        """
        message = WebSocketMessage(
            type=MessageType.EMERGENCY_ALERT,
            data=data,
        )
        return await self.broadcast(message)  # No subscription filter for emergencies

    async def send_to_client(self, client_id: str, message: WebSocketMessage) -> bool:
        """Send message to specific client.

        Args:
            client_id: Target client ID
            message: Message to send

        Returns:
            True if sent successfully
        """
        async with self._lock:
            client = self._clients.get(client_id)

        if client:
            return await client.send_message(message)
        return False

    def get_client(self, client_id: str) -> WebSocketClient | None:
        """Get client by ID.

        Args:
            client_id: Client ID

        Returns:
            Client or None if not found
        """
        return self._clients.get(client_id)

    def get_subscribed_clients(self, subscription_type: SubscriptionType) -> list[str]:
        """Get clients subscribed to a type.

        Args:
            subscription_type: Subscription type

        Returns:
            List of client IDs
        """
        return [
            client_id
            for client_id, client in self._clients.items()
            if client.is_subscribed(subscription_type)
        ]

    def get_stats(self) -> dict[str, Any]:
        """Get connection statistics.

        Returns:
            Statistics dictionary
        """
        subscription_counts: dict[str, int] = {}
        for sub_type in SubscriptionType:
            if sub_type != SubscriptionType.ALL:
                subscription_counts[sub_type.value] = len(
                    self.get_subscribed_clients(sub_type)
                )

        return {
            "active_connections": self.active_connections,
            "subscription_counts": subscription_counts,
        }


# Singleton instance
_connection_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get singleton connection manager instance.

    Returns:
        The connection manager
    """
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager
