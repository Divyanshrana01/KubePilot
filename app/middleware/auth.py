import datetime

import bcrypt
import jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.config import settings


#this reads the bearer token from the Authorization header on incoming requests
security = HTTPBearer()

#represents the logged-in user extracted from the jwt token
class User(BaseModel):
    id: str
    is_admin: bool = False

#hashes a plain text password using bcrypt with cost factor 12 — stores this in the db
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

#checks a plain text password against the stored bcrypt hash — returns True if they match
def verify_password(plain_password: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed.encode("utf-8"))

#creates a signed jwt token for a user with an expiry time and an optional admin flag
def create_access_token(username: str, expires_delta_seconds: int | None = None, is_admin: bool = False) -> str:
    if expires_delta_seconds is None:
        expires_delta_seconds = settings.jwt_expiration_minutes * 60
    expires = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=expires_delta_seconds)

    #sub is the standard jwt claim for who the token belongs to
    payload = {
        "sub": username,
        "is_admin": is_admin,
        "exp": expires,
        "iat": datetime.datetime.now(datetime.UTC),
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")

#fastapi dependency — call this in any route that needs a logged-in user
#it decodes the jwt and returns a User object, or raises 401 if something is wrong
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=["HS256"],
        )
        username = payload.get("sub")

        if not isinstance(username, str) or not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
            )
        is_admin: bool = payload.get("is_admin", False)
        return User(id=username, is_admin=is_admin)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from None


#fastapi dependency — same as get_current_user but also checks the is_admin flag
#use this on admin-only routes so regular users get a 403
def get_current_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user
