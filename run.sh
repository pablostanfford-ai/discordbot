#!/usr/bin/env bash
# Запуск бота + дашборда. Скопируйте .env.example в .env и заполните токены.
set -e
cd "$(dirname "$0")"
[ -f .env ] || { echo "⚠️  .env не найден — копирую из .env.example (демо-режим)"; cp .env.example .env; }
pip install -q -r requirements.txt

# Discord-бот + дашборд (основной запуск):
# exec python3 -m bot.main

# Telegram HelpDesk (бот поддержки + Mini App, порт из TG_PORT):
exec python3 -m helpdesk.main
