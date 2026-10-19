"""Утилиты: /ping, /invite, /help, /serverinfo, /avatar, /poll, префиксная !help."""
from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.core import ctx


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Пинг и аптайм бота")
    async def ping(self, interaction: discord.Interaction):
        ws = round(self.bot.latency * 1000)
        up = int(time.time() - ctx.started_at) if ctx.started_at else 0
        h, rem = divmod(up, 3600)
        m, s = divmod(rem, 60)
        emb = discord.Embed(title="🏓 Pong!", color=0x57F287)
        emb.add_field(name="WebSocket", value=f"{ws} ms")
        emb.add_field(name="Аптайм", value=f"{h}ч {m}м {s}с")
        await interaction.response.send_message(embed=emb)

    @app_commands.command(name="invite", description="Ссылка приглашения бота")
    async def invite(self, interaction: discord.Interaction):
        url = config.invite_url(permissions=8 | 4096 | 268500032)
        if not url:
            return await interaction.response.send_message("CLIENT_ID не настроен.", ephemeral=True)
        await interaction.response.send_message(f"➕ [Пригласить бота]({url})")

    @app_commands.command(name="serverinfo", description="Информация о сервере")
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        owner = f"<@{g.owner_id}>"
        emb = discord.Embed(title=g.name, color=0x5865F2, timestamp=discord.utils.utcnow())
        if g.icon:
            emb.set_thumbnail(url=str(g.icon))
        emb.add_field(name="Владелец", value=owner)
        emb.add_field(name="Участников", value=str(g.member_count))
        emb.add_field(name="Каналов", value=str(len(g.channels)))
        emb.add_field(name="Ролей", value=str(len(g.roles)))
        emb.add_field(name="Создан", value=f"<t:{int(g.created_at.timestamp())}:R>")
        emb.add_field(name="ID", value=str(g.id))
        await interaction.response.send_message(embed=emb)

    @app_commands.command(name="avatar", description="Показать аватар пользователя")
    async def avatar(self, interaction: discord.Interaction, user: discord.Member | None = None):
        user = user or interaction.user
        emb = discord.Embed(title=f"Аватар {user}", color=0x5865F2)
        emb.set_image(url=str(user.display_avatar))
        await interaction.response.send_message(embed=emb)

    @app_commands.command(name="poll", description="Создать опрос с реакциями ✅ ❌")
    @app_commands.describe(question="Текст опроса")
    async def poll(self, interaction: discord.Interaction, question: str):
        emb = discord.Embed(title="📊 Опрос", description=question, color=0xEB459E)
        msg = await interaction.response.send_message(embed=emb)
        try:
            m = await interaction.original_response()
            await m.add_reaction("✅")
            await m.add_reaction("❌")
        except discord.HTTPException:
            pass

    @app_commands.command(name="help", description="Список команд бота")
    async def slash_help(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._help_embed(), ephemeral=True)

    def _help_embed(self) -> discord.Embed:
        emb = discord.Embed(
            title="📖 Команды бота",
            description=(
                "**Модерация** (slash + префикс):\n"
                "`/ban` `/unban` `/kick` `/timeout` `/untimeout` `/warn` `/warnings` `/clearwarns` `/purge`\n\n"
                "**Инфо:** `/userinfo` `/serverinfo` `/ping` `/invite` `/avatar` `/poll`\n\n"
                "**Уровни:** `/rank` `/leaderboard`\n\n"
                f"**Префикс:** `{self.prefix_default}` — `!ban @user`, `!warn @user`, `!clear 10`\n\n"
                "⚙️ Полный контроль модулей — в **дашборде**."
            ),
            color=0x5865F2,
        )
        return emb

    @property
    def prefix_default(self) -> str:
        return "!"


async def setup(bot: commands.Bot):
    cog = Utility(bot)
    await bot.add_cog(cog)

    if bot.get_command("help") is None:
        @bot.command(name="help")
        async def _help(ctxmsg: commands.Context):
            await ctxmsg.send(embed=cog._help_embed())
