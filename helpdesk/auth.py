"""Аутентификация Telegram Mini App: проверка initData по HMAC + JWT-сессия оператора."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Optional
from urllib.parse import parse_qsl

import jwt
from fastapi import HTTPException, Request

from helpdesk.config import config

ALGORITHM = "HS256"
COOKIE_NAME = "tg_helpdesk_session"
MAX_AUTH_AGE_SEC = 86400  # Telegram рекомендует не принимать initData старше суток


def validate_init_data(init_data: str) -> Optional[dict]:
    """Возвращает dict с payload'ом пользователя, если подпись валидна.

    Если TELEGRAM_WEBAPP_SECRET не задан (локальная разработка) — доверяем данным.
    """
    try:
        data = dict(parse_qsl(init_data, strict_parsing=False))
    except ValueError:
        return None
    user_raw = data.get("user")
    if not user_raw:
        return None
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError:
        return None

    secret_key = config.WEBAPP_SECRET
    if not secret_key:
        # DEV-режим: без секрета проверяем только наличие auth_date
        return user

    hash_got = data.pop("hash", "")
    # data_check_string: key=value, отсортированные по ключу
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", secret_key.encode("utf-8"), hashlib.sha256).digest()
    calc = hmac.new(secret, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, hash_got):
        return None

    auth_date = int(data.get("auth_date", "0") or 0)
    if auth_date and time.time() - auth_date > MAX_AUTH_AGE_SEC:
        return None
    return user


def create_agent_token(user: dict) -> str:
    payload = {
        "uid": user["id"],
        "username": user.get("username", ""),
        "full_name": user.get("full_name", ""),
        "role": "agent",
        "iat": int(time.time()),
        "exp": int(time.time()) + config.SESSION_TTL_HOURS * 3600,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=ALGORITHM)


def decode_agent_session(request: Request) -> Optional[dict]:
    token = request.cookies.get(COOKIE_NAME) or (request.headers.get("Authorization") or "").replace("Bearer ", "")
    if not token:
        return None
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def require_agent(request: Request) -> dict:
    session = decode_agent_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Не авторизован: откройте приложение из бота")
    if config.ADMIN_IDS and session.get("uid") not in config.ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Нет доступа: вы не оператор поддержки")
    return session
