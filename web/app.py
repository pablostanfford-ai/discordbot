"""Веб-слой дашборда: OAuth2 Discord + REST API к данным бота (FastAPI)."""
from __future__ import annotations

import secrets
import time
from typing import Optional

import aiohttp
import discord
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from bot.config import config
from bot.core import ctx
from web import demo_data
from web.auth import COOKIE_NAME, create_session_token, decode_session

DISCORD_API = "https://discord.com/api/v10"

from bot.config import ROOT_DIR

templates = Jinja2Templates(directory=str(ROOT_DIR / "web" / "templates"))

_state_store: dict[str, float] = {}  # oauth state -> ts


def _cleanup_states():
    now = time.time()
    for k in [k for k, v in _state_store.items() if now - v > 600]:
        _state_store.pop(k, None)


# ---------- Helpers ----------
async def fetch_discord_user(token: str) -> Optional[dict]:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status != 200:
                return None
            return await r.json()


async def fetch_guilds(access_token: str) -> list[dict]:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{DISCORD_API}/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status != 200:
                return []
            return await r.json()


def get_live_guild_ids() -> set[str]:
    """Гильдии, где реально присутствует бот."""
    bot = ctx.bot
    if bot is None or not getattr(bot, "guilds", None):
        return set()
    return {str(g.id) for g in bot.guilds}


def require_user(request: Request) -> dict:
    user = decode_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return user


def require_manage(request: Request, guild_id: str) -> dict:
    """Проверяет право управлять сервером: владелец/админ через Discord API или демо-режим."""
    user = require_user(request)
    if ctx.demo_mode:
        return user
    if guild_id not in get_live_guild_ids():
        raise HTTPException(status_code=404, detail="Бот не состоит на этом сервере")
    # Реальная проверка прав: запрашиваем гильдии пользователя через Discord API
    # (нужен доступ к боту — берём токен приложения из кэша сессии при логине).
    perms = _user_perms_cache.get(str(user["uid"]), {}).get(guild_id)
    if perms is None:
        # Нет данных о правах → разрешаем только владельцу гильдии (по кэшу бота)
        bot = ctx.bot
        g = bot.get_guild(int(guild_id)) if bot else None
        if g is None or str(g.owner_id) != str(user["uid"]):
            raise HTTPException(status_code=403, detail="Нет прав Manage Guild на этом сервере")
        return user
    if not (perms & 0x8):  # ADMINISTRATOR
        raise HTTPException(status_code=403, detail="Нет прав Manage Guild на этом сервере")
    return user


# uid -> {guild_id -> permissions} — заполняется в OAuth-callback из /users/@me/guilds
_user_perms_cache: dict[str, dict[str, int]] = {}


def guild_summary(guild: dict) -> dict:
    """Обогащает гильдию данными из живого кэша бота (участники, каналы и т.д.)."""
    out = dict(guild)
    gid = str(out.get("id"))
    bot = ctx.bot
    if bot is not None:
        g = bot.get_guild(int(gid)) if gid.isdigit() else None
        if g is not None:
            out["member_count"] = g.member_count
            out["channels_count"] = len(g.channels)
            out["roles_count"] = len(g.roles)
            out["icon_url"] = str(g.icon) if g.icon else None
    return out


# ---------- Pydantic модели для PATCH настроек ----------
class SettingsPatch(BaseModel):
    patch: dict


