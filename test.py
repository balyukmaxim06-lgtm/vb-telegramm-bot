import asyncio
import logging
import re
import os
import threading
import html

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

# ВСТАВЬ НОВЫЙ ТОКЕН, КОТОРЫЙ ПОЛУЧИШЬ ЧЕРЕЗ @BotFather
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
    """
    Оставляет только цифры в артикуле.
    """
    value = str(value).strip()
    value = re.sub(r"\D", "", value)
    return value


def get_price(product):
    """
    Получает актуальную цену.
    Ищет во всех возможных полях.
    """
    
    # Список всех возможных полей с ценой
    price_fields = [
        "salePriceU",
        "clientPriceU",
        "sale_price_u",
        "priceU",
        "basicPriceU",
        "price_u",
        "price",
        "PriceU",
        "SalePriceU",
        "ClientPriceU"
    ]
    
    # Проверяем все поля
    for field in price_fields:
        value = product.get(field)
        if value is not None and value != "":
            try:
                price = float(value)
                if price > 0:
                    # Если цена > 1000 — это копейки (делим на 100)
                    # Если цена < 1000 — это рубли (не делим)
                    if price > 1000:
                        return price / 100
                    else:
                        return price
            except (ValueError, TypeError):
                continue
    
    # Если не нашли — проверяем вложенные объекты
    for key, value in product.items():
        if isinstance(value, dict):
            result = get_price(value)
            if result > 0:
                return result
    
    return 0

def get_rating(product):
    """
    Получает рейтинг из всех возможных полей.
    """
    
    # Все возможные поля с рейтингом
    rating_fields = [
        "rating",
        "reviewRating",
        "Rating",
        "ReviewRating",
        "review_rating"
    ]
    
    # Проверяем все поля
    for field in rating_fields:
        value = product.get(field)
        if value is not None:
            try:
                rating = float(value)
                if rating > 0:
                    return rating
            except (ValueError, TypeError):
                continue
    
    # Проверяем вложенные объекты
    for key, value in product.items():
        if isinstance(value, dict):
            result = get_rating(value)
            if result > 0:
                return result
    
    return 0
def get_reviews(product):
    """
    Получает количество отзывов из всех возможных полей.
    """
    
    # Все возможные поля с отзывами
    reviews_fields = [
        "feedbacks",
        "feedbacksCount",
        "feedbackCount",
        "reviews",
        "reviewCount",
        "Feedbacks",
        "Reviews"
    ]
    
    # Проверяем все поля
    for field in reviews_fields:
        value = product.get(field)
        if value is not None:
            try:
                reviews = int(float(value))
                if reviews > 0:
                    return reviews
            except (ValueError, TypeError):
                continue
    
    # Проверяем вложенные объекты
    for key, value in product.items():
        if isinstance(value, dict):
            result = get_reviews(value)
            if result > 0:
                return result
    
    return 0
def build_product(product, nm_id):
    """
    Приводит ответ Wildberries к единому формату.
    """
    
    # ========================================================
    # ОТЛАДКА: выводим ВСЕ ключи объекта
    # ========================================================
    print("=" * 60)
    print("ВСЕ КЛЮЧИ В ОБЪЕКТЕ ТОВАРА:")
    if isinstance(product, dict):
        for key in product.keys():
            value = product[key]
            if isinstance(value, dict):
                print(f"  {key}: (dict) {list(value.keys())[:5]}...")
            elif isinstance(value, list):
                print(f"  {key}: (list) длина {len(value)}")
            else:
                print(f"  {key}: {type(value).__name__} = {str(value)[:50]}")
    print("=" * 60)

    name = (
        product.get("name")
        or product.get("title")
        or "Название не указано"
    )

    brand = (
        product.get("brand")
        or product.get("brandName")
        or "Не указан"
    )

    # Артикул продавца
    vendor_code = (
        product.get("supplierArticle")
        or product.get("vendorCode")
        or "Не указан"
    )

    # Категория
    category = (
        product.get("subjectName")
        or product.get("category")
        or "Не указана"
    )

    # Описание
    description = (
        product.get("description")
        or "Описание отсутствует"
    )

    return {
        "name": str(name).strip(),
        "price": get_price(product),
        "rating": get_rating(product),
        "reviews": get_reviews(product),
        "brand": str(brand).strip(),
        "category": str(category).strip(),
        "sale_percent": product.get("salePercent", 0) or 0,
        "vendor_code": str(vendor_code).strip(),
        "stock": "Нет данных",
        "description": str(description).strip(),
        "url": (
            f"https://www.wildberries.by/catalog/"
            f"{nm_id}/detail.aspx"
        )
    }



