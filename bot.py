import asyncio
import logging
import os
import re
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile

# === Налаштування ===
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ВСТАВ СВОЇ file_id СЮДИ (між лапками). Можна кілька через кому.
VIDEO_SETS = {
    "free": [
        "ВСТАВ_ТУТ_FILE_ID_1",
        # "BAACAgIAAxkBAAMFaLwnYcxRR03m9z3G8F8WKgdFM00AAsyHAALzatlJw8SHG-Y_jQk2BA",
    ],
    "course1": [
        # "BAACAgIAAxkBAAMKaLwqrgsdVndDd_IJv-89xCL-zWgAAup4AAIKEuFJlD2robhaSKI2BA",
    ]
}

WELCOME_TEXT = (
    "Привіт! 👋 Я надішлю тобі відеоматеріали автоматично.\n"
    "Якщо нічого не прийшло — натисни /help."
)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def send_video_safely(chat_id: int, ref: str):
    """Відправляє відео з file_id, URL або локального файлу."""
    try:
        is_probable_file_id = bool(re.match(r"^[A-Za-z0-9\-_]{20,}$", ref))
        is_url = ref.startswith("http://") or ref.startswith("https://")
        if is_probable_file_id and not is_url:
            await bot.send_video(chat_id, video=ref)
        elif is_url:
            await bot.send_video(chat_id, video=ref)
        else:
            await bot.send_video(chat_id, video=FSInputFile(ref))
    except Exception as e:
        await bot.send_message(chat_id, f"Не вдалося надіслати відео: {e}")

async def send_set(chat_id: int, key: str):
    videos = VIDEO_SETS.get(key)
    if not videos:
        await bot.send_message(chat_id, "Набір відео не знайдено. Спробуй /help.")
        return
    await bot.send_message(chat_id, f"Надсилаю набір відео: *{key}*", parse_mode="Markdown")
    for ref in videos:
        await send_video_safely(chat_id, ref)

@dp.message(CommandStart(deep_link=True))
async def start_deeplink(message: Message):
    parts = message.text.split(maxsplit=1)
    key = parts[1].strip() if len(parts) > 1 else ""
    await message.answer(WELCOME_TEXT)
    await send_set(message.chat.id, key or "free")

@dp.message(CommandStart())
async def start_plain(message: Message):
    await message.answer(WELCOME_TEXT)
    await send_set(message.chat.id, "free")

@dp.message(Command("help"))
async def help_cmd(message: Message):
    keys = ", ".join(VIDEO_SETS.keys())
    txt = (
        "Щоб отримати набір відео, заходь за лінком:\n"
        "`https://t.me/<ТвійЮзернеймБота>?start=<ключ>`\n\n"
        f"Доступні ключі: `{keys}`"
    )
    await message.answer(txt, parse_mode="Markdown")

# /getfileid працює і як reply на відео, і якщо відео надіслали разом з командою
@dp.message(Command("getfileid"))
async def get_file_id(message: Message):
    if message.reply_to_message and message.reply_to_message.video:
        fid = message.reply_to_message.video.file_id
        await message.answer(f"`{fid}`", parse_mode="Markdown")
        return
    if message.video:
        fid = message.video.file_id
        await message.answer(f"`{fid}`", parse_mode="Markdown")
        return
    await message.answer("Надішли відео або зроби /getfileid у відповідь на відео 🙂")

# Автовідповідь: будь-яке відео → повертаємо file_id
@dp.message(F.video)
async def auto_file_id(message: Message):
    await message.answer(f"`{message.video.file_id}`", parse_mode="Markdown")

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не задано BOT_TOKEN. Додай його в налаштуваннях Render.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
