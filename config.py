
import os
from dotenv import load_dotenv
from pydantic import BaseSettings
load_dotenv()

class Settings:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")
    JWT_SECRET = os.getenv("JWT_SECRET")

settings = Settings()

class Settings(BaseSettings):
    supabase_url: str
    football_api_key: str
    sentry_dsn: str
settings = Settings()


ALLOWED_ORIGINS: list[str] = ["https://livepulse.app"]