# ============================================================
# ОСНОВНОЙ API WILDBERRIES
# ============================================================

def get_from_wb_v4(nm_id):
    """
    Получение товара через актуальный cards/v4/detail.
    """

    url = "https://card.wb.ru/cards/v4/detail"

    params = {
        "appType": 1,
        "curr": "rub",
        "dest": "-1257786",
        "spp": 30,
        "lang": "ru",
        "nm": nm_id
    }

    try:

        print("=" * 60)
        print("Пробуем WB API v4")
        print("URL:", url)
        print("Артикул:", nm_id)

        response = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=20
        )

        print("HTTP:", response.status_code)
        print("Ответ:", response.text[:500])

        if response.status_code != 200:
            return None

        data = response.json()

        # Ожидаем:
        # {
        #   "data": {
        #       "products": [...]
        #   }
        # }

        products = (
            data
            .get("data", {})
            .get("products", [])
        )

        if not products:
            print("API v4: products пустой")
            return None

        # Ищем именно нужный nmID
        selected_product = None

        for product in products:

            product_id = (
                product.get("id")
                or product.get("nmId")
                or product.get("nmID")
            )

            if str(product_id) == str(nm_id):
                selected_product = product
                break

        # Если API вернул один товар,
        # используем его
        if selected_product is None and len(products) == 1:
            selected_product = products[0]

        if selected_product is None:
            print("Нужный товар не найден среди products")
            return None

        print(
            "Найден товар:",
            selected_product.get("name")
        )

        return build_product(
            selected_product,
            nm_id
        )

    except requests.RequestException as e:

        print("Ошибка HTTP:", e)

        return None

    except ValueError as e:

        print("Ошибка JSON:", e)

        return None

    except Exception as e:

        print("Ошибка API v4:", e)

        return None


# ============================================================
# ЗАПАСНОЙ API ЧЕРЕЗ WB BASKET
# ============================================================

def get_from_basket(nm_id):
    """
    Резервный способ получения card.json.

    Для WB:
        vol  = nm_id // 100000
        part = nm_id // 1000

    Например:
        330535596
        vol  = 3305
        part = 330535
    """

    try:

        nm = int(nm_id)

        vol = nm // 100000
        part = nm // 1000

        print("=" * 60)
        print("Пробуем резервный basket API")
        print("vol:", vol)
        print("part:", part)

        # Пробуем несколько basket-серверов
        basket_servers = [
            "01",
            "02",
            "03",
            "04",
            "05",
            "06",
            "07",
            "08",
            "09",
            "10",
            "11",
            "12",
            "13",
            "14",
            "15",
            "16",
            "17",
            "18",
            "19",
            "20",
            "21",
            "22",
            "23",
            "24",
            "25",
            "26",
            "27",
            "28",
            "29",
            "30"
        ]

        for server in basket_servers:

            url = (
                f"https://basket-{server}.wbbasket.ru/"
                f"vol{vol}/part{part}/{nm_id}/"
                f"info/ru/card.json"
            )

            try:

                print("Пробую:", url)

                response = requests.get(
                    url,
                    headers=HEADERS,
                    timeout=10
                )

                if response.status_code != 200:
                    continue

                data = response.json()

                if not data:
                    continue

                print(
                    "Basket API найден:",
                    data.get("imt_name")
                    or data.get("name")
                )

                product = {
                    "name": (
                        data.get("imt_name")
                        or data.get("name")
                        or "Название не указано"
                    ),

                    "salePriceU": (
                        data.get("salePriceU")
                        or data.get("sale_price_u")
                        or data.get("priceU")
                        or data.get("price_u")
                        or 0
                    ),

                    "reviewRating": (
                        data.get("reviewRating")
                        or data.get("rating")
                        or 0
                    ),

                    "feedbacks": (
                        data.get("feedbacks")
                        or data.get("feedbacksCount")
                        or 0
                    ),

                    "brand": (
                        data.get("brand")
                        or data.get("brandName")
                        or "Не указан"
                    ),

                    "supplierArticle": (
                        data.get("supplierArticle")
                        or data.get("vendorCode")
                        or "Не указан"
                    ),

                    "subjectName": (
                        data.get("subjectName")
                        or "Не указана"
                    ),

                    "description": (
                        data.get("description")
                        or "Описание отсутствует"
                    )
                }

                return build_product(
                    product,
                    nm_id
                )

            except Exception as e:

                print(
                    f"Ошибка basket {server}: {e}"
                )

                continue

        return None

    except Exception as e:

        print("Ошибка basket API:", e)

        return None


