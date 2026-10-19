"""Приветствия и провожания + автороли. Настройки берутся из дашборда в реальном времени."""
from __future__ import annotations

import discord
from discord.ext import commands

from bot.core import ctx


def render(template: str, member: discord.Member) -> str:
    return (
        template.replace("{user}", str(member))
        .replace("{mention}", member.mention)
        .replace("{guild_name}", member.guild.name)
        .replace("{server_count}", str(member.guild.member_count))
        .replace("{member_count}", str(member.guild.member_count))
    )


def parse_color(value: str | None, default: int = 0x5865F2) -> int:
    if not value:
        return default
    try:
        return int(str(value).lstrip("#"), 16)
    except ValueError:
        return default


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        s = await ctx.storage.get_guild_settings(str(member.guild.id))
        w = s["welcome"]
        if not (s["modules"].get("welcome") and w.get("enabled")):
            return

        # Автороли
        for role_id in w.get("autorole_ids", []):
            try:
                role = member.guild.get_role(int(role_id))
                if role and role < member.guild.me.top_role:
                    await member.add_roles(role, reason="Welcome autorole (dashboard)")
            except (discord.Forbidden, discord.HTTPException):
                pass

        channel = member.guild.get_channel(int(w["channel_id"])) if w.get("channel_id") else None
        if channel is None:
            channel = discord.utils.get(member.guild.text_channels, name="welcome")
        if channel is None:
            return

        emb = discord.Embed(
            description=render(w["message"], member),
            color=parse_color(w.get("embed_color")),
            timestamp=discord.utils.utcnow(),
        )
        emb.set_thumbnail(url=str(member.display_avatar))
        emb.set_footer(text=f"ID: {member.id}")
        try:
            await channel.send(content=member.mention, embed=emb)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        s = await ctx.storage.get_guild_settings(str(member.guild.id))
        w = s["welcome"]
        if not (s["modules"].get("welcome") and w.get("enabled")):
            return
        channel = member.guild.get_channel(int(w["channel_id"])) if w.get("channel_id") else None
        if channel is None:
            return
        emb = discord.Embed(
            description=render(w.get("leave_message", "{user} покинул сервер."), member),
            color=0xED4245,
        )
        emb.set_thumbnail(url=str(member.display_avatar))
        try:
            await channel.send(embed=emb)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
