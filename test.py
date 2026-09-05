import asyncio
import logging
import json
import time
import re
import os
import threading

from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import cloudscraper


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO)


# ============================================================
# FLASK APP (для Render)
# ============================================================

web_app = Flask(__name__)

@web_app.route('/')
@web_app.route('/health')
def health():
    return "✅ Bot is running!", 200


# ============================================================
# TELEGRAM BOT
# ============================================================

# ⚠️ ВСТАВЬ СВОЙ НОВЫЙ ТОКЕН (СБРОШЕННЫЙ ЧЕРЕЗ @BotFather)
TOKEN = "8818834067:AAGZFrrlXShenGh4Pb8NllTLePxjbh9RRdw"

bot = Bot(token=TOKEN)
dp = Dispatcher()


# ============================================================
# ПОЛУЧЕНИЕ ДАННЫХ ТОВАРА (через cloudscraper)
# ============================================================

def get_product_data(nm_id):
    """Получает данные через cloudscraper (обходит блокировку Wildberries)"""
    
    scraper = cloudscraper.create_scraper()
    
    # Пробуем разные API
    urls = [
        f"https://card.wb.ru/cards/detail?nm={nm_id}",
        f"https://catalog.wb.ru/catalog/detail/v4?nm={nm_id}",
        f"https://wbx-content-v2.wbstatic.net/ru/{nm_id}.json"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.wildberries.by/"
    }
    
    for url in urls:
        try:
            print(f"Пробую API: {url}")
            response = scraper.get(url, headers=headers, timeout=30)
            print(f"Статус: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # === Для card.wb.ru ===
                if "data" in data and "products" in data["data"]:
                    products = data["data"]["products"]
                    if products:
                        p = products[0]
                        return {
                            'name': p.get('name', 'Название не указано'),
                            'price': p.get('priceU', 0) / 100,
                            'rating': p.get('rating', 0),
                            'reviews': p.get('feedbacks', 0),
                            'brand': p.get('brand', 'Не указан'),
                            'category': 'Не указана',
                            'sale_percent': 0,
                            'vendor_code': 'Не указан',
                            'stock': 'Нет данных',
                            'description': 'Описание отсутствует',
                            'url': f"https://www.wildberries.by/catalog/{nm_id}/detail.aspx"
                        }
                
                # === Для wbstatic.net ===
                if "im_name" in data:
                    return {
                        'name': data.get('im_name', 'Название не указано'),
                        'price': data.get('sale_price_u', 0) / 100,
                        'rating': data.get('rating', 0),
                        'reviews': data.get('feedbacks', 0),
                        'brand': 'Не указан',
                        'category': 'Не указана',
                        'sale_percent': 0,
                        'vendor_code': 'Не указан',
                        'stock': 'Нет данных',
                        'description': 'Описание отсутствует',
                        'url': f"https://www.wildberries.by/catalog/{nm_id}/detail.aspx"
                    }
                    
        except Exception as e:
            print(f"Ошибка при запросе к {url}: {e}")
            continue
    
    return None


# ============================================================
# /START
# ============================================================

@dp.message(Command("start"))
async def start_command(message: types.Message):

    await message.answer(
        "👋 Привет! Я бот для расширенного анализа "
        "товаров на Wildberries.by.\n\n"
        "📌 Просто отправь мне артикул товара — "
        "и я покажу всю информацию!\n\n"
        "📊 Я покажу:\n"
        "• Название, бренд, категорию\n"
        "• Цену и скидку\n"
        "• Рейтинг и количество отзывов\n"
        "• Артикул продавца\n"
        "• Наличие на складах\n"
        "• Описание товара\n\n"
        "Пример: 2147724\n"
        "Или: /check 12345678"
    )


# ============================================================
# /CHECK
# ============================================================

@dp.message(Command("check"))
async def check_product(message: types.Message):

    args = message.text.split()

    if len(args) < 2:

        await message.answer(
            "❌ Укажи артикул.\n\n"
            "Пример:\n"
            "/check 12345678"
        )

        return

    nm_id = args[1]

    await message.answer(
        "🔎 Ищу товар...\n"
        "⏳ Это займёт примерно 5-10 секунд."
    )

    try:

        loop = asyncio.get_event_loop()

        product_data = await loop.run_in_executor(
            None,
            get_product_data,
            nm_id
        )

        if not product_data:

            await message.answer(
                "❌ Товар не найден.\n"
                "Проверь артикул."
            )

            return

        if (
            product_data["price"] == 0
            and
            product_data["name"] == "Название не указано"
        ):

            await message.answer(
                "❌ Не удалось найти данные "
                "на странице.\n\n"
                "Попробуй позже."
            )

            return

        answer_text = f"📦 <b>{product_data['name']}</b>\n\n"

        if product_data.get('brand') and product_data['brand'] != "Не указан":
            answer_text += f"🏷️ <b>Бренд:</b> {product_data['brand']}\n"

        if product_data.get('category') and product_data['category'] != "Не указана":
            answer_text += f"📂 <b>Категория:</b> {product_data['category']}\n"

        answer_text += f"💰 <b>Цена:</b> {product_data['price']:.2f} руб.\n"

        if product_data.get('sale_percent', 0) > 0:
            answer_text += f"🔥 <b>Скидка:</b> {product_data['sale_percent']}%\n"

        if product_data.get('vendor_code') and product_data['vendor_code'] != "Не указан":
            answer_text += f"🔢 <b>Артикул продавца:</b> {product_data['vendor_code']}\n"

        answer_text += f"⭐ <b>Рейтинг:</b> {product_data['rating']}\n"
        answer_text += f"📝 <b>Отзывов:</b> {product_data['reviews']}\n"

        if product_data.get('stock') and product_data['stock'] != "Нет данных":
            answer_text += f"📦 <b>Наличие:</b> {product_data['stock']}\n"

        if product_data.get('description') and product_data['description'] != "Описание отсутствует":
            desc = product_data['description']
            if len(desc) > 200:
                desc = desc[:200] + "..."
            answer_text += f"\n📄 <b>Описание:</b>\n{desc}\n"

        answer_text += f"\n🔗 <a href='{product_data['url']}'>Открыть на Wildberries</a>"

        await message.answer(
            answer_text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    except Exception as e:

        print(f"Ошибка команды /check: {e}")

        await message.answer(
            f"❌ Ошибка: {str(e)}"
        )


# ============================================================
# АВТОМАТИЧЕСКОЕ РАСПОЗНАВАНИЕ АРТИКУЛА
# ============================================================

@dp.message()
async def auto_check(message: types.Message):

    text = message.text.strip()

    match = re.search(r'\b(\d{4,15})\b', text)

    if not match:
        return

    nm_id = match.group(1)

    await message.answer(
        f"🔎 Автоматически распознал артикул: {nm_id}\n"
        "⏳ Ищу товар... (это займёт 5-10 секунд)"
    )

    try:
        loop = asyncio.get_event_loop()
        product_data = await loop.run_in_executor(
            None,
            get_product_data,
            nm_id
        )

        if not product_data:
            await message.answer(
                "❌ Товар не найден.\n"
                "Проверь артикул."
            )
            return

        if product_data["price"] == 0 and product_data["name"] == "Название не указано":
            await message.answer(
                "❌ Не удалось найти данные на странице.\n"
                "Попробуй позже."
            )
            return

        answer_text = f"📦 <b>{product_data['name']}</b>\n\n"

        if product_data.get('brand') and product_data['brand'] != "Не указан":
            answer_text += f"🏷️ <b>Бренд:</b> {product_data['brand']}\n"

        if product_data.get('category') and product_data['category'] != "Не указана":
            answer_text += f"📂 <b>Категория:</b> {product_data['category']}\n"

        answer_text += f"💰 <b>Цена:</b> {product_data['price']:.2f} руб.\n"

        if product_data.get('sale_percent', 0) > 0:
            answer_text += f"🔥 <b>Скидка:</b> {product_data['sale_percent']}%\n"

        if product_data.get('vendor_code') and product_data['vendor_code'] != "Не указан":
            answer_text += f"🔢 <b>Артикул продавца:</b> {product_data['vendor_code']}\n"

        answer_text += f"⭐ <b>Рейтинг:</b> {product_data['rating']}\n"
        answer_text += f"📝 <b>Отзывов:</b> {product_data['reviews']}\n"

        if product_data.get('stock') and product_data['stock'] != "Нет данных":
            answer_text += f"📦 <b>Наличие:</b> {product_data['stock']}\n"

        if product_data.get('description') and product_data['description'] != "Описание отсутствует":
            desc = product_data['description']
            if len(desc) > 200:
                desc = desc[:200] + "..."
            answer_text += f"\n📄 <b>Описание:</b>\n{desc}\n"

        answer_text += f"\n🔗 <a href='{product_data['url']}'>Открыть на Wildberries</a>"

        await message.answer(
            answer_text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


# ============================================================
# MAIN
# ============================================================

async def main():
    print("🚀 Бот запускается...")
    print("📌 Отправь артикул (число) или /check 12345678")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке для Render
    def run_flask():
        port = int(os.environ.get("PORT", 8080))
        web_app.run(host="0.0.0.0", port=port)
    
    thread = threading.Thread(target=run_flask)
    thread.start()
    
    # Запускаем бота
    asyncio.run(main())
