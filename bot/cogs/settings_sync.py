"""Синхронизация настроек из дашборда с живым ботом: события и статусы."""
from __future__ import annotations

import discord
from discord.ext import commands

from bot.core import ctx


class SettingsSync(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Статус "View Dashboard" с ссылкой на дашборд
        try:
            await self.bot.change_presence(
                activity=discord.CustomActivity(name=f"📊 {ctx.__dict__.get('base_url', 'Дашборд')}")
            )
        except Exception:
            pass
        try:
            await self.bot.change_presence(
                activity=discord.Activity(type=discord.ActivityType.watching, name="дашборд | /help")
            )
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # Создаём запись настроек по умолчанию, чтобы она сразу появилась в дашборде
        await ctx.storage.get_guild_settings(str(guild.id))
        for ch in guild.text_channels:
            if ch.name == "bot-logs":
                break
        else:
            try:
                overwrites = [discord.PermissionOverwrite(view_channel=False)]
                owner = guild.get_member(guild.owner_id)
                if owner:
                    overwrites = [(owner, discord.PermissionOverwrite(view_channel=True))]
                await guild.create_text_channel("bot-logs", overwrites=overwrites,
                                                reason="Авто-создан для логов бота")
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsSync(bot))
