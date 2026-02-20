import asyncio
import pytest
from app.services.event_sync_service import EventSyncService

@pytest.mark.asyncio
async def test_external_api_timeout(monkeypatch):
    async def timeout_fetch():
        await asyncio.sleep(10)
        raise TimeoutError("API timeout")

    monkeypatch.setattr(
        EventSyncService,
        "fetch_live_events",
        timeout_fetch,
    )

    service = EventSyncService(match_id=1)
    result = await service.sync_events()

    assert result is False
