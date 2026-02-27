from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger("sams.cloud.ws")


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: Dict[str, List[WebSocket]] = {"global": []}

    async def connect(self, ws: WebSocket, topic: str = "global") -> None:
        await ws.accept()
        self._connections.setdefault(topic, []).append(ws)
        logger.info(f"WS connected: topic={topic}, total={self.count()}")

    def disconnect(self, ws: WebSocket, topic: str = "global") -> None:
        bucket = self._connections.get(topic, [])
        if ws in bucket:
            bucket.remove(ws)
        logger.info(f"WS disconnected: topic={topic}, total={self.count()}")

    async def broadcast(self, data: dict, topic: str = "global") -> None:
        payload = json.dumps(data)
        dead: List[WebSocket] = []
        for ws in list(self._connections.get(topic, [])):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, topic)

    async def broadcast_all(self, data: dict) -> None:
        payload = json.dumps(data)
        dead: List[tuple[WebSocket, str]] = []
        for topic, connections in self._connections.items():
            for ws in list(connections):
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append((ws, topic))
        for ws, topic in dead:
            self.disconnect(ws, topic)

    def count(self) -> int:
        return sum(len(v) for v in self._connections.values())

ws_manager = ConnectionManager()
