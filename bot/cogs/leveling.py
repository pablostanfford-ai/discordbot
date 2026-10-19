"""Уровни и XP: начисление за сообщения, /rank с прогресс-баром, /leaderboard, роль-награды."""
from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

from bot.core import ctx


def progress_bar(current: int, total: int, width: int = 12) -> str:
    if total <= 0:
        total = 1
    ratio = max(0.0, min(1.0, current / total))
    filled = int(round(ratio * width))
    return "▓" * filled + "░" * (width - filled) + f" {int(ratio * 100)}%"


class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_xp: dict[str, float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        s = await ctx.storage.get_guild_settings(str(message.guild.id))
        lv = s["leveling"]
        if not (s["modules"].get("leveling") and lv.get("enabled")):
            return
        key = f"{message.guild.id}:{message.author.id}"
        now = time.time()
        if now - self._last_xp.get(key, 0) < int(lv["cooldown_seconds"]):
            return
        self._last_xp[key] = now

        old = await ctx.storage.get_user_xp(str(message.guild.id), str(message.author.id))
        rec = await ctx.storage.add_xp(str(message.guild.id), str(message.author.id), int(lv["xp_per_message"]))
        if rec["level"] > old["level"]:
            await self._on_level_up(message.guild, message.author, rec["level"], s)

    async def _on_level_up(self, guild: discord.Guild, member: discord.Member, level: int, settings: dict):
        # Роль-награда
        for reward in settings["leveling"].get("role_rewards", []):
            try:
                if int(reward["level"]) == level:
                    role = guild.get_role(int(reward["role_id"]))
                    if role and role < guild.me.top_role:
                        await member.add_roles(role, reason=f"Level {level} reward")
            except (KeyError, ValueError, discord.HTTPException):
                pass
        channel = None
        cid = settings["leveling"].get("announce_channel_id")
        if cid:
            channel = guild.get_channel(int(cid))
        if channel:
            emb = discord.Embed(
                title="🎉 Уровень повышен!",
                description=f"{member.mention} достиг **{level} уровня**!",
                color=0xFEE319,
            )
            try:
                await channel.send(embed=emb)
            except discord.HTTPException:
                pass

    @app_commands.command(name="rank", description="Показать твой уровень и XP")
    async def rank(self, interaction: discord.Interaction, user: discord.Member | None = None):
        user = user or interaction.user
        rec = await ctx.storage.get_user_xp(str(interaction.guild.id), str(user.id))
        cur_lvl_xp = ctx.storage.xp_for_level(rec["level"])
        next_lvl_xp = ctx.storage.xp_for_level(rec["level"] + 1)
        into = rec["xp"] - cur_lvl_xp
        need = next_lvl_xp - cur_lvl_xp
        emb = discord.Embed(color=0x5865F2, title=f"Ранг — {user}")
        emb.set_thumbnail(url=str(user.display_avatar))
        emb.add_field(name="Уровень", value=f"{rec['level']}")
        emb.add_field(name="XP", value=f"{rec['xp']}")
        emb.add_field(name="Прогресс", value=progress_bar(into, need))
        emb.add_field(name="Сообщений", value=str(rec.get("messages", 0)))
        await interaction.response.send_message(embed=emb)

    @app_commands.command(name="leaderboard", description="Таблица лидеров по XP")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = await ctx.storage.top_xp(str(interaction.guild.id), 10)
        if not rows:
            return await interaction.response.send_message("Пока никто не набрал XP. Пишите в чат!")
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(rows, 1):
            m = interaction.guild.get_member(int(r["user_id"]))
            name = str(m) if m else f"`{r['user_id']}`"
            lines.append(f"{medals[i-1] if i <= 3 else f'{i}.'} {name} — L{r['level']} ({r['xp']} XP)")
        emb = discord.Embed(title="🏆 Таблица лидеров", description="\n".join(lines), color=0xFEE319)
        await interaction.response.send_message(embed=emb)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
