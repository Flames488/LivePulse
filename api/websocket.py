
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websocket.manager import manager

router = APIRouter()

@router.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"Live Update: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.websocket("/ws/{match_id}")
async def ws(websocket: WebSocket, match_id: int):
    await websocket.accept()
    await websocket.send_text(f"Connected to match {match_id}")
