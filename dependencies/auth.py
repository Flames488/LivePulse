
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return {"user_id": "mock_user"}

def require_admin(user=Depends(get_current_user)):
    if user.get("user_id") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
