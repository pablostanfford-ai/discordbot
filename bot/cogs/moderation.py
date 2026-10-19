"""Модерация: бан, кик, мут(таймаут), варн, очистка канала, инфо о пользователе."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core import ctx


def storage():
    return ctx.storage


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Утилиты ----------
    async def _settings(self, guild_id: int) -> dict:
        return await storage().get_guild_settings(str(guild_id))

    async def _require_mod(self, interaction: discord.Interaction) -> bool:
        member = interaction.user
        if isinstance(member, discord.Member):
            if member.guild_permissions.manage_messages:
                return True
            s = await self._settings(interaction.guild.id)
            mod_role_id = s["moderation"]["mod_role_id"]
            if mod_role_id and any(str(r.id) == str(mod_role_id) for r in member.roles):
                return True
        await interaction.response.send_message("❌ Недостаточно прав (нужен Manage Messages или модер-роль).", ephemeral=True)
        return False

    async def _log(self, **kw) -> None:
        await storage().log_action(kw)

    # ---------- Slash команды ----------
    @app_commands.command(name="ban", description="Забанить участника")
    @app_commands.describe(user="Кого забанить", reason="Причина", days="Удалить сообщения за N дней")
    @app_commands.default_permissions(manage_messages=True)
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Не указана", days: int = 0):
        if not await self._require_mod(interaction):
            return
        try:
            await interaction.guild.ban(user, reason=f"[{interaction.user}] {reason}", delete_message_days=days)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Не могу забанить (у цели выше роль или нет прав).", ephemeral=True)
        await self._log(guild_id=str(interaction.guild.id), moderator_id=str(interaction.user.id),
                        moderator_tag=str(interaction.user), target_id=str(user.id), target_tag=str(user),
                        action="ban", reason=reason)
        await interaction.response.send_message(f"🔨 **{user}** забанен. Причина: {reason}")

    @app_commands.command(name="unban", description="Разбанить пользователя по ID")
    @app_commands.default_permissions(manage_messages=True)
    async def unban(self, interaction: discord.Interaction, user_id: str):
        if not await self._require_mod(interaction):
            return
        try:
            await interaction.guild.unban(discord.Object(id=int(user_id)))
        except Exception as e:
            return await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)
        await self._log(guild_id=str(interaction.guild.id), moderator_id=str(interaction.user.id),
                        moderator_tag=str(interaction.user), target_id=user_id, target_tag="",
                        action="unban", reason="")
        await interaction.response.send_message(f"✅ Пользователь `{user_id}` разбанен.")

    @app_commands.command(name="kick", description="Выгнать участника")
    @app_commands.default_permissions(manage_messages=True)
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Не указана"):
        if not await self._require_mod(interaction):
            return
        try:
            await user.kick(reason=f"[{interaction.user}] {reason}")
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Нет прав на кик этого участника.", ephemeral=True)
        await self._log(guild_id=str(interaction.guild.id), moderator_id=str(interaction.user.id),
                        moderator_tag=str(interaction.user), target_id=str(user.id), target_tag=str(user),
                        action="kick", reason=reason)
        await interaction.response.send_message(f"👢 **{user}** выгнан. Причина: {reason}")

    @app_commands.command(name="timeout", description="Выдать тайм-аут (мут)")
    @app_commands.describe(minutes="Длительность в минутах")
    @app_commands.default_permissions(manage_messages=True)
    async def timeout(self, interaction: discord.Interaction, user: discord.Member, minutes: int = 10, reason: str = "Не указана"):
        if not await self._require_mod(interaction):
            return
        from datetime import timedelta

        try:
            await user.timeout(timedelta(minutes=max(1, min(minutes, 40320))), reason=reason)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Нет прав Mod Members.", ephemeral=True)
        await self._log(guild_id=str(interaction.guild.id), moderator_id=str(interaction.user.id),
                        moderator_tag=str(interaction.user), target_id=str(user.id), target_tag=str(user),
                        action="timeout", reason=f"{minutes} мин: {reason}")
        await interaction.response.send_message(f"⏱️ **{user}** получил тайм-аут на {minutes} мин. Причина: {reason}")

    @app_commands.command(name="untimeout", description="Снять тайм-аут")
    @app_commands.default_permissions(manage_messages=True)
    async def untimeout(self, interaction: discord.Interaction, user: discord.Member):
        if not await self._require_mod(interaction):
            return
        try:
            await user.timeout(None)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        await interaction.response.send_message(f"✅ Тайм-аут с **{user}** снят.")

    @app_commands.command(name="warn", description="Выдать предупреждение")
    @app_commands.default_permissions(manage_messages=True)
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Не указана"):
        if not await self._require_mod(interaction):
            return
        entry = await self._log(guild_id=str(interaction.guild.id), moderator_id=str(interaction.user.id),
                                moderator_tag=str(interaction.user), target_id=str(user.id), target_tag=str(user),
                                action="warn", reason=reason)
        warns = [a for a in await storage().get_actions(str(interaction.guild.id), 1000)
                 if a["action"] == "warn" and str(a["target_id"]) == str(user.id)]
        await interaction.response.send_message(
            f"⚠️ **{user}** предупреждён ({len(warns)} всего). Причина: {reason}"
        )

    @app_commands.command(name="warnings", description="Показать предупреждения пользователя")
    async def warnings(self, interaction: discord.Interaction, user: discord.Member):
        warns = [a for a in await storage().get_actions(str(interaction.guild.id), 1000)
                 if a["action"] == "warn" and str(a["target_id"]) == str(user.id)]
        if not warns:
            return await interaction.response.send_message(f"✅ У {user} нет предупреждений.")
        lines = [f"`#{w['id']}` <t:{w['created_at']}:d> — {w['reason']} (от {w['moderator_tag']})" for w in warns[-10:]]
        emb = discord.Embed(title=f"⚠️ Предупреждения {user}", description="\n".join(lines), color=0xfaa61a)
        await interaction.response.send_message(embed=emb)

    @app_commands.command(name="clearwarns", description="Очистить предупреждения")
    @app_commands.default_permissions(manage_messages=True)
    async def clearwarns(self, interaction: discord.Interaction, user: discord.Member):
        if not await self._require_mod(interaction):
            return
        actions = await storage().read("modlog", [])
        remaining = [a for a in actions if not (a["action"] == "warn" and str(a.get("target_id")) == str(user.id)
                                                and str(a.get("guild_id")) == str(interaction.guild.id))]
        await storage().write("modlog", remaining)
        await interaction.response.send_message(f"✅ Предупреждения {user} очищены.")

    @app_commands.command(name="purge", description="Удалить N сообщений канала")
    @app_commands.describe(limit="Сколько сообщений удалить (1-200)")
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, limit: int = 10):
        if not await self._require_mod(interaction):
            return
        limit = max(1, min(limit, 200))
        deleted = await interaction.channel.purge(limit=limit)
        await interaction.followup.send(f"🧹 Удалено {len(deleted)} сообщений.", ephemeral=True)

    @app_commands.command(name="userinfo", description="Информация о пользователе")
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member | None = None):
        user = user or interaction.user
        rec = await storage().get_user_xp(str(interaction.guild.id), str(user.id))
        roles = ", ".join(r.mention for r in sorted(user.roles, key=lambda r: r.position, reverse=True)[:5]) or "—"
        emb = discord.Embed(color=user.color if user.color != discord.Colour.default() else 0x5865F2)
        emb.set_author(name=str(user), icon_url=str(user.display_avatar))
        emb.add_field(name="ID", value=user.id)
        emb.add_field(name="Аккаунт создан", value=f"<t:{int(user.created_at.timestamp())}:R>")
        emb.add_field(name="На сервере с", value=f"<t:{int(user.joined_at.timestamp()):R}>" if user.joined_at else "—")
        emb.add_field(name="Уровень", value=f"L{rec['level']} ({rec['xp']} XP)")
        emb.add_field(name="Роли", value=roles, inline=False)
        await interaction.response.send_message(embed=emb)


# ---------- Префиксные алиасы (!cmd) для удобства ----------
def register_prefix_aliases(bot: commands.Bot):
    @bot.command(name="ban")
    @commands.has_permissions(manage_messages=True)
    async def _ban(ctxmsg: commands.Context, member: discord.Member, *, reason="Не указана"):
        await ctxmsg.guild.ban(member, reason=reason)
        await ctxmsg.send(f"🔨 {member} забанен.")

    @bot.command(name="kick")
    @commands.has_permissions(manage_messages=True)
    async def _kick(ctxmsg: commands.Context, member: discord.Member, *, reason="Не указана"):
        await member.kick(reason=reason)
        await ctxmsg.send(f"👢 {member} выгнан.")

    @bot.command(name="warn")
    @commands.has_permissions(manage_messages=True)
    async def _warn(ctxmsg: commands.Context, member: discord.Member, *, reason="Не указана"):
        await storage().log_action(guild_id=str(ctxmsg.guild.id), moderator_id=str(ctxmsg.author.id),
                                   moderator_tag=str(ctxmsg.author), target_id=str(member.id),
                                   target_tag=str(member), action="warn", reason=reason)
        await ctxmsg.send(f"⚠️ {member} предупреждён: {reason}")

    @bot.command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def _clear(ctxmsg: commands.Context, limit: int = 10):
        deleted = await ctxmsg.channel.purge(limit=limit + 1)
        await ctxmsg.send(f"🧹 Удалено {len(deleted)-1} сообщений.")


async def setup(bot: commands.Bot):
    cog = Moderation(bot)
    await bot.add_cog(cog)
    register_prefix_aliases(bot)
