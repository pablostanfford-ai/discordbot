#!/usr/bin/env bash
# Запуск бота + дашборда. Скопируйте .env.example в .env и заполните токены.
set -e
cd "$(dirname "$0")"
[ -f .env ] || { echo "⚠️  .env не найден — копирую из .env.example (демо-режим)"; cp .env.example .env; }
pip install -q -r requirements.txt
exec python3 -m bot.main
