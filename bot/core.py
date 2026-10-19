"""Глобальный контекст приложения: доступ к боту и хранилищу из веб-слоя."""
from __future__ import annotations

from typing import Optional

from bot.storage import JsonStore


class AppContext:
    bot: Optional[object] = None          # discord.Client (после запуска)
    tree_ready: bool = False              # slash-команды синхронизированы
    storage: Optional[JsonStore] = None
    demo_mode: bool = False               # дашборд работает без реального бота
    started_at: int = 0


ctx = AppContext()
