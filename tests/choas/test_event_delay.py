import asyncio
import pytest
from app.services.event_sync_service import EventSyncService

@pytest.mark.asyncio
async def test_delayed_event_processing(monkeypatch):
    events = [
        {"id": "evt1", "type": "GOAL", "minute": 32},
        {"id": "evt2", "type": "CORNER", "minute": 31},  # out of order
    ]

    async def delayed_fetch():
        await asyncio.sleep(2)
        return events

    monkeypatch.setattr(
        EventSyncService,
        "fetch_live_events",
        delayed_fetch,
    )

    service = EventSyncService(match_id=1)
    processed = await service.sync_events()

    assert processed is True
