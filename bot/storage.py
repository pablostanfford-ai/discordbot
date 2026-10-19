"""Простое асинхронное JSON-хранилище: настройки гильдий, XP, журнал действий, статистика."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

DEFAULT_GUILD_SETTINGS: dict[str, Any] = {
    "prefix": "!",
    "modules": {
        "moderation": True,
        "automod": True,
        "welcome": True,
        "leveling": True,
        "logging": True,
        "autoroles": False,
    },
    "welcome": {
        "enabled": True,
        "channel_id": None,
        "message": "👋 Добро пожаловать, {user}! Ты здесь {server_count}-й участник. Рад видеть на {guild_name}!",
        "leave_message": "👋 {user} покинул сервер. Было приятно ({member_count} участников осталось).",
        "embed_color": "#5865F2",
        "autorole_ids": [],
    },
    "automod": {
        "enabled": True,
        "max_mentions": 5,
        "max_links": 3,
        "banned_words": ["идиот", "дурак"],
        "action": "timeout",          # delete | timeout | kick | warn
        "timeout_minutes": 10,
        "ignore_channels": [],
        "whitelist_users": [],
    },
    "leveling": {
        "enabled": True,
        "xp_per_message": 5,
        "cooldown_seconds": 60,
        "announce_channel_id": None,
        "role_rewards": [],           # [{"level": 5, "role_id": "123"}]
    },
    "logging": {
        "enabled": True,
        "channel_id": None,
        "events": ["message_edit", "message_delete", "member_join", "member_leave", "mod_actions"],
    },
    "moderation": {
        "enabled": True,
        "mod_role_id": None,
        "mute_role_id": None,
        "min_reason_length": 3,
    },
}


def _deep_merge(base: dict, incoming: dict) -> dict:
    """Возвращает base, обновлённый значениями incoming (рекурсивно для dict)."""
    out = dict(base)
    for k, v in incoming.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class JsonStore:
    """Потокобезопасное (в рамках event loop) хранилище нескольких JSON-файлов."""

    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}
        self._cache: dict[str, Any] = {}

    def _path(self, name: str) -> Path:
        return self.dir / f"{name}.json"

    def _lock(self, name: str) -> asyncio.Lock:
        return self._locks.setdefault(name, asyncio.Lock())

    async def read(self, name: str, default: Any) -> Any:
        if name in self._cache:
            return self._cache[name]
        p = self._path(name)
        if p.exists():
            try:
                self._cache[name] = json.loads(p.read_text(encoding="utf-8"))
                return self._cache[name]
            except (json.JSONDecodeError, OSError):
                pass
        self._cache[name] = default
        return default

    async def write(self, name: str, data: Any) -> None:
        async with self._lock(name):
            self._cache[name] = data
            tmp = self._path(name).with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path(name))

    # ---------- Настройки гильдий ----------
    async def get_guild_settings(self, guild_id: str) -> dict:
        all_s = await self.read("settings", {})
        stored = all_s.get(guild_id, {})
        return _deep_merge(DEFAULT_GUILD_SETTINGS, stored)

    async def save_guild_settings(self, guild_id: str, patch: dict) -> dict:
        all_s = await self.read("settings", {})
        merged = _deep_merge(all_s.get(guild_id, {}), patch or {})
        all_s[guild_id] = merged
        await self.write("settings", all_s)
        return _deep_merge(DEFAULT_GUILD_SETTINGS, merged)

    # ---------- XP / уровни ----------
    async def add_xp(self, guild_id: str, user_id: str, amount: int) -> dict:
        xp = await self.read("xp", {})
        g = xp.setdefault(guild_id, {})
        rec = g.setdefault(user_id, {"xp": 0, "level": 1, "messages": 0, "last_xp": 0})
        rec["xp"] += amount
        rec["messages"] += 1
        rec["last_xp"] = int(time.time())
        rec["level"] = self.level_from_xp(rec["xp"])
        await self.write("xp", xp)
        return rec

    async def get_user_xp(self, guild_id: str, user_id: str) -> dict:
        xp = await self.read("xp", {})
        return xp.get(guild_id, {}).get(
            user_id, {"xp": 0, "level": 1, "messages": 0, "last_xp": 0}
        )

    async def top_xp(self, guild_id: str, limit: int = 10) -> list[dict]:
        xp = await self.read("xp", {})
        rows = [
            {"user_id": uid, **rec}
            for uid, rec in xp.get(guild_id, {}).items()
        ]
        rows.sort(key=lambda r: r["xp"], reverse=True)
        return rows[:limit]

    @staticmethod
    def level_from_xp(xp: int) -> int:
        """Уровень = floor(sqrt(xp/10)). 10 XP → L1, 40 → L2, 90 → L3 ..."""
        import math

        return max(1, int(math.floor(math.sqrt(max(xp, 0) / 10.0))))

    @staticmethod
    def xp_for_level(level: int) -> int:
        return (level * level) * 10

    # ---------- Журнал модерации ----------
    async def log_action(self, entry: dict | None = None, **kw) -> dict:
        entry = dict(entry or {})
        entry.update(kw)
        actions = await self.read("modlog", [])
        entry.setdefault("id", len(actions) + 1)
        entry["created_at"] = int(time.time())
        actions.append(entry)
        await self.write("modlog", actions[-5000:])
        return entry

    async def get_actions(self, guild_id: str | None = None, limit: int = 100) -> list[dict]:
        actions = await self.read("modlog", [])
        if guild_id:
            actions = [a for a in actions if str(a.get("guild_id")) == str(guild_id)]
        return list(reversed(actions[-limit * 4:]))[:limit]

    # ---------- Статистика команд ----------
    async def incr_command(self, command: str) -> None:
        stats = await self.read("stats", {"commands": {}, "started_at": int(time.time())})
        stats["commands"][command] = stats["commands"].get(command, 0) + 1
        await self.write("stats", stats)

    async def get_stats(self) -> dict:
        return await self.read("stats", {"commands": {}, "started_at": int(time.time())})
