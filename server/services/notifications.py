"""
MIA Notifications — Push notification engine via WebSocket.
"""

import asyncio
import time
from datetime import datetime
from typing import Optional


class NotificationEngine:
    """Push notification system for real-time alerts."""

    def __init__(self):
        self._clients: set = set()
        self._history: list[dict] = []
        self._max_history = 200

    def add_client(self, websocket):
        """Register a WebSocket client for notifications."""
        self._clients.add(websocket)

    def remove_client(self, websocket):
        """Remove a WebSocket client."""
        self._clients.discard(websocket)

    async def send(self, title: str, message: str, level: str = "info", data: Optional[dict] = None):
        """Send a notification to all connected clients.

        Args:
            title: Notification title.
            message: Notification body.
            level: 'info', 'success', 'warning', 'error'.
            data: Optional extra data.
        """
        notification = {
            "type": "notification",
            "id": f"notif_{int(time.time() * 1000)}",
            "title": title,
            "message": message,
            "level": level,
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }

        self._history.append(notification)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Send to all connected clients
        disconnected = set()
        for ws in self._clients:
            try:
                await ws.send_json(notification)
            except Exception:
                disconnected.add(ws)

        # Clean up disconnected clients
        self._clients -= disconnected

    def get_history(self, limit: int = 50) -> list:
        """Get notification history."""
        return self._history[-limit:]

    def clear_history(self):
        """Clear notification history."""
        self._history = []


# Global instance
notifications = NotificationEngine()
