import asyncio
import logging
import os
from decimal import Decimal
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import database as db
from marketplaces.portals import PortalsMarketplace

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("gift-radar")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
POLL_INTERVAL = max(20, int(os.getenv("POLL_INTERVAL_SECONDS", "60")))
# Portals reports prices in GRAM. Set this only after verifying a current GRAM->TON rate.
GRAM_TO_TON_RATE = os.getenv("GRAM_TO_TON_RATE", "").strip()

CATEGORIES = [
    ("5", "💸 Дешёвые · до 5 TON", Decimal("0"), Decimal("5")),
    ("10", "💎 10 TON · 5–15 TON", Decimal("5"), Decimal("15")),
    ("20", "🔥 20 TON · 15–27.5 TON", Decimal("15"), Decimal("27.5")),
    ("35", "🚀 35 TON · 27.5–60 TON", Decimal("27.5"), Decimal("60")),
    ("60", "👑 60+ TON", Decimal("60"), Decimal("Infinity")),
]

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
portals = PortalsMarketplace()


def category_for(price: Decimal) -> str:
    for key, _label, low, high in CATEGORIES:
        if low <= price < high:
            return key
    return "60"


def safe_url(value):
    if not value:
        return None
    parsed = urlparse(value)
    return value if parsed.scheme == "https" and parsed.netloc else None


