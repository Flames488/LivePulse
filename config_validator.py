import os

REQUIRED = [
    "DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "FOOTBALL_API_KEY",
    "SECRET_KEY"
]

def validate_env():
    missing = [v for v in REQUIRED if not os.getenv(v)]
    if missing:
        raise RuntimeError(f"Missing environment variables: {missing}")