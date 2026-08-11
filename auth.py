"""
RAYPAN Authentication & Authorization Module
- User registration/login/session
- Three-tier permission: guest / free / vip
- Monday Open House: registered users get VIP access during time windows
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, HTTPException, Response
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logger = logging.getLogger("raypan.auth")

DB = "postgresql://ruipan:Ruipan2026!@127.0.0.1:5432/ruipan"
SESSION_DAYS = 30

# Open House windows (Beijing time, UTC+8)
# Monday: 10:00-14:00 and 19:00-22:00
OPEN_HOUSE_WINDOWS = [(10, 14), (19, 22)]
OPEN_HOUSE_WEEKDAY = 0  # Monday


def db_conn():
    return psycopg2.connect(DB, cursor_factory=RealDictCursor)


def init_tables():
    """Create auth tables if not exist."""
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password_hash VARCHAR(128) NOT NULL,
            salt VARCHAR(32) NOT NULL,
            tier VARCHAR(20) NOT NULL DEFAULT 'free',
            vip_expires_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            last_login TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token VARCHAR(64) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")
    conn.commit()
    cur.close()
    conn.close()
    logger.info("Auth tables initialized")


def hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()


def make_token() -> str:
    return secrets.token_hex(32)


def create_session(user_id: int) -> str:
    token = make_token()
    expires = datetime.utcnow() + timedelta(days=SESSION_DAYS)
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sessions(token, user_id, expires_at) VALUES(%s,%s,%s)",
        (token, user_id, expires),
    )
    cur.execute("UPDATE users SET last_login=NOW() WHERE id=%s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return token


def get_user(token: str):
    if not token or len(token) < 10:
        return None
    try:
        conn = db_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT u.id, u.username, u.email, u.tier, u.vip_expires_at, u.created_at
               FROM sessions s JOIN users u ON s.user_id=u.id
               WHERE s.token=%s AND s.expires_at>NOW()""",
            (token,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_user error: {e}")
        return None


def is_open_house() -> bool:
    """Check if current time is within Monday Open House window (Beijing time)."""
    now = datetime.utcnow() + timedelta(hours=8)
    if now.weekday() != OPEN_HOUSE_WEEKDAY:
        return False
    h = now.hour
    return any(start <= h < end for start, end in OPEN_HOUSE_WINDOWS)


def get_effective_tier(request: Request) -> dict:
    """
    Returns {'tier': str, 'user': dict|None, 'open_house': bool}
    tier: 'guest' | 'free' | 'vip'
    open_house: True if free user getting VIP via open house
    """
    token = request.cookies.get("raypan_token") or request.headers.get("x-auth-token", "")
    user = get_user(token)
    oh = is_open_house()
    if not user:
        return {"tier": "guest", "user": None, "open_house": False}
    if user["tier"] == "vip" and (not user["vip_expires_at"] or user["vip_expires_at"] > datetime.utcnow()):
        return {"tier": "vip", "user": user, "open_house": False}
    if user["tier"] == "free" and oh:
        return {"tier": "vip", "user": user, "open_house": True}
    return {"tier": "free", "user": user, "open_house": False}


# ===== Router =====
router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterReq(BaseModel):
    username: str
    email: str
    password: str


class LoginReq(BaseModel):
    account: str  # username or email
    password: str


@router.post("/register")
def register(req: RegisterReq, response: Response):
    username = req.username.strip()
    email = req.email.strip().lower()
    if len(username) < 2 or len(username) > 30:
        raise HTTPException(400, "用户名长度2-30位")
    if "@" not in email or "." not in email:
        raise HTTPException(400, "邮箱格式不正确")
    if len(req.password) < 6:
        raise HTTPException(400, "密码至少6位")
    salt = secrets.token_hex(16)
    pw_hash = hash_pw(req.password, salt)
    try:
        conn = db_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users(username,email,password_hash,salt,tier) VALUES(%s,%s,%s,%s,'free') RETURNING id",
            (username, email, pw_hash, salt),
        )
        user_id = cur.fetchone()["id"]
        conn.commit()
        cur.close()
        conn.close()
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(400, "用户名或邮箱已被注册")
    token = create_session(user_id)
    response.set_cookie(
        key="raypan_token", value=token,
        max_age=SESSION_DAYS * 86400, httponly=True,
        samesite="lax", path="/",
    )
    return {"ok": True, "token": token, "user": {"id": user_id, "username": username, "tier": "free"}}


@router.post("/login")
def login(req: LoginReq, response: Response):
    account = req.account.strip()
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE username=%s OR email=%s",
        (account, account.lower()),
    )
    user = cur.fetchone()
    cur.close()
    conn.close()
    if not user:
        raise HTTPException(401, "账号或密码错误")
    pw_hash = hash_pw(req.password, user["salt"])
    if pw_hash != user["password_hash"]:
        raise HTTPException(401, "账号或密码错误")
    token = create_session(user["id"])
    response.set_cookie(
        key="raypan_token", value=token,
        max_age=SESSION_DAYS * 86400, httponly=True,
        samesite="lax", path="/",
    )
    return {
        "ok": True, "token": token,
        "user": {"id": user["id"], "username": user["username"], "tier": user["tier"],
                 "vip_expires_at": user.get("vip_expires_at")},
    }


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("raypan_token", "")
    if token:
        try:
            conn = db_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM sessions WHERE token=%s", (token,))
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass
    response.delete_cookie("raypan_token", path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    info = get_effective_tier(request)
    if not info["user"]:
        return {"tier": "guest", "open_house": is_open_house()}
    u = info["user"]
    return {
        "tier": info["tier"],
        "open_house": info["open_house"],
        "user": {
            "id": u["id"], "username": u["username"], "email": u["email"],
            "account_tier": u["tier"],
            "vip_expires_at": str(u["vip_expires_at"]) if u["vip_expires_at"] else None,
        },
    }


@router.get("/open-house")
def open_house_status():
    return {"open_house": is_open_house(), "windows": OPEN_HOUSE_WINDOWS, "weekday": OPEN_HOUSE_WEEKDAY}
