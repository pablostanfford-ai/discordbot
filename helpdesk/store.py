"""Хранилище тикетов поддержки (JSON на диске) + память о пользователях бота."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

STATUS_OPEN = "open"
STATUS_IN_PROGRESS = "in_progress"
STATUS_ANSWERED = "answered"
STATUS_CLOSED = "closed"

STATUSES = (STATUS_OPEN, STATUS_IN_PROGRESS, STATUS_ANSWERED, STATUS_CLOSED)

MAX_MESSAGE_LEN = 3500


class TicketStore:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._tickets_path = self.dir / "tickets.json"
        self._users_path = self.dir / "tg_users.json"
        self._lock = asyncio.Lock()
        # кэш: str -> dict (не перекрывать методами!)
        self._tickets_cache: dict[str, dict] | None = None
        self._users_cache: dict[str, dict] | None = None

    # ---------- low-level ----------
    def _load(self, path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def _save(self, path: Path, data: Any) -> None:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    async def _tickets(self) -> dict[str, dict]:
        async with self._lock:
            if self._tickets_cache is None:
                self._tickets_cache = self._load(self._tickets_path, {})
            return self._tickets_cache

    async def _users(self) -> dict[str, dict]:
        async with self._lock:
            if self._users_cache is None:
                self._users_cache = self._load(self._users_path, {})
            return self._users_cache

    async def _flush_tickets(self) -> None:
        async with self._lock:
            if self._tickets_cache is not None:
                self._save(self._tickets_path, self._tickets_cache)

    # ---------- пользователи ----------
    async def remember_user(self, user_id: int, username: str = "", full_name: str = "") -> None:
        users = await self._users()
        users[str(user_id)] = {
            "id": user_id,
            "username": username,
            "full_name": full_name,
            "seen_at": int(time.time()),
        }
        async with self._lock:
            self._save(self._users_path, users)

    async def get_user(self, user_id: int) -> dict | None:
        users = await self._users()
        return users.get(str(user_id))

    # ---------- тикеты ----------
    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex[:10]

    async def create_ticket(self, user_id: int, category: str, text: str,
                            username: str = "", full_name: str = "") -> dict:
        tickets = await self._tickets()
        now = int(time.time())
        tid = self._new_id()
        ticket = {
            "id": tid,
            "number": len(tickets) + 1,
            "user_id": user_id,
            "username": username,
            "full_name": full_name or username or str(user_id),
            "category": category,
            "status": STATUS_OPEN,
            "created_at": now,
            "updated_at": now,
            "messages": [
                {"author": "user", "text": text, "ts": now},
            ],
        }
        tickets[tid] = ticket
        await self._flush_tickets()
        return ticket

    async def get_ticket(self, tid: str) -> dict | None:
        tickets = await self._tickets()
        return tickets.get(tid)

    async def list_tickets(self, status: str | None = None, search: str = "", limit: int = 200) -> list[dict]:
        tickets = await self._tickets()
        rows = sorted(tickets.values(), key=lambda t: t["updated_at"], reverse=True)
        if status and status != "all":
            rows = [t for t in rows if t["status"] == status]
        if search:
            s = search.lower()
            rows = [t for t in rows
                    if s in t["full_name"].lower() or s in (t["username"] or "").lower()
                    or s in t["category"].lower() or any(s in m["text"].lower() for m in t["messages"][-3:])
                    or s == str(t["number"])]
        out = []
        for t in rows[:limit]:
            last = t["messages"][-1] if t["messages"] else {"text": "", "author": "user", "ts": t["created_at"]}
            out.append({
                "id": t["id"],
                "number": t["number"],
                "user": t["full_name"],
                "username": t["username"],
                "user_id": t["user_id"],
                "category": t["category"],
                "status": t["status"],
                "created_at": t["created_at"],
                "updated_at": t["updated_at"],
                "unread_agent": sum(1 for m in t["messages"] if m["author"] == "user" and not m.get("read")),
                "last_message": (last["text"][:120]),
                "last_author": last["author"],
                "messages_count": len(t["messages"]),
            })
        return out

    async def add_message(self, tid: str, author: str, text: str) -> dict | None:
        """author: 'user' | 'agent'. Возвращает обновлённый тикет или None."""
        tickets = await self._tickets()
        t = tickets.get(tid)
        if not t:
            return None
        now = int(time.time())
        msg = {"author": author, "text": text[:MAX_MESSAGE_LEN], "ts": now, "read": False}
        t["messages"].append(msg)
        t["updated_at"] = now
        # жизненный цикл статуса
        if author == "agent":
            if t["status"] != STATUS_CLOSED:
                t["status"] = STATUS_ANSWERED
        elif t["status"] in (STATUS_ANSWERED, STATUS_CLOSED):
            # пользователь ответил после ответа оператора / в закрытом тикете — снова в работе
            t["status"] = STATUS_IN_PROGRESS
        await self._flush_tickets()
        return t

    async def mark_read(self, tid: str, author: str) -> None:
        tickets = await self._tickets()
        t = tickets.get(tid)
        if not t:
            return
        changed = False
        for m in t["messages"]:
            if m["author"] == author and not m.get("read"):
                m["read"] = True
                changed = True
        if changed:
            await self._flush_tickets()

    async def set_status(self, tid: str, status: str) -> dict | None:
        if status not in STATUSES:
            return None
        tickets = await self._tickets()
        t = tickets.get(tid)
        if not t:
            return None
        t["status"] = status
        t["updated_at"] = int(time.time())
        await self._flush_tickets()
        return t

    async def stats(self) -> dict:
        tickets = await self._tickets()
        by_status = {s: 0 for s in STATUSES}
        unread = 0
        for t in tickets.values():
            by_status[t["status"]] = by_status.get(t["status"], 0) + 1
            unread += sum(1 for m in t["messages"] if m["author"] == "user" and not m.get("read"))
        return {"total": len(tickets), "by_status": by_status, "unread_messages": unread}
