"""JWT-сессии для дашборда."""
from __future__ import annotations

import time
from typing import Optional

import jwt
from fastapi import Request

from bot.config import config

ALGORITHM = "HS256"
COOKIE_NAME = "dash_session"


def create_session_token(user: dict) -> str:
    payload = {
        "uid": user["id"],
        "username": user["username"],
        "discriminator": user.get("discriminator", "0"),
        "avatar": user.get("avatar"),
        "iat": int(time.time()),
        "exp": int(time.time()) + config.SESSION_TTL_HOURS * 3600,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=ALGORITHM)


def decode_session(request: Request) -> Optional[dict]:
    token = request.cookies.get(COOKIE_NAME) or (request.headers.get("Authorization") or "").replace("Bearer ", "")
    if not token:
        return None
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
