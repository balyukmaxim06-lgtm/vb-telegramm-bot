import asyncio
import logging
import re
import os
import threading
import html
import time

from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# ============================================================
# FLASK APP FOR RENDER
# ============================================================

web_app = Flask(__name__)


@web_app.route("/")
@web_app.route("/health")
def health():
    return "Bot is running!", 200


# ============================================================
# TELEGRAM BOT
# ============================================================

TOKEN = "8818834067:AAGDaCZboIo2g-t8qTxlcpkJjjsYEf7DanQ"

bot = Bot(token=TOKEN)
dp = Dispatcher()


# ============================================================
# ПОЛУЧЕНИЕ ДАННЫХ ЧЕРЕЗ SELENIUM
# ============================================================

def get_product_data(nm_id):
    """Получает данные товара через Selenium с отладкой"""
    
    options = Options()
    # Убираем headless для обхода блокировки
    # options.add_argument("--headless=new")
    
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--lang=ru")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
    except Exception as e:
        print(f"Ошибка драйвера: {e}")
        return None

    try:
        # Скрываем признаки автоматизации
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            '''
        })
        
        url = f"https://www.wildberries.by/catalog/{nm_id}/detail.aspx"
        print(f"ЗАГРУЖАЕМ: {url}")
        driver.get(url)
        
        print("ОЖИДАЕМ ЗАГРУЗКИ (10 секунд)...")
        time.sleep(10)
        
        # === СОХРАНЯЕМ HTML ДЛЯ ОТЛАДКИ ===
        html_content = driver.page_source
        filename = f"debug_{nm_id}.html"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        print(f"✅ HTML СОХРАНЁН: {filename}")
        print(f"📄 РАЗМЕР HTML: {len(html_content)} символов")
        
        # Проверяем, есть ли признаки блокировки
        if "подозрительная активность" in html_content.lower():
            print("🚫 ОБНАРУЖЕНА КАПЧА!")
            return None
        
        if "пожалуйста, подождите" in html_content.lower():
            print("🚫 ОБНАРУЖЕНА СТРАНИЦА С ОЖИДАНИЕМ!")
            return None
        
        # Проверяем, есть ли название товара
        if "название" not in html_content.lower() and "товар" not in html_content.lower():
            print("⚠️ НА СТРАНИЦЕ НЕТ ДАННЫХ О ТОВАРЕ")
            # Показываем первые 500 символов HTML
            print(f"📄 ПЕРВЫЕ 500 СИМВОЛОВ HTML:\n{html_content[:500]}")
            return None

        # Прокручиваем страницу
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(3)

        # ====================================================
        # ПАРСИНГ ДАННЫХ
        # ====================================================

        # Название
        name = "Название не найдено"
        try:
            name_element = driver.find_element(By.CSS_SELECTOR, "h1")
            name = name_element.text.strip()
            print(f"✅ НАЗВАНИЕ: {name}")
        except Exception as e:
            print(f"❌ Ошибка поиска названия: {e}")

        # Цена
        price = 0
        try:
            price_elements = driver.find_elements(By.CSS_SELECTOR, "span[class*='price']")
            for el in price_elements:
                text = el.text.strip()
                if text and any(c.isdigit() for c in text):
                    cleaned = re.sub(r'[^\d.,]', '', text)
                    cleaned = cleaned.replace(',', '.')
                    try:
                        price = float(cleaned)
                        if price > 0:
                            print(f"✅ ЦЕНА: {price}")
                            break
                    except:
                        continue
        except Exception as e:
            print(f"❌ Ошибка поиска цены: {e}")

        # Рейтинг
        rating = 0
        try:
            rating_elements = driver.find_elements(By.CSS_SELECTOR, "span[class*='rating']")
            if rating_elements:
                text = rating_elements[0].text.strip()
                if text:
                    rating = float(text.replace(',', '.'))
                    print(f"✅ РЕЙТИНГ: {rating}")
        except Exception as e:
            print(f"❌ Ошибка поиска рейтинга: {e}")

        # Отзывы
        reviews = 0
        try:
            reviews_elements = driver.find_elements(By.CSS_SELECTOR, "span[class*='feedbacks'], span[class*='count-feedback']")
            if reviews_elements:
                text = reviews_elements[0].text.strip()
                if text:
                    reviews_text = re.sub(r'\D', '', text)
                    if reviews_text:
                        reviews = int(reviews_text)
                        print(f"✅ ОТЗЫВОВ: {reviews}")
        except Exception as e:
            print(f"❌ Ошибка поиска отзывов: {e}")

        # Бренд
        brand = "Не указан"
        try:
            brand_elements = driver.find_elements(By.CSS_SELECTOR, "span[class*='brand']")
            if brand_elements:
                brand = brand_elements[0].text.strip()
                print(f"✅ БРЕНД: {brand}")
        except Exception as e:
            print(f"❌ Ошибка поиска бренда: {e}")

        # Описание
        description = "Описание отсутствует"
        try:
            desc_elements = driver.find_elements(By.CSS_SELECTOR, "div[class*='description'], div[class*='about']")
            for el in desc_elements:
                text = el.text.strip()
                if text and len(text) > 20:
                    description = text
                    print(f"✅ ОПИСАНИЕ: {description[:100]}...")
                    break
        except Exception as e:
            print(f"❌ Ошибка поиска описания: {e}")

        # Категория
        category = "Не указана"
        try:
            category_elements = driver.find_elements(By.CSS_SELECTOR, "ol[class*='breadcrumb'] li")
            if category_elements:
                category = category_elements[-1].text.strip()
                print(f"✅ КАТЕГОРИЯ: {category}")
        except Exception as e:
            print(f"❌ Ошибка поиска категории: {e}")

        # Артикул продавца
        vendor_code = "Не указан"
        try:
            vendor_elements = driver.find_elements(By.CSS_SELECTOR, "span[class*='vendor']")
            if vendor_elements:
                vendor_code = vendor_elements[0].text.strip()
                print(f"✅ АРТИКУЛ ПРОДАВЦА: {vendor_code}")
        except Exception as e:
            print(f"❌ Ошибка поиска артикула: {e}")

        print("=" * 60)
        print("РЕЗУЛЬТАТ ПАРСИНГА:")
        print(f"Название: {name}")
        print(f"Цена: {price}")
        print(f"Рейтинг: {rating}")
        print(f"Отзывы: {reviews}")
        print(f"Бренд: {brand}")
        print("=" * 60)

        return {
            "name": name,
            "price": price,
            "rating": rating,
            "reviews": reviews,
            "brand": brand,
            "category": category,
            "sale_percent": 0,
            "vendor_code": vendor_code,
            "stock": "Нет данных",
            "description": description,
            "url": url
        }

    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        return None
    finally:
        driver.quit()


# ============================================================
# ФОРМИРОВАНИЕ ОТВЕТА
# ============================================================

def make_answer(product_data):
    name = html.escape(str(product_data.get("name", "Название не указано")))
    answer_text = f"📦 <b>{name}</b>\n\n"

    brand = product_data.get("brand")
    if brand and brand != "Не указан":
        answer_text += f"🏷️ <b>Бренд:</b> {html.escape(str(brand))}\n"

    category = product_data.get("category")
    if category and category != "Не указана":
        answer_text += f"📂 <b>Категория:</b> {html.escape(str(category))}\n"

    price = product_data.get("price", 0)
    if price > 0:
        answer_text += f"💰 <b>Цена:</b> {price:.2f} руб.\n"
    else:
        answer_text += "💰 <b>Цена:</b> нет данных\n"

    rating = product_data.get("rating", 0)
    reviews = product_data.get("reviews", 0)
    answer_text += f"⭐ <b>Рейтинг:</b> {rating}\n"
    answer_text += f"📝 <b>Отзывов:</b> {reviews}\n"

    description = product_data.get("description")
    if description and description != "Описание отсутствует":
        description = str(description)
        if len(description) > 500:
            description = description[:500] + "..."
        description = html.escape(description)
        answer_text += f"\n📄 <b>Описание:</b>\n{description}\n"

    product_url = product_data.get("url")
    if product_url:
        answer_text += f"\n🔗 <a href='{product_url}'>Открыть на Wildberries</a>"

    return answer_text


# ============================================================
# КОМАНДЫ
# ============================================================

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для анализа товаров на Wildberries.by.\n\n"
        "📌 Отправь мне артикул товара:\n\n"
        "Например: 2147724"
    )


@dp.message(Command("check"))
async def check_product(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Укажи артикул. Пример: /check 2147724")
        return

    nm_id = args[1]
    await message.answer(f"🔎 Ищу товар {nm_id}...\n⏳ Подожди 20-30 секунд.")

    try:
        loop = asyncio.get_running_loop()
        product_data = await loop.run_in_executor(None, get_product_data, nm_id)

        if not product_data:
            await message.answer(f"❌ Товар не найден.\n\nАртикул: {nm_id}")
            return

        answer_text = make_answer(product_data)
        await message.answer(answer_text, parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        logging.exception("Ошибка команды /check")
        await message.answer(f"❌ Ошибка: {str(e)}")


@dp.message()
async def auto_check(message: types.Message):
    if not message.text:
        return

    text = message.text.strip()
    match = re.search(r"\b(\d{4,15})\b", text)

    if not match:
        return

    nm_id = match.group(1)

    await message.answer(f"🔎 Артикул: {nm_id}\n⏳ Ищу товар... (20-30 секунд)")

    try:
        loop = asyncio.get_running_loop()
        product_data = await loop.run_in_executor(None, get_product_data, nm_id)

        if not product_data:
            await message.answer(f"❌ Товар не найден.\n\nАртикул: {nm_id}")
            return

        answer_text = make_answer(product_data)
        await message.answer(answer_text, parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        logging.exception("Ошибка автоматического поиска")
        await message.answer(f"❌ Ошибка: {str(e)}")


# ============================================================
# MAIN
# ============================================================

async def main():
    print("=" * 60)
    print("BOT STARTING")
    print("=" * 60)
    print("Отправь в Telegram: /check 2147724")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    def run_flask():
        port = int(os.environ.get("PORT", 8080))
        print(f"Flask запускается на порту {port}")
        web_app.run(host="0.0.0.0", port=port)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    asyncio.run(main())