# ---------- App factory ----------
def create_app() -> FastAPI:
    app = FastAPI(title="UniPer-like Dashboard", docs_url="/docs")
    app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "web" / "static")), name="static")

    # ---------- Страницы ----------
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        user = decode_session(request)
        return templates.TemplateResponse("index.html", {"request": request, "user": user,
                                                          "demo": ctx.demo_mode})

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        user = decode_session(request)
        return templates.TemplateResponse("login.html", {"request": request, "user": user,
                                                          "demo": ctx.demo_mode})

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_page(request: Request):
        user = decode_session(request)
        if not user and not ctx.demo_mode:
            return RedirectResponse("/login")
        return templates.TemplateResponse("dashboard.html", {"request": request, "user": user or demo_data.DEMO_USER,
                                                              "demo": ctx.demo_mode})

    @app.get("/guild/{guild_id}", response_class=HTMLResponse)
    async def guild_page(request: Request, guild_id: str):
        user = decode_session(request)
        if not user and not ctx.demo_mode:
            return RedirectResponse("/login")
        return templates.TemplateResponse("guild.html", {"request": request,
                                                         "user": user or demo_data.DEMO_USER,
                                                         "guild_id": guild_id,
                                                         "demo": ctx.demo_mode})

    # ---------- Auth ----------
    @app.get("/api/auth/login")
    async def auth_login():
        if ctx.demo_mode:
            token = create_session_token(demo_data.DEMO_USER)
            resp = RedirectResponse("/dashboard")
            resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", max_age=86400 * 3)
            return resp
        if not (config.CLIENT_ID and config.CLIENT_SECRET):
            raise HTTPException(500, "CLIENT_ID/CLIENT_SECRET не настроены")
        _cleanup_states()
        state = secrets.token_urlsafe(16)
        _state_store[state] = time.time()
        url = (
            f"{DISCORD_API}/oauth2/authorize"
            f"?client_id={config.CLIENT_ID}"
            "&response_type=code"
            f"&redirect_uri={config.oauth_redirect_uri()}"
            f"&scope={config.OAUTH_SCOPES.replace(' ', '%20')}"
            f"&state={state}"
        )
        return RedirectResponse(url)

    @app.get("/api/auth/callback")
    async def auth_callback(code: str = "", state: str = ""):
        if state not in _state_store:
            raise HTTPException(400, "Invalid OAuth state")
        _state_store.pop(state, None)
        if not code:
            raise HTTPException(400, "No code")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{DISCORD_API}/oauth2/token",
                data={
                    "client_id": config.CLIENT_ID,
                    "client_secret": config.CLIENT_SECRET,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": config.oauth_redirect_uri(),
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status != 200:
                    raise HTTPException(401, "Discord OAuth обмен не удался")
                data = await r.json()
        access = data.get("access_token", "")
        user = await fetch_discord_user(access)
        if not user:
            raise HTTPException(401, "Не удалось получить профиль")
        # Кэшируем права пользователя по гильдиям для require_manage
        guilds = await fetch_guilds(access)
        _user_perms_cache[str(user["id"])] = {
            str(g["id"]): int(g.get("permissions", 0)) for g in guilds
        }
        token = create_session_token(user)
        resp = RedirectResponse("/dashboard")
        resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", max_age=86400 * 3)
        return resp

    @app.post("/api/auth/logout")
    async def auth_logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE_NAME)
        return resp

    @app.get("/api/users/@me")
    async def users_me(request: Request):
        user = require_user(request)
        return user

    @app.get("/api/users/guilds")
    async def users_guilds(request: Request):
        user = require_user(request)
        if ctx.demo_mode:
            return [guild_summary(g) for g in demo_data.DEMO_GUILDS]
        # Список гильдий пользователя берётся из сессии OAuth при логине;
        # дополнительно помечаем, где есть бот.
        live = get_live_guild_ids()
        # Для простоты показываем только те гильдии, где есть бот (как в UniPer).
        bot = ctx.bot
        result = []
        if bot is not None:
            for g in bot.guilds:
                result.append(guild_summary({
                    "id": str(g.id), "name": g.name,
                    "icon": str(g.icon) if g.icon else None,
                    "owner": str(g.owner_id) == str(user["uid"]),
                    "permissions": 8,
                    "bot_present": True,
                }))
        return result

    # ---------- Guild data ----------
    @app.get("/api/guilds/{guild_id}/overview")
    async def guild_overview(request: Request, guild_id: str):
        require_manage(request, guild_id)
        if ctx.demo_mode:
            g = next((x for x in demo_data.DEMO_GUILDS if x["id"] == guild_id), demo_data.DEMO_GUILDS[0])
            stats = await ctx.storage.get_stats()
            return {
                "guild": g,
                "stats": {
                    "members": g["member_count"],
                    "channels": g["channels_count"],
                    "roles": g["roles_count"],
                    "commands_used": sum(stats["commands"].values()),
                    "bot_online": True,
                    "uptime_seconds": int(time.time() - (ctx.started_at or time.time())),
                },
                "settings": await ctx.storage.get_guild_settings(guild_id),
            }
        bot = ctx.bot
        g = bot.get_guild(int(guild_id))
        if g is None:
            raise HTTPException(404, "Гильдия не найдена")
        stats = await ctx.storage.get_stats()
        return {
            "guild": {
                "id": str(g.id), "name": g.name,
                "icon": str(g.icon) if g.icon else None,
                "owner": str(g.owner_id), "member_count": g.member_count,
                "channels_count": len(g.channels), "roles_count": len(g.roles),
            },
            "stats": {
                "members": g.member_count,
                "channels": len(g.channels),
                "roles": len(g.roles),
                "commands_used": sum(stats["commands"].values()),
                "bot_online": True,
                "uptime_seconds": int(time.time() - (ctx.started_at or time.time())),
            },
            "settings": await ctx.storage.get_guild_settings(guild_id),
        }

    @app.get("/api/guilds/{guild_id}/settings")
    async def guild_settings_get(request: Request, guild_id: str):
        require_manage(request, guild_id)
        return await ctx.storage.get_guild_settings(guild_id)

    @app.patch("/api/guilds/{guild_id}/settings")
    async def guild_settings_patch(request: Request, guild_id: str, body: SettingsPatch):
        require_manage(request, guild_id)
        return await ctx.storage.save_guild_settings(guild_id, body.patch)

    @app.get("/api/guilds/{guild_id}/channels")
    async def guild_channels(request: Request, guild_id: str):
        require_manage(request, guild_id)
        if ctx.demo_mode:
            return demo_data.demo_channels(guild_id)
        bot = ctx.bot
        g = bot.get_guild(int(guild_id))
        if not g:
            raise HTTPException(404)
        return [{"id": str(c.id), "name": c.name, "type": "text" if isinstance(c, discord.TextChannel) else "voice"}
                for c in g.text_channels]

    @app.get("/api/guilds/{guild_id}/roles")
    async def guild_roles(request: Request, guild_id: str):
        require_manage(request, guild_id)
        if ctx.demo_mode:
            return demo_data.demo_roles(guild_id)
        bot = ctx.bot
        g = bot.get_guild(int(guild_id))
        if not g:
            raise HTTPException(404)
        return [{"id": str(r.id), "name": r.name, "color": f"{r.color.value:06X}"} for r in g.roles if not r.is_default()]

    @app.get("/api/guilds/{guild_id}/members")
    async def guild_members(request: Request, guild_id: str, limit: int = 50, offset: int = 0, q: str = ""):
        require_manage(request, guild_id)
        if ctx.demo_mode:
            ms = demo_data.demo_members(guild_id)
            if q:
                ms = [m for m in ms if q.lower() in m["username"].lower()]
            return ms[offset: offset + limit]
        bot = ctx.bot
        g = bot.get_guild(int(guild_id))
        if not g:
            raise HTTPException(404)
        xp_all = (await ctx.storage.read("xp", {})).get(guild_id, {})
        members = list(g.members)
        if q:
            members = [m for m in members if q.lower() in str(m).lower()]
        page = members[offset: offset + limit]
        return [{
            "id": str(m.id),
            "username": m.name if hasattr(m, "display_name") else str(m),
            "discriminator": m.discriminator,
            "avatar_color": f"{m.color.value:06X}",
            "bot": m.bot,
            "joined_at": int(m.joined_at.timestamp()) if m.joined_at else None,
            "level": xp_all.get(str(m.id), {}).get("level", 1),
            "xp": xp_all.get(str(m.id), {}).get("xp", 0),
            "roles": [r.name for r in m.roles[:5]],
        } for m in page]

    @app.get("/api/guilds/{guild_id}/modlog")
    async def modlog(request: Request, guild_id: str, limit: int = 50):
        require_manage(request, guild_id)
        if ctx.demo_mode:
            return demo_data.demo_modlog(guild_id)
        return await ctx.storage.get_actions(guild_id, limit)

    @app.get("/api/guilds/{guild_id}/leaderboard")
    async def leaderboard(request: Request, guild_id: str):
        require_manage(request, guild_id)
        if ctx.demo_mode:
            rows = demo_data.demo_members(guild_id)
            return sorted(rows, key=lambda r: r["xp"], reverse=True)[:10]
        rows = await ctx.storage.top_xp(guild_id, 10)
        bot = ctx.bot
        g = bot.get_guild(int(guild_id))
        out = []
        for i, r in enumerate(rows):
            m = g.get_member(int(r["user_id"])) if g else None
            out.append({
                "rank": i + 1,
                "id": r["user_id"],
                "username": str(m) if m else r["user_id"],
                "level": r["level"],
                "xp": r["xp"],
            })
        return out

    # ---------- Bot status ----------
    @app.get("/api/bot/status")
    async def bot_status():
        bot = ctx.bot
        return {
            "online": bot is not None and getattr(bot, "is_ready", lambda: False)(),
            "demo": ctx.demo_mode,
            "guilds": len(bot.guilds) if bot else len(demo_data.DEMO_GUILDS),
            "invite_url": config.invite_url(permissions=8 | 4096 | 268500032),
            "version": discord.__version__ if not ctx.demo_mode else "demo",
        }

    @app.exception_handler(HTTPException)
    async def http_exc_handler(request: Request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    return app