# ============================================================
# ПОЛУЧЕНИЕ ДАННЫХ ТОВАРА
# ============================================================

def get_product_data(nm_id):

    nm_id = normalize_article(nm_id)

    # Проверяем артикул
    if not nm_id:

        print("Пустой артикул")

        return None

    # Слишком короткий/длинный
    if not 4 <= len(nm_id) <= 15:

        print(
            f"Некорректный артикул: {nm_id}"
        )

        return None

    print("=" * 60)
    print("ИЩЕМ ТОВАР")
    print("Артикул:", nm_id)
    print("=" * 60)

    # ========================================================
    # 1. Основной API
    # ========================================================

    product = get_from_wb_v4(nm_id)

    if product:

        print("Товар найден через API v4")

        return product

    # Небольшая пауза
    time_sleep = 1

    import time
    time.sleep(time_sleep)

    # ========================================================
    # 2. Резервный API
    # ========================================================

    product = get_from_basket(nm_id)

    if product:

        print("Товар найден через basket API")

        return product

    # ========================================================
    # Ничего не найдено
    # ========================================================

    print("=" * 60)
    print("ТОВАР НЕ НАЙДЕН")
    print("Артикул:", nm_id)
    print("=" * 60)

    return None


# ============================================================
# ФОРМИРОВАНИЕ ОТВЕТА
# ============================================================

def make_answer(product_data):

    name = html.escape(
        str(product_data.get("name", "Название не указано"))
    )

    answer_text = (
        f"📦 <b>{name}</b>\n\n"
    )

    brand = product_data.get("brand")

    if brand and brand != "Не указан":

        answer_text += (
            f"🏷️ <b>Бренд:</b> "
            f"{html.escape(str(brand))}\n"
        )

    category = product_data.get("category")

    if category and category != "Не указана":

        answer_text += (
            f"📂 <b>Категория:</b> "
            f"{html.escape(str(category))}\n"
        )

    price = product_data.get("price", 0)

    answer_text += (
        f"💰 <b>Цена:</b> "
        f"{price:.2f} руб.\n"
    )

    sale = product_data.get(
        "sale_percent",
        0
    )

    if sale:

        answer_text += (
            f"🔥 <b>Скидка:</b> "
            f"{sale}%\n"
        )

    vendor_code = product_data.get(
        "vendor_code"
    )

    if (
        vendor_code
        and vendor_code != "Не указан"
    ):

        answer_text += (
            f"🔢 <b>Артикул продавца:</b> "
            f"{html.escape(str(vendor_code))}\n"
        )

    rating = product_data.get(
        "rating",
        0
    )

    reviews = product_data.get(
        "reviews",
        0
    )

    answer_text += (
        f"⭐ <b>Рейтинг:</b> {rating}\n"
        f"📝 <b>Отзывов:</b> {reviews}\n"
    )

    description = product_data.get(
        "description"
    )

    if (
        description
        and description != "Описание отсутствует"
    ):

        description = str(description)

        if len(description) > 500:
            description = (
                description[:500]
                + "..."
            )

        description = html.escape(
            description
        )

        answer_text += (
            f"\n📄 <b>Описание:</b>\n"
            f"{description}\n"
        )

    product_url = product_data.get(
        "url"
    )

    if product_url:

        answer_text += (
            f"\n🔗 <a href='{product_url}'>"
            f"Открыть на Wildberries"
            f"</a>"
        )

    return answer_text


