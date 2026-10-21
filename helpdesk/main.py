"""Точка входа Telegram HelpDesk: бот (aiogram) + Mini App (FastAPI/uvicorn).

Запуск:  python -m helpdesk.main
Без TELEGRAM_BOT_TOKEN поднимается только панель Mini App (режим разработки),
данные тикетов читаются/пишутся в data/telegram/tickets.json.
"""
from __future__ import annotations

import asyncio
import logging

from helpdesk.config import DATA_DIR, config
from helpdesk.store import TicketStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("helpdesk.main")

store = TicketStore(DATA_DIR)


async def run_bot() -> None:
    from helpdesk.tg_bot import setup_bot, sla_monitor

    bot, dp, _ = await setup_bot()
    if bot is None or dp is None:
        return
    asyncio.create_task(sla_monitor(store))
    # передаём хранилище в обработчики через workflow_data
    kwargs = {"store": store}
    try:
        await dp.start_polling(bot, **kwargs)
    finally:
        await bot.session.close()


async def run_web() -> None:
    import uvicorn

    from helpdesk.webapp.app import create_webapp_app

    app = create_webapp_app(store)
    cfg = uvicorn.Config(app, host=config.HOST, port=config.PORT, log_level="info")
    server = uvicorn.Server(cfg)
    log.info("Mini App «Панель тикетов» доступен: %s/app (порт %s)", config.BASE_URL, config.PORT)
    await server.serve()


async def main() -> None:
    tasks = [asyncio.create_task(run_web())]
    if config.has_bot_token():
        tasks.append(asyncio.create_task(run_bot()))
    else:
        log.warning("⚠️  TELEGRAM_BOT_TOKEN не задан → запускаю только Mini App (dev-режим). "
                    "Кнопка «Засеять демо» создаст тестовые тикеты.")
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    for t in pending:
        t.cancel()
    for t in done:
        exc = t.exception()
        if exc:
            log.error("Задача упала: %r", exc)
            raise exc


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")
