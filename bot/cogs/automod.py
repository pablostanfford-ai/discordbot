"""Авто-модерация: спам упоминаниями, ссылки, запрещённые слова. Настройки из дашборда."""
from __future__ import annotations

import re

import discord
from discord.ext import commands

from bot.core import ctx

LINK_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def settings_for(self, guild_id: str) -> dict:
        return await ctx.storage.get_guild_settings(guild_id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        s = await self.settings_for(str(message.guild.id))
        cfg = s["automod"]
        mods = s["modules"]
        if not (mods.get("automod") and cfg.get("enabled")):
            return
        if str(message.channel.id) in [str(c) for c in cfg["ignore_channels"]]:
            return
        if str(message.author.id) in [str(u) for u in cfg["whitelist_users"]]:
            return
        try:
            me = message.guild.me
            if me and me.guild_permissions.manage_messages is False:
                return
        except Exception:
            pass

        content = (message.content or "").lower()
        violations: list[str] = []

        mentions = len(message.role_mentions) + len(message.mentioned_users)
        if mentions > int(cfg["max_mentions"]):
            violations.append(f"спам упоминаниями ({mentions})")

        links = LINK_RE.findall(content)
        if len(links) > int(cfg["max_links"]):
            violations.append(f"спам ссылками ({len(links)})")

        hit_words = [w for w in cfg["banned_words"] if w and w.lower() in content]
        if hit_words:
            violations.append(f"запрещённое слово: {', '.join(hit_words)}")

        if not violations:
            return

        action = cfg.get("action", "delete")
        reason = "; ".join(violations)
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        if action in ("timeout", "kick") and isinstance(message.author, discord.Member):
            try:
                if action == "timeout":
                    from datetime import timedelta

                    await message.author.timeout(timedelta(minutes=int(cfg["timeout_minutes"])),
                                                reason=f"AutoMod: {reason}")
                else:
                    await message.author.kick(reason=f"AutoMod: {reason}")
            except discord.Forbidden:
                pass

        await ctx.storage.log_action(
            guild_id=str(message.guild.id), moderator_id="AutoMod", moderator_tag="AutoMod",
            target_id=str(message.author.id), target_tag=str(message.author),
            action="automod", reason=reason,
        )
        try:
            await message.channel.send(
                f"⚠️ Сообщение от {message.author.mention} удалено (AutoMod): {reason}",
                delete_after=8,
            )
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
