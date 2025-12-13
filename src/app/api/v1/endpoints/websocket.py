"""WebSocket API endpoints for real-time updates."""

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket import (
    ConnectionManager,
    MessageType,
    SubscriptionRequest,
    SubscriptionType,
    WebSocketMessage,
    get_connection_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])


@router.websocket("")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates.

    Protocol:
    1. Client connects
    2. Server sends CONNECTED message with client_id
    3. Client sends SUBSCRIBE message with subscription types
    4. Server sends SUBSCRIBED confirmation
    5. Server broadcasts updates based on subscriptions
    6. Client can UNSUBSCRIBE at any time
    7. Client/server can send PING/PONG for keep-alive
    """
    manager = get_connection_manager()
    client = await manager.connect(websocket)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                await handle_client_message(client.client_id, message, manager)
            except json.JSONDecodeError:
                await client.send_message(
                    WebSocketMessage(
                        type=MessageType.ERROR,
                        error="Invalid JSON format",
                    )
                )
    except WebSocketDisconnect:
        await manager.disconnect(client.client_id)
    except Exception as e:
        logger.error(f"WebSocket error for {client.client_id}: {e}")
        await manager.disconnect(client.client_id)


async def handle_client_message(
    client_id: str,
    message: dict[str, Any],
    manager: ConnectionManager,
) -> None:
    """Handle incoming client message.

    Args:
        client_id: Client ID
        message: Parsed message
        manager: Connection manager
    """
    msg_type = message.get("type", "").upper()
    client = manager.get_client(client_id)

    if not client:
        return

    if msg_type == "PING":
        await client.send_message(
            WebSocketMessage(type=MessageType.PONG, data={"message": "pong"})
        )

    elif msg_type == "SUBSCRIBE":
        subscriptions = message.get("subscriptions", [])
        for sub in subscriptions:
            try:
                sub_type = SubscriptionType(sub.upper())
                client.subscribe(sub_type)
            except ValueError:
                pass

        await client.send_message(
            WebSocketMessage(
                type=MessageType.SUBSCRIBED,
                data={
                    "subscriptions": [s.value for s in client.subscriptions],
                    "message": f"Subscribed to {len(client.subscriptions)} channels",
                },
            )
        )

    elif msg_type == "UNSUBSCRIBE":
        subscriptions = message.get("subscriptions", [])
        for sub in subscriptions:
            try:
                sub_type = SubscriptionType(sub.upper())
                client.unsubscribe(sub_type)
            except ValueError:
                pass

        await client.send_message(
            WebSocketMessage(
                type=MessageType.UNSUBSCRIBED,
                data={
                    "subscriptions": [s.value for s in client.subscriptions],
                    "message": "Unsubscribed successfully",
                },
            )
        )

    else:
        await client.send_message(
            WebSocketMessage(
                type=MessageType.ERROR,
                error=f"Unknown message type: {msg_type}",
            )
        )


@router.get("/stats")
async def get_websocket_stats() -> dict[str, Any]:
    """Get WebSocket connection statistics.

    Returns:
        Connection stats
    """
    manager = get_connection_manager()
    return manager.get_stats()


@router.post("/broadcast/nav")
async def broadcast_nav_update(data: dict[str, Any]) -> dict[str, Any]:
    """Broadcast NAV update to all subscribed clients.

    Args:
        data: NAV update data

    Returns:
        Broadcast result
    """
    manager = get_connection_manager()
    count = await manager.broadcast_nav_update(data)
    return {"status": "broadcasted", "clients_notified": count}


@router.post("/broadcast/risk")
async def broadcast_risk_update(data: dict[str, Any]) -> dict[str, Any]:
    """Broadcast risk update to all subscribed clients.

    Args:
        data: Risk update data

    Returns:
        Broadcast result
    """
    manager = get_connection_manager()
    count = await manager.broadcast_risk_update(data)
    return {"status": "broadcasted", "clients_notified": count}


@router.post("/broadcast/alert")
async def broadcast_alert(data: dict[str, Any]) -> dict[str, Any]:
    """Broadcast alert to all subscribed clients.

    Args:
        data: Alert data

    Returns:
        Broadcast result
    """
    manager = get_connection_manager()
    count = await manager.broadcast_alert(data)
    return {"status": "broadcasted", "clients_notified": count}


@router.post("/broadcast/emergency")
async def broadcast_emergency(data: dict[str, Any]) -> dict[str, Any]:
    """Broadcast emergency to ALL clients (ignores subscriptions).

    Args:
        data: Emergency data

    Returns:
        Broadcast result
    """
    manager = get_connection_manager()
    count = await manager.broadcast_emergency(data)
    return {"status": "emergency_broadcasted", "clients_notified": count}
