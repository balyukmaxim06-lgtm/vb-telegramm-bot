import asyncio
import logging
import re
import os
import threading
import html
import time

import requests
from flask import Flask

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command


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
# HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.wildberries.by/",
    "Origin": "https://www.wildberries.by",
    "Connection": "keep-alive",
}


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def normalize_article(value):
    """Оставляет только цифры в артикуле."""
    value = str(value).strip()
    value = re.sub(r"\D", "", value)
    return value


def find_value(obj, keys):
    """
    Ищет значение по указанным ключам.
    """
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj[key] is not None:
                value = obj[key]
                if value != "":
                    return value
        for value in obj.values():
            result = find_value(value, keys)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = find_value(item, keys)
            if result is not None:
                return result
    return None


def convert_price(value):
    """Преобразует цену WB в рубли."""
    if value is None:
        return 0.0
    try:
        value = float(value)
        if value <= 0:
            return 0.0
        return value / 100
    except (ValueError, TypeError):
        return 0.0


def get_price(product):
    """Получает цену товара."""
    sale_price = find_value(product, ["salePriceU", "clientPriceU", "sale_price_u"])
    price = find_value(product, ["priceU", "basicPriceU", "price_u"])

    converted_sale_price = convert_price(sale_price)
    if converted_sale_price > 0:
        return converted_sale_price

    converted_price = convert_price(price)
    if converted_price > 0:
        return converted_price

    return 0.0


def get_rating(product):
    """Получает рейтинг товара."""
    value = find_value(product, ["rating", "reviewRating"])
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def get_reviews(product):
    """Получает количество отзывов."""
    value = find_value(product, ["feedbacks", "feedbacksCount", "feedbackCount", "reviews", "reviewCount"])
    if value is None:
        return 0
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def get_text_value(product, keys, default=""):
    """Получает текстовое значение."""
    value = find_value(product, keys)
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return default
    return str(value).strip()


# ============================================================
# СОЗДАНИЕ ЕДИНОГО ОБЪЕКТА ТОВАРА
# ============================================================

def build_product(product, nm_id):
    name = get_text_value(product, ["name", "title", "imt_name"], "Название не указано")
    brand = get_text_value(product, ["brand", "brandName", "brand_name"], "Не указан")
    vendor_code = get_text_value(product, ["supplierArticle", "vendorCode", "supplier_article"], "Не указан")
    category = get_text_value(product, ["subjectName", "category", "subject"], "Не указана")
    description = get_text_value(product, ["description", "descr"], "Описание отсутствует")

    price = get_price(product)
    rating = get_rating(product)
    reviews = get_reviews(product)

    sale_percent = find_value(product, ["salePercent", "sale_percent"])
    if sale_percent is None:
        sale_percent = 0
    try:
        sale_percent = int(float(sale_percent))
    except (ValueError, TypeError):
        sale_percent = 0

    print("-" * 60)
    print("РАСПАРСЕННЫЕ ДАННЫЕ:")
    print("Название:", name)
    print("Цена:", price)
    print("Рейтинг:", rating)
    print("Отзывы:", reviews)
    print("Бренд:", brand)
    print("Артикул продавца:", vendor_code)
    print("-" * 60)

    return {
        "name": name,
        "price": price,
        "rating": rating,
        "reviews": reviews,
        "brand": brand,
        "category": category,
        "sale_percent": sale_percent,
        "vendor_code": vendor_code,
        "stock": "Нет данных",
        "description": description,
        "url": f"https://www.wildberries.by/catalog/{nm_id}/detail.aspx"
    }


# ============================================================
# ОСНОВНОЙ API WILDBERRIES (с увеличенным таймаутом и повторами)
# ============================================================

def get_from_wb_v4(nm_id):
    url = "https://card.wb.ru/cards/v4/detail"
    params = {
        "appType": 1,
        "curr": "rub",
        "dest": "-1257786",
        "spp": 30,
        "lang": "ru",
        "nm": nm_id
    }

    # Пробуем 3 раза с увеличивающимся таймаутом
    for attempt in range(3):
        try:
            print("=" * 60)
            print(f"ПРОБУЕМ WB API V4 (попытка {attempt + 1}/3)")
            print("Артикул:", nm_id)
            print("URL:", url)

            response = requests.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=30 + attempt * 10  # 30, 40, 50 секунд
            )

            print("HTTP:", response.status_code)

            if response.status_code != 200:
                print("Ответ сервера:")
                print(response.text[:500])
                if attempt < 2:
                    print(f"Ждём {attempt + 2} секунд перед следующей попыткой...")
                    time.sleep(attempt + 2)
                continue

            data = response.json()
            products = data.get("data", {}).get("products", [])

            if not products:
                products = data.get("products", [])

            if not products:
                print("API v4: products пустой")
                print("Ответ JSON:")
                print(str(data)[:3000])
                continue

            print("Количество товаров:", len(products))

            selected_product = None
            for product in products:
                product_id = product.get("id") or product.get("nmId") or product.get("nmID")
                if str(product_id) == str(nm_id):
                    selected_product = product
                    break

            if selected_product is None and len(products) == 1:
                selected_product = products[0]

            if selected_product is None:
                print("Нужный товар не найден среди products")
                continue

            print("Найден товар:", selected_product.get("name"))
            return build_product(selected_product, nm_id)

        except requests.RequestException as e:
            print(f"Ошибка HTTP (попытка {attempt + 1}): {e}")
            if attempt < 2:
                print(f"Ждём {attempt + 3} секунд перед следующей попыткой...")
                time.sleep(attempt + 3)
            continue
        except ValueError as e:
            print(f"Ошибка JSON (попытка {attempt + 1}): {e}")
            continue
        except Exception as e:
            print(f"Ошибка API v4 (попытка {attempt + 1}): {e}")
            continue

    return None


