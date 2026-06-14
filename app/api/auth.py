import psycopg2
from fastapi import APIRouter, HTTPException, status, Request

from app.config import settings
from app.middleware.auth import create_access_token, verify_password, hash_password
from app.middleware.rate_limiter import is_allowed_ip

router = APIRouter(tags=["auth"])


#simple helper to open a fresh postgres connection each time
def _get_db_conn():
    return psycopg2.connect(settings.database_url)


#register endpoint — creates a new user account and returns a jwt token
#rate limited to 3 registrations per hour per ip to stop bots signing up in bulk
@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(request: Request, body: dict) -> dict:
    client_ip = request.client.host if request.client else "unknown"

    #check if this ip has hit the registration limit
    allowed, _, _ = is_allowed_ip(
        client_ip,
        "/auth/register",
        limit=3,
        window_seconds=3600,
    )

    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    username = body.get("username")
    password = body.get("password")

    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")

    #hash the password before storing it — never store plain text passwords
    password_hash = hash_password(password)
    conn = _get_db_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, password_hash),
        )
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        #if the username already exists, postgres raises a unique violation
        conn.rollback()
        raise HTTPException(status_code=409, detail="User already exists") from None
    finally:
        cur.close()
        conn.close()

    #issue a jwt token right away so the user is logged in immediately after register
    token = create_access_token(username=username)
    return {"token": token}


#login endpoint — checks credentials and returns a jwt token if they match
#rate limited to 5 attempts per minute per ip to slow down brute force attacks
@router.post("/auth/login")
async def login(request: Request, body: dict) -> dict:
    client_ip = request.client.host if request.client else "unknown"

    allowed, _, _ = is_allowed_ip(
        client_ip,
        "/auth/login",
        limit=5,
        window_seconds=60,
    )

    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    username = body.get("username")
    password = body.get("password")

    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")

    #look up the user in the db and get their stored password hash and admin flag
    conn = _get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT password_hash, is_admin FROM users WHERE username = %s",
        (username,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    #if user doesnt exist or password is wrong, return the same generic error (dont reveal which one)
    if row is None or not verify_password(password, row[0]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    #create the token, and include the is_admin flag so protected routes can check it
    token = create_access_token(username, is_admin=bool(row[1]))
    return {"token": token}
