"""Логирование событий сервера в указанный канал (настраивается через дашборд)."""
from __future__ import annotations

import discord
from discord.ext import commands

from bot.core import ctx


class ServerLogging(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _channel_and_enabled(self, guild: discord.Guild, event: str):
        s = await ctx.storage.get_guild_settings(str(guild.id))
        cfg = s["logging"]
        if not (s["modules"].get("logging") and cfg.get("enabled")):
            return None
        if event not in cfg.get("events", []):
            return None
        cid = cfg.get("channel_id")
        if not cid:
            return None
        ch = guild.get_channel(int(cid))
        return ch if isinstance(ch, discord.TextChannel) else None

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.content == after.content:
            return
        ch = await self._channel_and_enabled(before.guild, "message_edit")
        if not ch:
            return
        emb = discord.Embed(
            title="✏️ Сообщение изменено",
            color=0xFEE75C,
            description=f"**Канал:** {before.channel.mention}\n**Автор:** {before.author.mention}",
        )
        emb.add_field(name="Было", value=(before.content[:500] or "*пусто*"), inline=False)
        emb.add_field(name="Стало", value=(after.content[:500] or "*пусто*"), inline=False)
        try:
            await ch.send(embed=emb)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot:
            return
        ch = await self._channel_and_enabled(message.guild, "message_delete")
        if not ch:
            return
        emb = discord.Embed(
            title="🗑️ Сообщение удалено",
            color=0xED4245,
            description=f"**Канал:** {message.channel.mention}\n**Автор:** {message.author.mention}\n"
                        f"{(message.content[:500] or '*без текста*')}",
        )
        try:
            await ch.send(embed=emb)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        ch = await self._channel_and_enabled(member.guild, "member_join")
        if not ch:
            return
        emb = discord.Embed(
            description=f"📥 **{member}** присоединился ({member.guild.member_count}-й участник).",
            color=0x57F287,
        )
        emb.set_thumbnail(url=str(member.display_avatar))
        try:
            await ch.send(embed=emb)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        ch = await self._channel_and_enabled(member.guild, "member_leave")
        if not ch:
            return
        emb = discord.Embed(
            description=f"📤 **{member}** покинул сервер.",
            color=0xED4245,
        )
        emb.set_thumbnail(url=str(member.display_avatar))
        try:
            await ch.send(embed=emb)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerLogging(bot))
