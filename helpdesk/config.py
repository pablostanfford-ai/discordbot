"""Конфигурация Telegram HelpDesk: .env + переменные окружения."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover
    pass

ROOT_DIR = Path(__file__).resolve().parent          # /workspace/telegram
PROJECT_ROOT = ROOT_DIR.parent                       # /workspace
DATA_DIR = Path(os.getenv("TG_DATA_DIR", PROJECT_ROOT / "data" / "telegram"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class TgConfig:
    """Токен и настройки берутся из env (см. .env.example)."""

    BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    # Telegram-id оператора(ов), которые видят Mini App «Панель тикетов»
    ADMIN_IDS: set[int] = {
        int(x) for x in os.getenv("TELEGRAM_ADMIN_IDS", "").replace(",", " ").split() if x.lstrip("-").isdigit()
    }
    WEBAPP_SECRET: str = os.getenv("TELEGRAM_WEBAPP_SECRET", "")  # HMAC-ключ (BotFather → WebApp → Bot)
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
    SESSION_TTL_HOURS: int = int(os.getenv("SESSION_TTL_HOURS", "72"))

    HOST: str = os.getenv("TG_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("TG_PORT", "8060"))
    BASE_URL: str = os.getenv("TG_BASE_URL", f"http://localhost:{PORT}").rstrip("/")

    DEMO_MODE: bool = _bool("DEMO_MODE", True)

    @classmethod
    def has_bot_token(cls) -> bool:
        return bool(cls.BOT_TOKEN)

    @classmethod
    def is_admin(cls, user_id: int) -> bool:
        """Если ADMIN_IDS пуст — считаем админом всех (для локальной разработки)."""
        return not cls.ADMIN_IDS or user_id in cls.ADMIN_IDS

    @classmethod
    def webapp_url(cls) -> str:
        return f"{cls.BASE_URL}/app"


config = TgConfig()
