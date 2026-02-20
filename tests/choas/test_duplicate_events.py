import pytest
from app.services.event_sync_service import EventSyncService

@pytest.mark.asyncio
async def test_event_deduplication(monkeypatch):
    duplicate_events = [
        {"id": "goal_123", "type": "GOAL"},
        {"id": "goal_123", "type": "GOAL"},
    ]

    async def fetch_events():
        return duplicate_events

    monkeypatch.setattr(
        EventSyncService,
        "fetch_live_events",
        fetch_events,
    )

    service = EventSyncService(match_id=99)
    await service.sync_events()

    stored = await service.get_stored_events()
    assert len(stored) == 1
