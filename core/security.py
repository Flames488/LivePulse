
from jose import jwt
import os, datetime
SECRET=os.getenv("JWT_SECRET","secret")
def create(data):
    data["exp"]=datetime.datetime.utcnow()+datetime.timedelta(hours=12)
    return jwt.encode(data,SECRET,algorithm="HS256")


def secure_headers():
    return {}
