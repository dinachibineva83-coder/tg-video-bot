import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

# ========== НАЛАШТУВАННЯ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Публічний URL сервісу на Render:
# спочатку спробуємо RENDER_EXTERNAL_URL; якщо його немає — використовуй PUBLIC_URL
PUBLIC_URL = (os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL") or "").rstrip("/")

# Твій вітальний текст
WELCOME_TEXT = (
    "Вітаю! 👋 Я Наталія Керницька, інструктор з курсів манікюру.\n"
    "Нижче надішлю тобі відеоматеріали з навчальної програми — переглянь їх, "
    "щоб отримати максимум користі."
)

# -------- Налаштовувана серія на 3 дні --------
# День 1 — одразу після Start, День 2 — через 1 день, День 3 — через 2 дні
SERIES_KEY_DEFAULT = "free"
SERIES = {
    "free": [
        # День 1
        "BAACAgIAAxkBAAMKaLwqrgsdVndDd_IJv-89xCL-zWgAAup4AAIKEuFJlD2robhaSKI2BA",
        # День 2
        "BAACAgIAAxkBAAMFaLwnYcxRR03m9z3G8F8WKgdFM00AAsyHAALzatlJw8SHG-Y_jQk2BA",
        # День 3 — якщо захочеш, додай ще один file_id сюди:
        # BAACAgIAAxkBAAMhaL1yyP2oXCK6d81EYCmeNI_vP9MAAiKCAAIKEvFJL_Sa9_O1i4I2BA",
    ]
}
SEND_HOUR_KYIV = 10  # о котрій годині відправляти заплановані відео (за Києвом)

# ========== ІНІЦІАЛІЗАЦІЯ ==========
logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# База для дріп-серії (дуже проста):
# зберігаємо, що і коли наступним надсилати користувачу
DB = "drip.sqlite3"

def db_init():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS drip (
        user_id INTEGER NOT NULL,
        series_key TEXT NOT NULL,
        next_index INTEGER NOT NULL,
        run_at_utc TEXT NOT NULL,
        PRIMARY KEY (user_id, series_key)
    )
    """)
    conn.commit()
    conn.close()

def db_upsert(user_id: int, series_key: str, next_index: int, run_at_utc: datetime):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
    INSERT INTO drip(user_id, series_key, next_index, run_at_utc)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(user_id, series_key) DO UPDATE SET
        next_index=excluded.next_index,
        run_at_utc=excluded.run_at_utc
    """, (user_id, series_key, next_index, run_at_utc.isoformat()))
    conn.commit()
    conn.close()

def db_delete(user_id: int, series_key: str):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM drip WHERE user_id=? AND series_key=?", (user_id, series_key))
    conn.commit()
    conn.close()

def db_due(now_utc: datetime):
    """Усі записи, в яких час настав."""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    rows = c.execute("SELECT user_id, series_key, next_index, run_at_utc FROM drip").fetchall()
    conn.close()
    due = []
    for user_id, series_key, next_index, run_at_iso in rows:
        try:
            run_at = datetime.fromisoformat(run_at_iso)
        except Exception:
            run_at = now_utc
        if run_at <= now_utc:
            due.append((user_id, series_key, next_index))
    return due

# ========== ДОПОМІЖНЕ ==========
def kyiv_midnight_plus(hour: int, days_ahead: int = 1) -> datetime:
    """Повертає datetime (UTC) на завтра/післязавтра о фіксованій годині Києва."""
    # Київ зараз UTC+3 (Europe/Kyiv у вересні 2025 → UTC+3).
    # Для простоти візьмемо фіксований зсув +3. Якщо буде інший сезон — можна винести в змінну.
    KYIV_OFFSET = 3
    now_utc = datetime.now(timezone.utc)
    # цільова дата у Києві
    kyiv_now = now_utc + timedelta(hours=KYIV_OFFSET)
    kyiv_target = (kyiv_now.replace(hour=hour, minute=0, second=0, microsecond=0)
                   + timedelta(days=days_ahead))
    # назад в UTC
    return kyiv_target - timedelta(hours=KYIV_OFFSET)

async def send_video(user_id: int, file_id: str):
    try:
        await bot.send_video(user_id, file_id)
    except Exception as e:
        logging.error(f"Помилка відправки відео {file_id} → user {user_id}: {e}")

