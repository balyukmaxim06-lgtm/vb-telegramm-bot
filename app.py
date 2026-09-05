import asyncio
import os
from flask import Flask
from aiogram import Bot, Dispatcher
# ... (все остальные твои импорты)

# Создаём Flask-приложение для health-check'ов Render
app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health_check():
    return "Bot is running!", 200

# --- Твой код бота (всё, что было до `async def main()`) ---
# ...

# --- Запуск бота ---
async def start_bot():
    print("🚀 Бот запускается...")
    # Убедись, что бот не мешает веб-серверу
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

# Запускаем всё вместе
if __name__ == '__main__':
    # Запускаем бота в фоновом режиме
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(start_bot())

    # Запускаем Flask-сервер, который будет слушать порт, назначенный Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)