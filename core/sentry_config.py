import sentry_sdk
import os

def init_sentry():
    """
    Initialize Sentry for production monitoring.
    """
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        traces_sample_rate=0.5,
        environment=os.getenv("ENVIRONMENT", "production"),
    )