def listing_keyboard(lot):
    rows = [[InlineKeyboardButton(text="🎁 Открыть лот", url=lot["lot_url"])]]
    seller_url = safe_url(lot.get("seller_url"))
    if seller_url:
        rows.append([InlineKeyboardButton(text="👤 Открыть продавца", url=seller_url)])
    rows.append([InlineKeyboardButton(
        text="📌 Занять",
        callback_data=f"reserve:{lot['source']}:{lot['source_id']}"[:64]
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def log_keyboard(lot):
    rows = []
    if safe_url(lot.get("lot_url")):
        rows.append([InlineKeyboardButton(text="🎁 Открыть лот", url=lot["lot_url"])])
    if safe_url(lot.get("seller_url")):
        rows.append([InlineKeyboardButton(text="👤 Открыть продавца", url=lot["seller_url"])])
    rows.append([InlineKeyboardButton(
        text="🔓 Освободить занятие",
        callback_data=f"release:{lot['source']}:{lot['source_id']}"[:64]
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def publish_lot(lot):
    # Do not silently treat GRAM, Stars, or rubles as TON.
    if lot.get("currency") != "TON":
        return
    price = Decimal(str(lot["price"]))
    key = category_for(price)
    for chat in await db.get_chats():
        thread_id = chat.get(f"topic_{key}")
        caption = (
            f"<b>{lot['title']}</b>\n"
            f"💰 Цена: <b>{price.normalize()} TON</b>\n"
            f"🏷 Источник: <b>{lot['source'].title()}</b>\n"
            f"🆔 Лот: <code>{lot['source_id']}</code>"
        )
        try:
            if lot.get("image_url"):
                sent = await bot.send_photo(
                    chat_id=chat["chat_id"], photo=lot["image_url"], caption=caption,
                    reply_markup=listing_keyboard(lot), message_thread_id=thread_id
                )
            else:
                sent = await bot.send_message(
                    chat_id=chat["chat_id"], text=caption,
                    reply_markup=listing_keyboard(lot), message_thread_id=thread_id
                )
            await db.save_lot(lot, chat["chat_id"], sent.message_id)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            log.warning("Cannot publish to chat %s: %s", chat["chat_id"], exc)


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "💎 <b>NFT Gift Radar</b>\n\n"
        "Я отслеживаю новые NFT-лоты и публикую их в подключённые группы.\n\n"
        "Добавь меня в супергруппу, включи темы и выдай права администратора "
        "на управление темами. Затем отправь в группе /setup."
    )


@dp.message(Command("setup"))
async def setup(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Команду /setup нужно отправить в супергруппе.")
        return
    me = await bot.get_me()
    member = await bot.get_chat_member(message.chat.id, me.id)
    if member.status != "administrator" or not getattr(member, "can_manage_topics", False):
        await message.answer("Сделай бота администратором и включи право «Управление темами».")
        return
    try:
        topics = {}
        for key, title, _low, _high in CATEGORIES:
            topic = await bot.create_forum_topic(message.chat.id, name=title)
            topics[key] = topic.message_thread_id
        await db.add_chat(message.chat.id, message.chat.title or str(message.chat.id), topics)
        await message.answer(
            "✅ <b>Группа подключена!</b>\n"
            "Создал 5 тем: до 5, 10, 20, 35 и 60+ TON."
        )
    except TelegramBadRequest as exc:
        await message.answer(f"Не удалось создать темы: <code>{exc}</code>\nПроверь, что включены темы форума.")


@dp.message(Command("status"))
async def status(message: Message):
    chats = await db.get_chats()
    await message.answer(f"📡 Подключено групп: <b>{len(chats)}</b>\nИнтервал проверки: {POLL_INTERVAL} сек.")


@dp.callback_query(F.data.startswith("reserve:"))
async def reserve(callback: CallbackQuery):
    _, source, source_id = callback.data.split(":", 2)
    user = callback.from_user
    lot = await db.reserve_lot(source, source_id, user.id, user.username)
    if not lot:
        await callback.answer("Лот уже занят или больше недоступен.", show_alert=True)
        return
    await callback.answer("Лот закреплён за тобой!")
    username = f"@{user.username}" if user.username else user.full_name
    seller_status = "не предоставлен источником" if not lot.get("seller_url") else lot["seller_url"]
    text = (
        "📋 <b>ЛОГ ЗАНЯТИЯ NFT</b>\n\n"
        f"🎁 <b>{lot['title']}</b>\n"
        f"💰 Цена: <b>{lot['price']} {lot['currency']}</b>\n"
        f"🏷 Источник: {source.title()}\n"
        f"👤 Занял: {username}\n"
        f"🆔 ID: <code>{source_id}</code>\n\n"
        "👤 <b>Данные продавца</b>\n"
        f"Ссылка: {seller_status}\n"
        "Рейтинг и последнее посещение: доступны только если их предоставляет площадка.\n\n"
        "🔒 Лот закреплён за тобой до ручного освобождения."
    )
    try:
        await bot.send_message(user.id, text, reply_markup=log_keyboard(lot))
    except TelegramForbiddenError:
        await db.release_lot(source, source_id)
        await callback.answer("Сначала открой бота и нажми /start, затем попробуй снова.", show_alert=True)
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🔒 Занял {username}", callback_data="reserved_info")]
        ]))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("release:"))
async def release(callback: CallbackQuery):
    _, source, source_id = callback.data.split(":", 2)
    lot = await db.get_lot(source, source_id)
    if not lot or lot.get("reserved_by") != callback.from_user.id:
        await callback.answer("Освободить занятие может только тот, кто занял лот.", show_alert=True)
        return
    await db.release_lot(source, source_id)
    await callback.answer("Занятие освобождено.")
    try:
        await callback.message.edit_text(callback.message.text + "\n\n🔓 <b>Занятие освобождено.</b>")
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "reserved_info")
async def reserved_info(callback: CallbackQuery):
    await callback.answer("Этот лот уже занят.", show_alert=True)


async def tracker_loop():
    while True:
        try:
            listings = await portals.fetch_listings()
            for lot in listings:
                if lot.get("currency") != "TON":
                    continue
                if await db.get_lot(lot["source"], lot["source_id"]):
                    continue
                await publish_lot(lot)
            log.info("Portals scan complete: %s listings", len(listings))
        except Exception:
            log.exception("Tracker scan failed")
        await asyncio.sleep(POLL_INTERVAL)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    await db.init_db()
    asyncio.create_task(tracker_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
