
import requests
import os

API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = "https://v3.football.api-sports.io"

headers = {
    "x-apisports-key": API_KEY
}

def fetch_live_matches():
    url = f"{BASE_URL}/fixtures?live=all"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def fetch_live_events(match_id: int):
    url = f"{BASE_URL}/fixtures/events?fixture={match_id}"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()
