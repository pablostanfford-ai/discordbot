"""Конфигурация бота и дашборда: .env + переменные окружения."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Config:
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "").strip()
    CLIENT_ID: str = os.getenv("DISCORD_CLIENT_ID", "").strip()
    CLIENT_SECRET: str = os.getenv("DISCORD_CLIENT_SECRET", "").strip()

    HOST: str = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("DASHBOARD_PORT", "8050"))
    BASE_URL: str = os.getenv("DASHBOARD_BASE_URL", f"http://localhost:{PORT}").rstrip("/")

    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
    SESSION_TTL_HOURS: int = int(os.getenv("SESSION_TTL_HOURS", "72"))

    DEMO_MODE: bool = _bool("DEMO_MODE", True)

    OAUTH_SCOPES = "identify guilds"

    @classmethod
    def has_bot_credentials(cls) -> bool:
        return bool(cls.DISCORD_TOKEN and cls.CLIENT_ID and cls.CLIENT_SECRET)

    @classmethod
    def oauth_redirect_uri(cls) -> str:
        return f"{cls.BASE_URL}/api/auth/callback"

    @classmethod
    def invite_url(cls, permissions: int = 8) -> str:
        """Ссылка приглашения бота (Manage Roles по умолчанию)."""
        if not cls.CLIENT_ID:
            return ""
        return (
            "https://discord.com/oauth2/authorize"
            f"?client_id={cls.CLIENT_ID}"
            f"&permissions={permissions}"
            "&scope=bot%20applications.commands"
        )


config = Config
