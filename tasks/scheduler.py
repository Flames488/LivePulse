from app.db.job_lock import acquire_lock
if not await acquire_lock("score_matches"):
    return
