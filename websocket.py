
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, match_id: str):
        await websocket.accept()
        self.active_connections.setdefault(match_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, match_id: str):
        self.active_connections[match_id].remove(websocket)

    async def broadcast(self, match_id: str, message: str):
        for connection in self.active_connections.get(match_id, []):
            await connection.send_text(message)

manager = ConnectionManager()
