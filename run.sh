#!/usr/bin/env bash
# Запуск Telegram HelpDesk (бот поддержки + Mini App панель).
# Discord-бот (bot/ + web/) — отдельный проект, здесь не запускается.
set -e
cd "$(dirname "$0")"
[ -f .env ] || { echo "⚠️  .env не найден — копирую из .env.example (демо-режим)"; cp .env.example .env; }
pip install -q -r requirements.txt
exec python3 -m helpdesk.main
