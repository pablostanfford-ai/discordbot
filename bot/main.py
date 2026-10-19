"""Точка входа: запускает Discord-бота (если есть токен) и веб-дашборд (uvicorn)."""
from __future__ import annotations

import asyncio
import logging
import time

import discord
from discord.ext import commands

from bot.config import DATA_DIR, config
from bot.core import ctx
from bot.storage import JsonStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("bot.main")

COGS = [
    "bot.cogs.moderation",
    "bot.cogs.automod",
    "bot.cogs.welcome",
    "bot.cogs.leveling",
    "bot.cogs.logging_cog",
    "bot.cogs.utility",
    "bot.cogs.settings_sync",
]


def get_prefix(bot: commands.Bot, message: discord.Message) -> str:
    # Асинхронный доступ невозможен в синхронном get_prefix — кэшируем дефолт,
    # реальный префикс применяется через on_message ниже.
    return "!"


class DashBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix=get_prefix, intents=intents, help_command=None)

    async def setup_hook(self):
        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info("Загружен cog: %s", cog)
            except Exception as e:  # noqa: BLE001
                log.exception("Не удалось загрузить %s: %s", cog, e)
        try:
            synced = await self.tree.sync()
            ctx.tree_ready = True
            log.info("Slash-команды синхронизированы: %d шт.", len(synced))
        except Exception as e:  # noqa: BLE001
            log.warning("tree.sync не удался: %s", e)

    async def on_ready(self):
        log.info("Бот онлайн как %s (id=%s), гильдий: %d", self.user, self.user.id, len(self.guilds))

    async def on_message(self, message: discord.Message):
        if message.author.bot or not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return
        s = await ctx.storage.get_guild_settings(str(message.guild.id))
        prefix = s.get("prefix", "!")
        if message.content.startswith(prefix):
            try:
                processed = await self.process_commands(message)
                if processed:
                    await ctx.storage.incr_command(message.content[len(prefix):].split()[0])
            except commands.CommandNotFound:
                pass
            return
        # Сообщения без команд всё равно проходят через коги (leveling/automod слушают on_message)
        self.dispatch("message_without_command", message)
        await super().on_message(message)


async def run_bot():
    bot = DashBot()
    ctx.bot = bot
    ctx.started_at = int(time.time())
    await bot.start(config.DISCORD_TOKEN)


async def main():
    ctx.storage = JsonStore(DATA_DIR)
    ctx.demo_mode = not config.has_bot_credentials()

    # Импортируем приложение после инициализации контекста
    from web.app import create_app

    app = create_app()

    import uvicorn

    web_task = asyncio.create_task(
        _serve(uvicorn.Config(app, host=config.HOST, port=config.PORT, log_level="warning"))
    )

    if not ctx.demo_mode:
        log.info("Запускаю Discord-бота…")
        bot_task = asyncio.create_task(run_bot())
        done, pending = await asyncio.wait([web_task, bot_task], return_when=asyncio.FIRST_EXCEPTION)
        for t in pending:
            t.cancel()
        for t in done:
            exc = t.exception()
            if exc:
                log.error("Задача упала: %r", exc)
                raise exc
    else:
        log.warning("⚠️ DISCORD_TOKEN не задан → ДЕМО-РЕЖИМ дашборда (без бота).")
        await web_task


async def _serve(uvicorn_config):
    import uvicorn

    server = uvicorn.Server(uvicorn_config)
    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")
