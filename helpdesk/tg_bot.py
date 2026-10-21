"""Telegram-бот технической поддержки (aiogram 3).

Пользователь: /start → выбор категории → описание проблемы (+ скриншоты) → тикет.
Любое сообщение пользователя попадает в его открытый тикет, ответы оператора
бот доставляет прямо в личку. Операторы получают уведомления о новых тикетах,
нарушениях SLA и кнопку «Открыть панель» (Mini App).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from helpdesk.config import config
from helpdesk.store import STATUS_CLOSED, TicketStore

log = logging.getLogger("helpdesk.bot")
router = Router()

CATEGORIES = {
    "login": "🔑 Проблема со входом",
    "network": "🌐 Сеть / соединение",
    "payment": "💳 Оплата и подписка",
    "bug": "🐛 Ошибка / баг",
    "other": "📩 Другое",
}

DEMO_TICKET_ID = "demo000001"

# ---------- клавиатуры ----------
def categories_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text, callback_data=f"cat:{key}")] for key, text in CATEGORIES.items()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton("🛠 Открыть панель тикетов", web_app={"url": config.webapp_url()}),
    ]])


def ticket_link_kb(ticket_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton("💬 Ответить в чате", web_app={"url": f"{config.webapp_url()}/?ticket={ticket_id}"}),
    ]])


def _category_title(key: str) -> str:
    return CATEGORIES.get(key, key)


# ---------- handlers ----------
@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "👋 Привет! Я бот технической поддержки.\n\n"
        "Опишите свою проблему — я создам тикет, и оператор ответит вам здесь, в этом чате.\n\n"
        "Выберите категорию обращения:",
        reply_markup=categories_kb(),
    )


@router.callback_query(F.data.startswith("cat:"))
async def choose_category(cb: CallbackQuery, store: TicketStore) -> None:
    key = cb.data.split(":", 1)[1]
    await cb.answer()
    if key not in CATEGORIES:
        await cb.message.answer("Неизвестная категория. Отправьте /start")
        return
    await cb.message.answer(
        f"Категория: <b>{_category_title(key)}</b>\n\n"
        "Теперь опишите проблему как можно подробнее (что происходит, когда началось, "
        "что уже пробовали). Можно текстом или парой сообщений — я соберу их в один тикет.",
    )
    state[cb.from_user.id] = {"category": key}


@router.message(F.text & ~F.is_command())
async def user_message(message: Message, store: TicketStore) -> None:
    uid = message.from_user.id
    await store.remember_user(uid, message.from_user.username or "", message.from_user.full_name)

    pending = state.pop(uid, None)
    open_ticket = await find_open_ticket(store, uid)

    if pending is not None and pending.get("category"):
        ticket = await store.create_ticket(
            user_id=uid,
            category=pending["category"],
            text=message.text,
            username=message.from_user.username or "",
            full_name=message.from_user.full_name,
        )
        await message.answer(
            f"✅ Тикет <b>#{ticket['number']}</b> создан ({_category_title(ticket['category'])}).\n"
            "Оператор получит уведомление и ответит здесь. Обычно отвечаем в рабочее время.\n\n"
            "💡 Если есть скриншот ошибки — пришлите его фото, это ускорит решение.",
        )
        await notify_admins(store, ticket)
        return

    if open_ticket:
        updated = await store.add_message(open_ticket["id"], "user", message.text)
        await message.answer("📨 Сообщение добавлено в ваш тикет "
                             f"<b>#{open_ticket['number']}</b>. Ожидайте ответа оператора.")
        if updated:
            await notify_admins_message(updated, message.text)
        return

    # нет открытого тикета — предложим создать новый
    state[uid] = {"category": None}
    await message.reply(
        "У вас нет открытого тикета. Выберите категорию, чтобы обратиться в поддержку 👇",
        reply_markup=categories_kb(),
    )


@router.message(F.photo)
async def user_photo(message: Message, store: TicketStore) -> None:
    """Скриншот от пользователя → скачиваем и прикрепляем к открытому тикету."""
    uid = message.from_user.id
    await store.remember_user(uid, message.from_user.username or "", message.from_user.full_name)
    open_ticket = await find_open_ticket(store, uid)
    if not open_ticket:
        await message.reply("Сначала опишите проблему текстом — отправьте /start 👆")
        return
    photo = message.photo[-1]  # самое большое разрешение
    url = await download_photo(photo.file_unique_id, config.PHOTO_DIR / f"{photo.file_unique_id}.jpg")
    caption = (message.caption or "").strip()
    updated = await store.add_message(open_ticket["id"], "user",
                                      caption or "📷 Скриншот от клиента",
                                      kind="photo", photo_url=url)
    await message.answer(f"📷 Скриншот прикреплён к тикету <b>#{open_ticket['number']}</b>.")
    if updated and url:
        await notify_admins_message(updated, f"прислал(а) скриншот. {caption[:200]}")


@router.message(~F.text & ~F.photo)
async def unsupported(message: Message) -> None:
    await message.answer("Пока я принимаю текст и скриншоты (фото) 🙂 "
                         "Пришлите описание проблемы или снимок экрана.")


@router.message(F.text == "/myticket")
async def my_ticket(message: Message, store: TicketStore) -> None:
    t = await find_open_ticket(store, message.from_user.id)
    if not t:
        await message.answer("Открытых тикетов нет. Отправьте /start, чтобы создать новый.")
        return
    last = t["messages"][-1]["text"][:200]
    await message.answer(
        f"🎫 Тикет <b>#{t['number']}</b> · {_category_title(t['category'])} · статус: {t['status']}\n"
        f"Последнее сообщение: «{last}»\n\nПросто напишите новое сообщение — оно добавится в тикет."
    )


@router.message(F.text.startswith("/answer "))
async def agent_answer_via_chat(message: Message, store: TicketStore) -> None:
    """Резервный путь: оператор может ответить прямо в чате командой /answer <номер> <текст>."""
    if not config.is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /answer <номер тикета> <текст ответа>")
        return
    number, text = parts[1], parts[2]
    tickets = await store.list_tickets(limit=1000)
    target = next((t for t in tickets if str(t["number"]) == number.lstrip("#")), None)
    if not target:
        await message.answer(f"Тикет #{number} не найден.")
        return
    await store.add_message(target["id"], "agent", text)
    await message.answer(f"✅ Ответ отправлен в тикет #{target['number']}.")


# ---------- внутренняя логика ----------
state: dict[int, dict] = {}  # uid -> {"category": ...}: пользователь выбрал категорию, ждём текст


async def find_open_ticket(store: TicketStore, uid: int) -> dict | None:
    tickets = await store.list_tickets(status=None, limit=1000)
    for t in tickets:
        if t["user_id"] == uid and t["status"] != STATUS_CLOSED:
            full = await store.get_ticket(t["id"])
            return full
    return None


async def notify_admins(store: TicketStore, ticket: dict) -> None:
    bot = get_bot()
    if bot is None:
        log.info("[демо] Новое обращение #%s от %s: %s",
                 ticket["number"], ticket["full_name"], ticket["messages"][0]["text"][:80])
        return
    text = (
        f"🆕 <b>Новое обращение #{ticket['number']}</b>\n"
        f"👤 {ticket['full_name']} @{ticket['username'] or '—'} (id <code>{ticket['user_id']}</code>)\n"
        f"🏷 Категория: {_category_title(ticket['category'])}\n"
        f"💬 {ticket['messages'][0]['text'][:500]}"
    )
    for admin_id in admin_ids():
        try:
            await bot.send_message(admin_id, text, reply_markup=ticket_link_kb(ticket["id"]), parse_mode="HTML")
        except Exception as e:  # noqa: BLE001
            log.warning("Не удалось уведомить админа %s: %s", admin_id, e)


async def notify_admins_message(ticket: dict, text: str) -> None:
    bot = get_bot()
    if bot is None:
        log.info("[демо] Ответ пользователя в #%s: %s", ticket["number"], text[:80])
        return
    msg = (f"⬆️ Пользователь добавил сообщение в тикет <b>#{ticket['number']}</b> "
           f"({ticket['full_name']}):\n{text[:500]}")
    for admin_id in admin_ids():
        try:
            await bot.send_message(admin_id, msg, reply_markup=ticket_link_kb(ticket["id"]), parse_mode="HTML")
        except Exception as e:  # noqa: BLE001
            log.warning("Не удалось уведомить админа %s: %s", admin_id, e)


async def deliver_agent_reply(user_id: int, ticket_number: int, text: str) -> bool:
    """Доставляет ответ оператора пользователю в личку. В демо — просто лог."""
    bot = get_bot()
    if bot is None:
        log.info("[демо] Ответ оператором #%s → user %s: %s", ticket_number, user_id, text[:120])
        return True
    try:
        await bot.send_message(user_id, f"💬 <b>Ответ по тикету #{ticket_number}</b>:\n\n{text}", parse_mode="HTML")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Пользователь %s не принимает сообщения: %s", user_id, e)
        return False


async def deliver_status_notice(user_id: int, ticket_number: int, status: str) -> None:
    bot = get_bot()
    texts = {
        STATUS_CLOSED: f"✅ Тикет <b>#{ticket_number}</b> закрыт. Если проблема осталась — напишите /start снова.",
        "open": f"🔓 Тикет <b>#{ticket_number}</b> снова открыт оператором.",
        "in_progress": f"⏳ Тикет <b>#{ticket_number}</b> принят в работу.",
    }
    text = texts.get(status)
    if not text or bot is None:
        log.info("[демо] Статус #%s → %s (%s)", ticket_number, status, user_id)
        return
    try:
        await bot.send_message(user_id, text, parse_mode="HTML")
    except Exception as e:  # noqa: BLE001
        log.warning("Не удалось отправить статус пользователю %s: %s", user_id, e)


# ---------- скриншоты ----------
async def download_photo(file_unique_id: str, dest: Path) -> str | None:
    """Скачивает фото по file_unique_id в data/photos/. Возвращает URL /photos/<file>."""
    bot = get_bot()
    if bot is None:
        return None
    try:
        file = await bot.get_file(file_unique_id)
        await bot.download_file(file.file_path, str(dest))
        return f"/photos/{dest.name}"
    except Exception as e:  # noqa: BLE001
        log.warning("Не удалось скачать фото %s: %s", file_unique_id, e)
        return None


# ---------- SLA-монитор ----------
async def sla_monitor(store: TicketStore, interval: int = 60) -> None:
    """Раз в interval секунд ищет тикеты с просроченным SLA и уведомляет операторов."""
    while True:
        try:
            await asyncio.sleep(interval)
            for t in await store.overdue_sla():
                await notify_admins_sla(t)
                await store.mark_sla_notified(t["id"])
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("Ошибка SLA-монитора: %s", e)


async def notify_admins_sla(ticket: dict) -> None:
    bot = get_bot()
    if bot is None:
        log.info("[демо] SLA просрочен в #%s (%s)", ticket["number"], ticket["full_name"])
        return
    text = (f"⚠️ <b>SLA просрочен!</b> Тикет <b>#{ticket['number']}</b> без ответа\n"
            f"👤 {ticket['full_name']} · {_category_title(ticket['category'])}")
    for admin_id in admin_ids():
        try:
            await bot.send_message(admin_id, text, reply_markup=ticket_link_kb(ticket["id"]), parse_mode="HTML")
        except Exception as e:  # noqa: BLE001
            log.warning("Не удалось уведомить админа %s: %s", admin_id, e)


# ---------- запуск ----------
_bot: Bot | None = None


def get_bot() -> Bot | None:
    return _bot


def admin_ids() -> set[int]:
    return config.ADMIN_IDS or DEMO_ADMINS


DEMO_ADMINS: set[int] = set()


async def setup_bot() -> tuple[Bot, Dispatcher, Router] | tuple[None, None, None]:
    global _bot
    if not config.has_bot_token():
        log.warning("TELEGRAM_BOT_TOKEN не задан → бот не запускается (режим разработки Mini App).")
        return None, None, None
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    _bot = bot
    # команда /start с кнопкой панели для админов + меню бота
    try:
        cmds = [
            {"command": "start", "description": "Начать обращение в поддержку"},
            {"command": "myticket", "description": "Мой текущий тикет"},
            {"command": "panel", "description": "Панель оператора (для админа)"},
        ]
        await bot.set_my_commands(cmds)
    except Exception as e:  # noqa: BLE001
        log.warning("set_my_commands не удался: %s", e)
    me = await bot.get_me()
    log.info("Telegram-бот поддержки онлайн: @%s", me.username)
    return bot, dp, router


@router.message(F.text == "/panel")
async def cmd_panel(message: Message) -> None:
    if not config.is_admin(message.from_user.id):
        await message.answer("Команда доступна только операторам поддержки.")
        return
    await message.answer("🛠 Панель оператора:", reply_markup=panel_kb())