async def schedule_next(user_id: int, series_key: str, next_index: int, days_ahead: int):
    """Запланувати наступне відео через N днів, на SEND_HOUR_KYIV за Києвом."""
    run_at_utc = kyiv_midnight_plus(SEND_HOUR_KYIV, days_ahead=days_ahead)
    db_upsert(user_id, series_key, next_index, run_at_utc)

async def run_due_jobs():
    """Викликається кроном або вручну: надсилає все, що «протермінувалось»."""
    now = datetime.now(timezone.utc)
    for user_id, series_key, idx in db_due(now):
        videos = SERIES.get(series_key, [])
        if 0 <= idx < len(videos):
            # шлемо чергове відео
            await send_video(user_id, videos[idx])
            # плануємо наступне, якщо є
            if idx + 1 < len(videos):
                # наступний день після цього (тобто +1 день)
                await schedule_next(user_id, series_key, idx + 1, days_ahead=1)
            else:
                # серія завершена
                db_delete(user_id, series_key)
        else:
            # некоректний індекс — приберемо запис
            db_delete(user_id, series_key)

# ========== ХЕНДЛЕРИ БОТА ==========
@dp.message(CommandStart(deep_link=True))
async def start_with_key(message: Message):
    parts = message.text.split(maxsplit=1)
    key = parts[1].strip() if len(parts) > 1 else SERIES_KEY_DEFAULT
    series_key = key if key in SERIES else SERIES_KEY_DEFAULT

    await message.answer(WELCOME_TEXT)
    # День 1 — одразу
    await send_video(message.chat.id, SERIES[series_key][0])

    # День 2 о 10:00 за Києвом
    if len(SERIES[series_key]) > 1:
        await schedule_next(message.chat.id, series_key, next_index=1, days_ahead=1)
    # День 3 о 10:00 за Києвом
    if len(SERIES[series_key]) > 2:
        # Запишемо одразу "через 2 дні" як next_index=2,
        # але зверни увагу: ми завжди відправляємо "due" по порядку,
        # тому день 2 піде першим, потім перезапланується день 3 — це теж ок.
        pass  # не обов'язково додавати тут — алгоритм сам поставить після дня 2

@dp.message(CommandStart())
async def start_plain(message: Message):
    series_key = SERIES_KEY_DEFAULT
    await message.answer(WELCOME_TEXT)
    await send_video(message.chat.id, SERIES[series_key][0])
    if len(SERIES[series_key]) > 1:
        await schedule_next(message.chat.id, series_key, next_index=1, days_ahead=1)

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer("Натисни /start — надійде вітання та перше відео. Наступні частини прийдуть наступними днями о 10:00 за Києвом 🙂")

# Зручно: якщо надсилаєш боту відео — він повертає file_id (щоб наповнювати серію)
@dp.message(F.video)
async def give_file_id(message: Message):
    await message.answer(f"`{message.video.file_id}`", parse_mode="Markdown")

# ========== WEBHOOK-СЕРВЕР ==========
async def on_startup(app: web.Application):
    if not PUBLIC_URL:
        raise RuntimeError("Не задано PUBLIC_URL або RENDER_EXTERNAL_URL (Environment Variable).")
    webhook_url = PUBLIC_URL + "/webhook"
    await bot.set_webhook(webhook_url)
    logging.info(f"Webhook set to: {webhook_url}")

async def on_shutdown(app: web.Application):
    await bot.delete_webhook(drop_pending_updates=True)

async def handle_webhook(request: web.Request):
    # Telegram шле оновлення сюди (POST /webhook)
    data = await request.text()
    await dp.feed_webhook_update(bot, data)
    return web.Response()

async def handle_cron(request: web.Request):
    # Ендпоінт для «будильника» (щоб гарантовано надсилати, навіть якщо сервіс засинає)
    # Виклич цей URL раз на день ~10:00 за Києвом (через будь-який безкоштовний крон-сервіс).
    await run_due_jobs()
    return web.Response(text="ok")

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задано (Environment Variable)")
    db_init()

    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    app.router.add_post("/webhook", handle_webhook)
    # Додатковий маршрут /cron — на випадок сну сервісу
    app.router.add_get("/cron", handle_cron)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logging.info(f"Server started on port {port}")

    # тримаємо процес живим
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
