import os
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")

async def refresh_leaderboard():
    """
    Refresh materialized leaderboard view safely
    """
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "REFRESH MATERIALIZED VIEW CONCURRENTLY leaderboard_view;"
        )
    finally:
        await conn.close()
