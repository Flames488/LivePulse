
import os
import requests
from jose import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer

SUPABASE_URL = os.getenv("SUPABASE_URL")
security = HTTPBearer()

def verify_token(credentials=Depends(security)):
    token = credentials.credentials
    try:
        jwks = requests.get(f"{SUPABASE_URL}/auth/v1/keys").json()
        payload = jwt.decode(token, jwks, algorithms=["RS256"], audience="authenticated")
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
