
import requests
from tenacity import retry, stop_after_attempt, wait_fixed

API_URL = "https://api.football-data.org/v4/matches"

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def fetch_live_matches(api_key):
    headers = {"X-Auth-Token": api_key}
    response = requests.get(API_URL, headers=headers, timeout=5)
    response.raise_for_status()
    return response.json()
