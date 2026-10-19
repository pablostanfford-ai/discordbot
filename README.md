# Discord Bot + UniPer-style Dashboard

Полнофункциональный Discord-бот на **discord.py** сslash-командами, модерацией,
автонастройками (auto-moderation), приветствиями/провожаниями, логированием,
уровнями/XP, музыкой-заглушкой и административным **веб-дашбордом в стиле UniPer**:
OAuth2-логин через Discord, панель серверов, настройка модулей, статистика,
список участников, журнал действий — всё через REST API бота.

## Архитектура
```
/workspace
├── bot/                # Ядро бота (discord.py)
│   ├── main.py         # Точка входа: запуск бота + веба
│   ├── config.py       # Загрузка настроек из .env / env-переменных
│   ├── storage.py      # JSON-хранилище настроек/данных по гильдиям
│   ├── core.py         # Глобальный контекст (bot, storage, http) для веба
│   └── cogs/           # Модули команд
│       ├── moderation.py
│       ├── automod.py
│       ├── welcome.py
│       ├── leveling.py
│       ├── utility.py
│       ├── logging_cog.py
│       └── settings_sync.py  # применяет настройки из дашборда на лету
├── web/                # DASHBOARD (FastAPI + Jinja + vanilla JS)
│   ├── app.py          # роуты, OAuth2, REST API
│   ├── auth.py         # JWT-сессии
│   ├── templates/      # HTML страницы (UniPer-like дизайн)
│   └── static/         # CSS/JS
├── data/               # runtime JSON (settings, stats, audit log)
├── .env.example
└── requirements.txt
```

## Быстрый старт
1. Создайте приложение на https://discord.com/developers → включите
   `Server Members`, `Message Content`, `Guilds` intents и скопируйте Token / Client ID / Secret.
2. `cp .env.example .env` и заполните значения.
3. `pip install -r requirements.txt`
4. `python -m bot.main`  → бот + дашборд на http://localhost:8050
5. В Дискорде откройте ссылку приглашения из `/invite` или со страницы логина дашборда.

## Демо-режим (без реального токена)
Если `DISCORD_TOKEN` пустой, запускается **только дашборд** с мок-данными
(`DEMO_MODE=1`), чтобы можно было посмотреть интерфейс без бота.
