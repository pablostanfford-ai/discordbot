"""Хранилище тикетов поддержки (JSON на диске) + память о пользователях бота."""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

STATUS_OPEN = "open"
STATUS_IN_PROGRESS = "in_progress"
STATUS_ANSWERED = "answered"
STATUS_CLOSED = "closed"

STATUSES = (STATUS_OPEN, STATUS_IN_PROGRESS, STATUS_ANSWERED, STATUS_CLOSED)

# SLA по категориям (секунды до просрочки первого ответа)
SLA_SECONDS = {
    "login": 2 * 3600,        # вход — критично
    "network": 4 * 3600,
    "payment": 4 * 3600,
    "bug": 8 * 3600,
    "other": 12 * 3600,
}

MAX_MESSAGE_LEN = 3500
MAX_TAGS_PER_TICKET = 8
TAG_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_\- ]{1,30}$")


def sla_for(category: str) -> int:
    return SLA_SECONDS.get(category, 8 * 3600)


def parse_tags(raw) -> list[str]:
    """Нормализует список тегов: строки, без дублей, валидация."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        tag = str(x).strip()
        if tag and TAG_RE.match(tag) and tag not in out:
            out.append(tag[:30])
    return out[:MAX_TAGS_PER_TICKET]


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
                            username: str = "", full_name: str = "",
                            tags: list[str] | None = None) -> dict:
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
            "tags": parse_tags(tags or []),
            "sla_deadline": now + sla_for(category),
            "sla_notified": False,
            "created_at": now,
            "updated_at": now,
            "messages": [
                {"author": "user", "text": text[:MAX_MESSAGE_LEN], "ts": now,
                 "kind": "text", "read": False},
            ],
        }
        tickets[tid] = ticket
        await self._flush_tickets()
        return ticket

    # ---------- теги ----------
    async def set_tags(self, tid: str, tags: list[str]) -> dict | None:
        tickets = await self._tickets()
        t = tickets.get(tid)
        if not t:
            return None
        t["tags"] = parse_tags(tags)
        t["updated_at"] = int(time.time())
        await self._flush_tickets()
        return t

    async def all_tags(self) -> list[str]:
        """Уникальные теги по всем тикетам (для автодополнения)."""
        tickets = await self._tickets()
        seen: list[str] = []
        for t in tickets.values():
            for tag in t.get("tags", []):
                if tag not in seen:
                    seen.append(tag)
        return sorted(seen, key=str.lower)

    async def get_ticket(self, tid: str) -> dict | None:
        tickets = await self._tickets()
        return tickets.get(tid)

    async def list_tickets(self, status: str | None = None, search: str = "", limit: int = 200,
                           tag: str | None = None) -> list[dict]:
        tickets = await self._tickets()
        rows = sorted(tickets.values(), key=lambda t: t["updated_at"], reverse=True)
        if status and status != "all":
            rows = [t for t in rows if t["status"] == status]
        if tag:
            rows = [t for t in rows if tag.lower() in [x.lower() for x in t.get("tags", [])]]
        if search:
            s = search.lower()
            rows = [t for t in rows
                    if s in t["full_name"].lower() or s in (t["username"] or "").lower()
                    or s in t["category"].lower() or any(s in m["text"].lower() for m in t["messages"][-3:])
                    or any(s in x.lower() for x in t.get("tags", []))
                    or s == str(t["number"])]
        now = int(time.time())
        out = []
        for t in rows[:limit]:
            last = t["messages"][-1] if t["messages"] else {"text": "", "author": "user", "ts": t["created_at"], "kind": "text"}
            answered = any(m["author"] == "agent" for m in t["messages"])
            sla_left = t.get("sla_deadline", 0) - now
            out.append({
                "id": t["id"],
                "number": t["number"],
                "user": t["full_name"],
                "username": t["username"],
                "user_id": t["user_id"],
                "category": t["category"],
                "status": t["status"],
                "tags": t.get("tags", []),
                "created_at": t["created_at"],
                "updated_at": t["updated_at"],
                "unread_agent": sum(1 for m in t["messages"] if m["author"] == "user" and not m.get("read")),
                "last_message": (last["text"][:120] or ("📷 фото" if last.get("kind") == "photo" else "")),
                "last_author": last["author"],
                "messages_count": len(t["messages"]),
                "has_photo": any(m.get("kind") == "photo" for m in t["messages"]),
                # SLA: осталось секунд до дедлайна первого ответа (отриц. = просрочено)
                "sla_left": None if answered or t["status"] == STATUS_CLOSED else sla_left,
                "sla_overdue": (not answered and t["status"] != STATUS_CLOSED and sla_left < 0),
            })
        return out

    async def add_message(self, tid: str, author: str, text: str,
                          kind: str = "text", photo_url: str | None = None) -> dict | None:
        """author: 'user' | 'agent'. kind: 'text' | 'photo'. Возвращает тикет или None."""
        tickets = await self._tickets()
        t = tickets.get(tid)
        if not t:
            return None
        now = int(time.time())
        msg = {"author": author, "text": text[:MAX_MESSAGE_LEN], "ts": now,
               "read": False, "kind": kind}
        if photo_url:
            msg["photo_url"] = photo_url
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
        # при повторном открытии продлеваем SLA-дедлайн
        if status == STATUS_OPEN and any(m["author"] == "agent" for m in t["messages"]):
            t["sla_deadline"] = t["updated_at"] + sla_for(t["category"])
            t["sla_notified"] = False
        await self._flush_tickets()
        return t

    async def overdue_sla(self) -> list[dict]:
        """Тикеты с просроченным SLA, о которых ещё не уведомляли."""
        tickets = await self._tickets()
        now = int(time.time())
        out = []
        for t in tickets.values():
            if (t["status"] != STATUS_CLOSED
                    and not t.get("sla_notified")
                    and not any(m["author"] == "agent" for m in t["messages"])
                    and t.get("sla_deadline", 0) < now):
                out.append(t)
        return out

    async def mark_sla_notified(self, tid: str) -> None:
        tickets = await self._tickets()
        t = tickets.get(tid)
        if t:
            t["sla_notified"] = True
            await self._flush_tickets()

    async def stats(self) -> dict:
        tickets = await self._tickets()
        by_status = {s: 0 for s in STATUSES}
        unread = 0
        with_photo = 0
        for t in tickets.values():
            by_status[t["status"]] = by_status.get(t["status"], 0) + 1
            unread += sum(1 for m in t["messages"] if m["author"] == "user" and not m.get("read"))
            with_photo += any(m.get("kind") == "photo" for m in t["messages"])
        return {"total": len(tickets), "by_status": by_status, "unread_messages": unread,
                "with_photos": with_photo}
