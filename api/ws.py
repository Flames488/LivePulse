import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


async def heartbeat(ws: WebSocket):
    while True:
        await asyncio.sleep(25)
        await ws.send_json({"type": "ping"})


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    asyncio.create_task(heartbeat(websocket))

    try:
        while True:
            data = await websocket.receive_json()
            # Handle incoming messages here
            await websocket.send_json({"type": "message", "data": data})
    except WebSocketDisconnect:
        pass