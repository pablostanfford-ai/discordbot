"""Демо-данные для режима без Discord-токена (дашборд можно посмотреть сразу)."""
from __future__ import annotations

DEMO_GUILDS = [
    {
        "id": "100000000000000001",
        "name": "UniPer Demo Server",
        "icon": None,
        "owner": True,
        "permissions": 8,
        "bot_present": True,
        "member_count": 1247,
        "channels_count": 34,
        "roles_count": 12,
    },
    {
        "id": "100000000000000002",
        "name": "Русский Игровой Клуб",
        "icon": None,
        "owner": False,
        "permissions": 8,
        "bot_present": True,
        "member_count": 5820,
        "channels_count": 78,
        "roles_count": 25,
    },
]

DEMO_USER = {
    "id": "111111111111111111",
    "username": "DemoUser",
    "discriminator": "0",
    "avatar": None,
}

_DEMO_MEMBERS = [
    ("200000000000000001", "Alex_Pro", "57F287", 42, 12840),
    ("200000000000000002", "Masha_Dev", "EB459E", 38, 11230),
    ("200000000000000003", "Streamer_228", "FEE319", 31, 9015),
    ("200000000000000004", "NikitaK", "5865F2", 27, 7777),
    ("200000000000000005", "Katya_Gg", "ED4245", 24, 6320),
    ("200000000000000006", "ModerBotFan", "3BA55D", 19, 4510),
    ("200000000000000007", "Sanya_VR", "9B59B6", 15, 3220),
    ("200000000000000008", "Lena_Art", "E67E22", 12, 2100),
]


def demo_members(guild_id: str) -> list[dict]:
    out = []
    for i, (uid, name, color, level, xp) in enumerate(_DEMO_MEMBERS):
        out.append({
            "id": uid,
            "username": name,
            "discriminator": str(i % 9999),
            "avatar_color": color,
            "bot": name == "ModerBotFan",
            "joined_at": 1700000000 + i * 86400,
            "level": level,
            "xp": xp,
            "roles": ["Member"],
        })
    return out


def demo_channels(guild_id: str) -> list[dict]:
    names = ["general", "welcome", "off-topic", "gaming", "music", "memes", "bot-logs", "announcements"]
    return [{"id": f"{guild_id[-3:]}{i}", "name": n, "type": "text"} for i, n in enumerate(names)]


def demo_roles(guild_id: str) -> list[dict]:
    roles = [("Admin", "ED4245"), ("Moderator", "57F287"), ("VIP", "FEE319"),
             ("Muted", "95A5A6"), ("Member", "5865F2"), ("Bots", "7289DA")]
    return [{"id": f"{guild_id[-3:]}r{i}", "name": n, "color": c} for i, (n, c) in enumerate(roles)]


def demo_modlog(guild_id: str) -> list[dict]:
    base = [
        {"action": "ban", "moderator_tag": "Alex_Pro", "target_tag": "Spammer#1234", "reason": "Реклама в ЛС", "delta": 2},
        {"action": "timeout", "moderator_tag": "Masha_Dev", "target_tag": "ToxicUser#4321", "reason": "Оскорбления в голосовом", "delta": 5},
        {"action": "warn", "moderator_tag": "Alex_Pro", "target_tag": "NewGuy#0001", "reason": "Флуд в #general", "delta": 9},
        {"action": "automod", "moderator_tag": "AutoMod", "target_tag": "LinkSpam#7777", "reason": "спам ссылками (7)", "delta": 12},
        {"action": "kick", "moderator_tag": "NikitaK", "target_tag": "AltAccount#5555", "reason": "Мультиаккаунтинг", "delta": 26},
        {"action": "warn", "moderator_tag": "Masha_Dev", "target_tag": "ToxicUser#4321", "reason": "Provocation", "delta": 31},
        {"action": "automod", "moderator_tag": "AutoMod", "target_tag": "RandomUser#2222", "reason": "запрещённое слово: дурак", "delta": 44},
        {"action": "unban", "moderator_tag": "Alex_Pro", "target_tag": "OldTimer#9999", "reason": "Апелляция принята", "delta": 50},
    ]
    import time as _t

    now = int(_t.time())
    return [
        {
            "id": len(base) - i,
            "guild_id": guild_id,
            "created_at": now - e["delta"] * 3600,
            "moderator_id": "0",
            "target_id": "0",
            **e,
        }
        for i, e in enumerate(base)
    ]
