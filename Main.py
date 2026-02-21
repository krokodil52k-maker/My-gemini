import sqlite3
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
import google.generativeai as genai

# --- НАСТРОЙКИ ---
TG_TOKEN = "8214800081:AAF3Tc43aPol691BaS-6WP1ZBoejkMmL0vo"
GEMINI_KEY = "AIzaSyC-cP7xFc08GIjAKYqMjplG0YOMHQR2C_g"

# Настройка логирования (чтобы видеть ошибки в консоли)
logging.basicConfig(level=logging.INFO)

# Инициализация ИИ
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

# Инициализация бота
bot = Bot(token=TG_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (user_id INTEGER PRIMARY KEY, requests_left INTEGER)''')
    conn.commit()
    conn.close()

def get_limit(user_id):
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute("SELECT requests_left FROM users WHERE user_id = ?", (user_id,))
    res = cur.fetchone()
    conn.close()
    return res[0] if res else None

def update_limit(user_id, count, is_add=False):
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    current = get_limit(user_id)
    if current is None:
        cur.execute("INSERT INTO users VALUES (?, ?)", (user_id, 30))
    else:
        new_val = (current + count) if is_add else count
        cur.execute("UPDATE users SET requests_left = ? WHERE user_id = ?", (new_val, user_id))
    conn.commit()
    conn.close()

# --- ОБРАБОТКА КОМАНД ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    if get_limit(uid) is None:
        update_limit(uid, 30) # 30 бесплатных запросов новому юзеру
    
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n"
        f"Я бот на базе Gemini 2.0.\n\n"
        f"💰 Твой баланс: {get_limit(uid)} запросов.\n"
        f"Чтобы пополнить баланс, нажми /buy"
    )

@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    await message.answer_invoice(
        title="+30 запросов Gemini",
        description="Пополнение баланса (начисляется мгновенно)",
        payload="extra_30",
        currency="XTR", # Валюта - Звезды Telegram
        prices=[types.LabeledPrice(label="Покупка 30 запросов", amount=29)] # Цена в звездах
    )

# --- ПЛАТЕЖИ (STARS) ---

@dp.pre_checkout_query()
async def process_pre_checkout(query: types.PreCheckoutQuery):
    # Подтверждаем, что готовы принять оплату
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def on_success_pay(message: types.Message):
    uid = message.from_user.id
    update_limit(uid, 30, is_add=True)
    await message.answer("✅ Оплата прошла успешно! Тебе начислено 30 запросов.")

# --- ГЛАВНЫЙ ЧАТ ---

@dp.message()
async def handle_message(message: types.Message):
    # Игнорируем команды, которые не обработались выше
    if message.text and message.text.startswith('/'):
        return

    uid = message.from_user.id
    limit = get_limit(uid)

    # Если юзера нет в базе (написал сразу без /start)
    if limit is None:
        update_limit(uid, 30)
        limit = 30

    if limit <= 0:
        await message.answer("❌ Запросы закончились. Купи пакет запросов через /buy (29 ⭐️)")
        return

    try:
        # Эффект "печатает..."
        await bot.send_chat_action(message.chat.id, "typing")
        
        # Запрос к Gemini
        response = model.generate_content(message.text)
        
        # Списываем 1 запрос
        new_limit = limit - 1
        update_limit(uid, new_limit)
        
        await message.answer(f"{response.text}\n\n—\n🔋 Осталось запросов: {new_limit}")
    
    except Exception as e:
        logging.error(f"Ошибка ИИ: {e}")
        await message.answer("⚠️ Произошла ошибка. Скорее всего, запрос слишком сложный или сработал фильтр безопасности.")

# --- ЗАПУСК ---
async def main():
    init_db()
    print("Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")
