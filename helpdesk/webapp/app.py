"""REST API и страница Telegram Mini App «Панель тикетов» (FastAPI)."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from helpdesk import tg_bot
from helpdesk.auth import COOKIE_NAME, create_agent_token, decode_agent_session, require_agent, validate_init_data
from helpdesk.config import config
from helpdesk.store import MAX_MESSAGE_LEN, STATUS_CLOSED, STATUS_IN_PROGRESS, TicketStore

log = logging.getLogger("helpdesk.webapp")

WEBAPP_DIR = Path(__file__).resolve().parent  # /workspace/helpdesk/webapp


class AuthBody(BaseModel):
    init_data: str = Field(min_length=1)


class ReplyBody(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_LEN)


class StatusBody(BaseModel):
    status: str


class TagsBody(BaseModel):
    tags: list[str] = []


def create_webapp_app(store: TicketStore) -> FastAPI:
    app = FastAPI(title="Telegram HelpDesk Mini App", docs_url="/docs")
    app.state.store = store

    # ---------- страница Mini App ----------
    @app.get("/app")
    async def app_page():
        return FileResponse(WEBAPP_DIR / "index.html")

    @app.get("/")
    async def root():
        return RedirectResponse("/app")

    # ---------- auth ----------
    @app.post("/api/auth")
    async def auth(body: AuthBody):
        user = validate_init_data(body.init_data)
        if not user:
            raise HTTPException(401, "Не удалось проверить initData. Откройте приложение через кнопку бота.")
        token = create_agent_token(user)
        resp = JSONResponse({"ok": True, "user": {"id": user["id"],
                                                  "full_name": user.get("full_name", ""),
                                                  "username": user.get("username", "")}})
        resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="none", secure=True, max_age=86400 * 3)
        await store.remember_user(int(user["id"]), user.get("username", ""), user.get("full_name", ""))
        log.info("Оператор вошёл в панель: %s (%s)", user.get("full_name"), user.get("id"))
        return resp

    @app.get("/api/me")
    async def me(request: Request):
        session = decode_agent_session(request)
        if not session:
            raise HTTPException(401, "Нет сессии")
        return {"ok": True, **session}

    @app.post("/api/logout")
    async def logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE_NAME)
        return resp

    # ---------- тикеты ----------
    @app.get("/api/tickets")
    async def tickets(request: Request, status: str = "all", search: str = "", tag: str = "",
                      agent: dict = Depends(require_agent)):
        rows = await store.list_tickets(status=status or None, search=search, tag=tag or None)
        stats = await store.stats()
        return {"tickets": rows, "stats": stats, "tags": await store.all_tags(),
                "server_time": int(time.time())}

    @app.get("/api/tickets/{ticket_id}")
    async def ticket_detail(ticket_id: str, agent: dict = Depends(require_agent)):
        t = await store.get_ticket(ticket_id)
        if not t:
            raise HTTPException(404, "Тикет не найден")
        await store.mark_read(ticket_id, "user")  # оператор открыл — нечитаные сняты
        fresh = await store.get_ticket(ticket_id)
        return {"ticket": fresh}

    @app.post("/api/tickets/{ticket_id}/reply")
    async def reply(ticket_id: str, body: ReplyBody, agent: dict = Depends(require_agent)):
        t = await store.get_ticket(ticket_id)
        if not t:
            raise HTTPException(404, "Тикет не найден")
        updated = await store.add_message(ticket_id, "agent", body.text)
        delivered = await tg_bot.deliver_agent_reply(t["user_id"], t["number"], body.text)
        return {"ok": True, "delivered": delivered, "ticket": updated}

    @app.post("/api/tickets/{ticket_id}/status")
    async def set_status(ticket_id: str, body: StatusBody, agent: dict = Depends(require_agent)):
        t = await store.get_ticket(ticket_id)
        if not t:
            raise HTTPException(404, "Тикет не найден")
        if body.status not in (STATUS_IN_PROGRESS, STATUS_CLOSED, "open", "answered"):
            raise HTTPException(422, "Недопустимый статус")
        updated = await store.set_status(ticket_id, body.status)
        if body.status != t["status"]:
            await tg_bot.deliver_status_notice(t["user_id"], t["number"], body.status)
            if body.status == STATUS_CLOSED:
                await store.add_message(ticket_id, "agent", "Тикет закрыт оператором.")
        return {"ok": True, "ticket": updated}

    @app.post("/api/tickets/{ticket_id}/tags")
    async def set_tags(ticket_id: str, body: TagsBody, agent: dict = Depends(require_agent)):
        t = await store.set_tags(ticket_id, body.tags)
        if not t:
            raise HTTPException(404, "Тикет не найден")
        return {"ok": True, "ticket": t, "tags": await store.all_tags()}

    # ---------- скриншоты из тикетов ----------
    if config.PHOTO_DIR.exists():
        app.mount("/photos", StaticFiles(directory=str(config.PHOTO_DIR)), name="ticket-photos")

    # ---------- демо-обращения (для теста панели без реального бота) ----------
    @app.post("/api/demo/seed")
    async def demo_seed(agent: dict = Depends(require_agent)):
        """Создаёт 2 тестовых тикета, чтобы посмотреть работу панели без бота."""
        made = []
        demo_specs = [
            ("Алексей Петров", "alex_p", "login", "Не могу войти в аккаунт: пишет «неверный пароль», хотя я его не менял. Пробовал сбросить — письмо не приходит."),
            ("Мария Иванова", "m_ivanova", "network", "После обновления приложение не подключается к серверу, бесконечный «поиск соединения». Wi-Fi работает, другие приложения тоже."),
        ]
        for i, (name, uname, cat, text) in enumerate(demo_specs):
            t = await store.create_ticket(user_id=900000 + i, category=cat, text=text, username=uname, full_name=name)
            # добавим немного реализма: теги и «просроченный» SLA у первого тикета
            if i == 0:
                await store.set_tags(t["id"], ["срочно", "аккаунт"])
                tickets = await store._tickets()  # noqa: SLF001 — демо-хак
                tickets[t["id"]]["sla_deadline"] = int(time.time()) - 3600
                await store._flush_tickets()  # noqa: SLF001
            made.append(t["id"])
        return {"ok": True, "created": made}

    # ---------- static ----------
    if (WEBAPP_DIR / "static").exists():
        app.mount("/app/static", StaticFiles(directory=str(WEBAPP_DIR / "static")), name="webapp-static")

    @app.exception_handler(HTTPException)
    async def http_exc_handler(request: Request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    return app
