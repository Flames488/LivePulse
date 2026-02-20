
import requests
import os

API_KEY = os.getenv("FOOTBALL_API_KEY")
BASE_URL = "https://api.football-data.org/v4"

def get_live_epl_matches():
    headers = {"X-Auth-Token": API_KEY}
    r = requests.get(f"{BASE_URL}/competitions/PL/matches?status=LIVE", headers=headers)
    r.raise_for_status()
    return r.json()
