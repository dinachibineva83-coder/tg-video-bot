import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

# === Налаштування ===
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Відео, які надсилаються після /start або за посиланням
VIDEO_SETS = {
    "free": [
        "BAACAgIAAxkBAAMKaLwqrgsdVndDd_IJv-89xCL-zWgAAup4AAIKEuFJlD2robhaSKI2BA",
        "BAACAgIAAxkBAAMFaLwnYcxRR03m9z3G8F8WKgdFM00AAsyHAALzatlJw8SHG-Y_jQk2BA",
    ]
}

WELCOME_TEXT = (
    "Вітаю! 👋 Я Наталія Керницька, інструктор з курсів манікюру.\n"
    "Нижче надішлю тобі відеоматеріали з навчальної програми — переглянь їх, "
    "щоб отримати максимум користі."
)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def send_video_safely(chat_id: int, file_id: str):
    try:
        await bot.send_video(chat_id, file_id)
    except Exception as e:
        logging.error(f"Помилка відправки відео {file_id}: {e}")


@dp.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer(WELCOME_TEXT)
    for file_id in VIDEO_SETS["free"]:
        await send_video_safely(message.chat.id, file_id)


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer("Надішли /start щоб отримати відео.")


@dp.message(Command("getfileid"))
async def get_file_id(message: Message):
    if message.reply_to_message and message.reply_to_message.video:
        file_id = message.reply_to_message.video.file_id
        await message.answer(file_id)
    else:
        await message.answer("Будь ласка, використай цю команду у відповідь на повідомлення з відео.")


@dp.message(F.video)
async def handle_video(message: Message):
    file_id = message.video.file_id
    await message.reply(f"file_id цього відео:\n{file_id}")


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
