from fastapi import WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
import os

SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"

async def validate_websocket(websocket: WebSocket):
    """
    Validates JWT token during WebSocket handshake.
    Disconnects unauthorized users immediately.
    """
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=1008)
        raise WebSocketDisconnect()

    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        await websocket.close(code=1008)
        raise WebSocketDisconnect()