# ============================================================
# /START
# ============================================================

@dp.message(Command("start"))
async def start_command(
    message: types.Message
):

    await message.answer(
        "👋 Привет! Я бот для анализа "
        "товаров на Wildberries.by.\n\n"
        "📌 Отправь мне артикул товара:\n\n"
        "Например:\n"
        "2147724\n\n"
        "Или:\n"
        "/check 2147724"
    )


# ============================================================
# /CHECK
# ============================================================

@dp.message(Command("check"))
async def check_product(
    message: types.Message
):

    args = message.text.split()

    if len(args) < 2:

        await message.answer(
            "❌ Укажи артикул.\n\n"
            "Пример:\n"
            "/check 2147724"
        )

        return

    nm_id = normalize_article(
        args[1]
    )

    if not nm_id:

        await message.answer(
            "❌ Артикул должен содержать цифры."
        )

        return

    await message.answer(
        f"🔎 Ищу товар {nm_id}...\n"
        f"⏳ Подожди несколько секунд."
    )

    try:

        loop = asyncio.get_running_loop()

        product_data = await loop.run_in_executor(
            None,
            get_product_data,
            nm_id
        )

        if not product_data:

            await message.answer(
                "❌ Товар не найден.\n\n"
                f"Артикул: {nm_id}\n\n"
                "Проверь артикул или попробуй "
                "через несколько секунд."
            )

            return

        answer_text = make_answer(
            product_data
        )

        await message.answer(
            answer_text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    except Exception as e:

        logging.exception(
            "Ошибка команды /check"
        )

        await message.answer(
            "❌ Произошла ошибка при получении "
            "данных товара."
        )


# ============================================================
# АВТОМАТИЧЕСКОЕ РАСПОЗНАВАНИЕ АРТИКУЛА
# ============================================================

@dp.message()
async def auto_check(
    message: types.Message
):

    # Если это не текст
    if not message.text:

        return

    text = message.text.strip()

    # Ищем артикул от 4 до 15 цифр
    match = re.search(
        r"\b(\d{4,15})\b",
        text
    )

    if not match:

        return

    nm_id = match.group(1)

    await message.answer(
        f"🔎 Артикул: {nm_id}\n"
        f"⏳ Ищу товар..."
    )

    try:

        loop = asyncio.get_running_loop()

        product_data = await loop.run_in_executor(
            None,
            get_product_data,
            nm_id
        )

        if not product_data:

            await message.answer(
                "❌ Товар не найден.\n\n"
                f"Артикул: {nm_id}"
            )

            return

        answer_text = make_answer(
            product_data
        )

        await message.answer(
            answer_text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    except Exception as e:

        logging.exception(
            "Ошибка автоматического поиска"
        )

        await message.answer(
            "❌ Произошла ошибка при получении "
            "данных товара."
        )


# ============================================================
# MAIN
# ============================================================

async def main():

    print("=" * 60)
    print("BOT STARTING")
    print("=" * 60)

    print(
        "Отправь в Telegram:"
    )

    print(
        "/check 2147724"
    )

    # Удаляем старый webhook
    await bot.delete_webhook(
        drop_pending_updates=True
    )

    # Запускаем Telegram polling
    await dp.start_polling(bot)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    # ========================================================
    # FLASK ДЛЯ RENDER
    # ========================================================

    def run_flask():

        port = int(
            os.environ.get(
                "PORT",
                8080
            )
        )

        print(
            f"Flask запускается на порту {port}"
        )

        web_app.run(
            host="0.0.0.0",
            port=port
        )


    flask_thread = threading.Thread(
        target=run_flask,
        daemon=True
    )

    flask_thread.start()

    # ========================================================
    # TELEGRAM BOT
    # ========================================================

    asyncio.run(main())