# ============================================================
# ЗАПАСНОЙ API ЧЕРЕЗ WB BASKET (с увеличенным таймаутом)
# ============================================================

def get_from_basket(nm_id):
    try:
        nm = int(nm_id)
        vol = nm // 100000
        part = nm // 1000

        print("=" * 60)
        print("ПРОБУЕМ BASKET API")
        print("vol:", vol)
        print("part:", part)

        basket_servers = [f"{i:02d}" for i in range(1, 31)]

        for server in basket_servers:
            url = f"https://basket-{server}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/info/ru/card.json"

            try:
                response = requests.get(url, headers=HEADERS, timeout=15)
                if response.status_code != 200:
                    continue

                data = response.json()
                if not data:
                    continue

                print("Basket API найден:", data.get("imt_name") or data.get("name"))

                product = {
                    "name": data.get("imt_name") or data.get("name") or "Название не указано",
                    "salePriceU": data.get("salePriceU") or data.get("sale_price_u") or data.get("clientPriceU") or data.get("priceU") or data.get("price_u") or 0,
                    "priceU": data.get("priceU") or data.get("basicPriceU") or 0,
                    "reviewRating": data.get("reviewRating") or data.get("rating") or 0,
                    "feedbacks": data.get("feedbacks") or data.get("feedbacksCount") or data.get("feedbackCount") or 0,
                    "brand": data.get("brand") or data.get("brandName") or data.get("selling", {}).get("brand_name") or "Не указан",
                    "supplierArticle": data.get("supplierArticle") or data.get("vendorCode") or "Не указан",
                    "subjectName": data.get("subjectName") or "Не указана",
                    "description": data.get("description") or "Описание отсутствует"
                }

                return build_product(product, nm_id)

            except Exception as e:
                print(f"Ошибка basket {server}: {e}")
                continue

        return None

    except Exception as e:
        print("Ошибка basket API:", e)
        return None


# ============================================================
# ПОЛУЧЕНИЕ ДАННЫХ ТОВАРА (с увеличенным временем)
# ============================================================

def get_product_data(nm_id):
    nm_id = normalize_article(nm_id)

    if not nm_id:
        print("Пустой артикул")
        return None

    if not 4 <= len(nm_id) <= 15:
        print(f"Некорректный артикул: {nm_id}")
        return None

    print("=" * 60)
    print("ИЩЕМ ТОВАР")
    print("Артикул:", nm_id)
    print("=" * 60)

    # 1. Основной API (с повторами)
    product = get_from_wb_v4(nm_id)

    if product:
        print("Товар найден через API v4")
        return product

    time.sleep(2)

    # 2. Резервный API
    product = get_from_basket(nm_id)

    if product:
        print("Товар найден через basket API")
        return product

    print("=" * 60)
    print("ТОВАР НЕ НАЙДЕН")
    print("Артикул:", nm_id)
    print("=" * 60)

    return None


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
    try:
        price = float(price)
    except (ValueError, TypeError):
        price = 0.0

    if price > 0:
        price_text = f"{price:,.2f}".replace(",", " ")
        answer_text += f"💰 <b>Цена:</b> {price_text} руб.\n"
    else:
        answer_text += "💰 <b>Цена:</b> нет данных\n"

    sale = product_data.get("sale_percent", 0)
    if sale:
        answer_text += f"🔥 <b>Скидка:</b> {sale}%\n"

    vendor_code = product_data.get("vendor_code")
    if vendor_code and vendor_code != "Не указан":
        answer_text += f"🔢 <b>Артикул продавца:</b> {html.escape(str(vendor_code))}\n"

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
        "Например:\n"
        "2147724\n\n"
        "Или:\n"
        "/check 2147724"
    )


@dp.message(Command("check"))
async def check_product(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Укажи артикул.\n\nПример:\n/check 2147724")
        return

    nm_id = normalize_article(args[1])
    if not nm_id:
        await message.answer("❌ Артикул должен содержать цифры.")
        return

    await message.answer(f"🔎 Ищу товар {nm_id}...\n⏳ Подожди несколько секунд.")

    try:
        loop = asyncio.get_running_loop()
        product_data = await loop.run_in_executor(None, get_product_data, nm_id)

        if not product_data:
            await message.answer(f"❌ Товар не найден.\n\nАртикул: {nm_id}\n\nПроверь артикул или попробуй через несколько секунд.")
            return

        answer_text = make_answer(product_data)
        await message.answer(answer_text, parse_mode="HTML", disable_web_page_preview=True)

    except Exception:
        logging.exception("Ошибка команды /check")
        await message.answer("❌ Произошла ошибка при получении данных товара.")


@dp.message()
async def auto_check(message: types.Message):
    if not message.text:
        return

    text = message.text.strip()
    match = re.search(r"\b(\d{4,15})\b", text)

    if not match:
        return

    nm_id = match.group(1)

    await message.answer(f"🔎 Артикул: {nm_id}\n⏳ Ищу товар...")

    try:
        loop = asyncio.get_running_loop()
        product_data = await loop.run_in_executor(None, get_product_data, nm_id)

        if not product_data:
            await message.answer(f"❌ Товар не найден.\n\nАртикул: {nm_id}")
            return

        answer_text = make_answer(product_data)
        await message.answer(answer_text, parse_mode="HTML", disable_web_page_preview=True)

    except Exception:
        logging.exception("Ошибка автоматического поиска")
        await message.answer("❌ Произошла ошибка при получении данных товара.")


# ============================================================
# MAIN
# ============================================================

async def main():
    print("=" * 60)
    print("BOT STARTING")
    print("=" * 60)
    print("Отправь в Telegram:")
    print("/check 2147724")

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
