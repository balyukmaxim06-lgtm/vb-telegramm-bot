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

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager


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
# ПОЛУЧЕНИЕ ДАННЫХ ТОВАРА
# ============================================================

def get_product_data(nm_id):
    """Получает расширенные данные товара с Wildberries.by"""

     options = Options()
    
    # ПРОКСИ (вставь сюда свой)
    PROXY = "5.129.228.92"  # Замени на рабочий прокси
    options.add_argument(f"--proxy-server=http://{PROXY}")
    
    options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--lang=ru")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
    except Exception as e:
        print(f"Ошибка драйвера: {e}")
        return None

    try:

        # Скрываем webdriver
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """
            }
        )

        url = f"https://www.wildberries.by/catalog/{nm_id}/detail.aspx"

        print(f"Загружаем {url}...")

        driver.get(url)

        # ====================================================
        # УВЕЛИЧЕННОЕ ВРЕМЯ ОЖИДАНИЯ (30 секунд)
        # ====================================================
        print("Ожидаем загрузки данных...")
        try:
            # Ждём появления элемента с ценой или названием до 30 секунд
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1, span[class*='price'], div[class*='product']"))
            )
            print("✅ Страница загружена!")
        except TimeoutException:
            print("⏰ Страница не загрузилась за 30 секунд")
            # Проверяем на капчу
            if "подозрительная активность" in driver.page_source.lower():
                print("🚫 Обнаружена капча! Бот заблокирован.")
                return None
            # Если не капча, даём ещё 10 секунд
            time.sleep(30)

        # Прокручиваем страницу
        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight / 2);"
        )

        time.sleep(15)

        # ====================================================
        # ПЕРЕМЕННЫЕ
        # ====================================================

        name = "Название не найдено"
        price = 0
        rating = 0
        reviews = 0
        brand = "Не указан"
        category = "Не указана"
        sale_percent = 0
        vendor_code = "Не указан"
        stock_info = "Нет данных"
        description = "Описание отсутствует"

        # ====================================================
        # 1. ПОИСК В JSON
        # ====================================================

        script_elements = driver.find_elements(
            By.XPATH,
            "//script[@type='application/json']"
        )

        print(f"Найдено JSON-скриптов: {len(script_elements)}")

        for script in script_elements:

            content = script.get_attribute("innerHTML")

            if not content:
                continue

            try:

                data = json.loads(content)

                if (
                    "product" in data
                    and isinstance(data["product"], dict)
                ):

                    product = data["product"]

                    product_name = product.get("name")

                    if product_name:

                        name = str(product_name).strip()

                        print(f"Найдено название в JSON: {name}")

                        price_u = product.get("priceU", 0)

                        if price_u:
                            price = float(price_u) / 100

                        rating = product.get("rating", 0)
                        reviews = product.get("feedbacks", 0)

                        brand = product.get("brand", brand)
                        if brand:
                            print(f"Бренд из JSON: {brand}")

                        break

            except Exception:
                continue

        # ====================================================
        # 2. ПОИСК НАЗВАНИЯ (если не нашли в JSON)
        # ====================================================

        if name == "Название не найдено":

            try:

                title = driver.title.strip()

                print(f"Title страницы: {title}")

                if title:

                    title = re.sub(
                        r"\s*[—|-]\s*Wildberries.*$",
                        "",
                        title,
                        flags=re.IGNORECASE
                    )

                    title = re.sub(
                        r"\s*[—|-]\s*купить.*$",
                        "",
                        title,
                        flags=re.IGNORECASE
                    )

                    title = title.strip()

                    if len(title) > 5:

                        name = title

                        print(f"Название из title: {name}")

            except Exception as e:

                print(f"Ошибка при поиске title: {e}")

        if name == "Название не найдено":

            try:

                h1_elements = driver.find_elements(
                    By.TAG_NAME,
                    "h1"
                )

                print(f"Найдено H1: {len(h1_elements)}")

                for element in h1_elements:

                    text = element.text.strip()

                    if not text:
                        continue

                    lower_text = text.lower()

                    if "wildberries" in lower_text:
                        continue

                    if "купить" == lower_text:
                        continue

                    if len(text) < 5:
                        continue

                    name = text

                    print(f"Название из H1: {name}")

                    break

            except Exception as e:

                print(f"Ошибка H1: {e}")

        # ====================================================
        # 3. ПОИСК БРЕНДА
        # ====================================================

        if brand == "Не указан":
            try:
                brand_selectors = [
                    "span[class*='brand']",
                    "a[class*='brand']",
                    "div[class*='brand'] span",
                    "[data-link='text:brand']"
                ]
                for selector in brand_selectors:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        text = el.text.strip()
                        if text and len(text) > 1:
                            brand = text
                            print(f"Найден бренд: {brand}")
                            break
                    if brand != "Не указан":
                        break
            except Exception as e:
                print(f"Ошибка поиска бренда: {e}")

        # ====================================================
        # 4. ПОИСК КАТЕГОРИИ
        # ====================================================

        if category == "Не указана":
            try:
                category_selectors = [
                    "ol[class*='breadcrumb'] li:last-child",
                    "div[class*='breadcrumbs'] a:last-child",
                    "nav[class*='breadcrumb'] span:last-child",
                    "[data-link='text:breadcrumbs'] span:last-child"
                ]
                for selector in category_selectors:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        text = el.text.strip()
                        if text and len(text) > 1:
                            category = text
                            print(f"Найдена категория: {category}")
                            break
                    if category != "Не указана":
                        break
            except Exception as e:
                print(f"Ошибка поиска категории: {e}")

        # ====================================================
        # 5. ПОИСК СКИДКИ
        # ====================================================

        try:
            sale_selectors = [
                "span[class*='sale']",
                "span[class*='discount']",
                "div[class*='sale']",
                "[data-link='text:sale']"
            ]
            for selector in sale_selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    text = el.text.strip()
                    if text and '%' in text:
                        sale_percent = int(re.sub(r'\D', '', text))
                        if sale_percent > 0:
                            print(f"Найдена скидка: {sale_percent}%")
                            break
                if sale_percent > 0:
                    break
        except Exception as e:
            print(f"Ошибка поиска скидки: {e}")

        # ====================================================
        # 6. ПОИСК АРТИКУЛА ПРОДАВЦА
        # ====================================================

        try:
            vendor_selectors = [
                "span[class*='vendor']",
                "div[class*='vendor'] span",
                "span[class*='article']",
                "[data-link='text:vendorCode']"
            ]
            for selector in vendor_selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    text = el.text.strip()
                    if text and any(c.isdigit() for c in text):
                        vendor_code = text
                        print(f"Найден артикул продавца: {vendor_code}")
                        break
                if vendor_code != "Не указан":
                    break
        except Exception as e:
            print(f"Ошибка поиска артикула: {e}")

        # ====================================================
        # 7. ПОИСК НАЛИЧИЯ
        # ====================================================

        try:
            stock_selectors = [
                "span[class*='stock']",
                "div[class*='stock'] span",
                "span[class*='availability']",
                "[data-link='text:stock']"
            ]
            for selector in stock_selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    text = el.text.strip()
                    if text and any(c.isdigit() for c in text):
                        stock_info = text
                        print(f"Найдено наличие: {stock_info}")
                        break
                if stock_info != "Нет данных":
                    break
        except Exception as e:
            print(f"Ошибка поиска наличия: {e}")

        # ====================================================
        # 8. ПОИСК ОПИСАНИЯ
        # ====================================================

        try:
            description_selectors = [
                "div[class*='description']",
                "div[class*='about']",
                "div[class*='product-description']",
                "[data-link='text:description']"
            ]
            for selector in description_selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    text = el.text.strip()
                    if text and len(text) > 20:
                        description = text[:300] + "..." if len(text) > 300 else text
                        print(f"Найдено описание: {description[:100]}...")
                        break
                if description != "Описание отсутствует":
                    break
        except Exception as e:
            print(f"Ошибка поиска описания: {e}")

        # ====================================================
        # 9. ЦЕНА (если не нашли в JSON)
        # ====================================================

        if price == 0:

            price_selectors = [
                "span[data-link='text:priceWithDiscount']",
                "span[class*='final-price']",
                "span[class*='price-block'] span",
                "span[class*='price']"
            ]

            for selector in price_selectors:

                try:

                    elements = driver.find_elements(
                        By.CSS_SELECTOR,
                        selector
                    )

                    for element in elements:

                        text = element.text.strip()

                        if not text:
                            continue

                        if not any(
                            c.isdigit()
                            for c in text
                        ):
                            continue

                        cleaned = re.sub(
                            r"[^\d.,]",
                            "",
                            text
                        )

                        cleaned = cleaned.replace(
                            ",",
                            "."
                        )

                        try:

                            candidate = float(cleaned)

                            if candidate > 0:

                                price = candidate

                                print(f"Найдена цена: {price}")

                                break

                        except ValueError:
                            continue

                    if price > 0:
                        break

                except Exception:
                    continue

        # ====================================================
        # 10. РЕЙТИНГ (если не нашли в JSON)
        # ====================================================

        if not rating:

            rating_selectors = [
                "span[class*='rating']",
                "span[data-link='text:rating']",
                "div[class*='rating'] span"
            ]

            for selector in rating_selectors:

                try:

                    elements = driver.find_elements(
                        By.CSS_SELECTOR,
                        selector
                    )

                    for element in elements:

                        text = element.text.strip()

                        if not text:
                            continue

                        match = re.search(
                            r"\d+[.,]\d+",
                            text
                        )

                        if match:

                            rating = float(
                                match.group(0).replace(
                                    ",",
                                    "."
                                )
                            )

                            print(f"Найден рейтинг: {rating}")

                            break

                    if rating:
                        break

                except Exception:
                    continue

        # ====================================================
        # 11. ОТЗЫВЫ (если не нашли в JSON)
        # ====================================================

        if not reviews:

            reviews_selectors = [
                "span[data-link='text:feedbacks']",
                "span[class*='count-feedback']",
                "a[class*='feedbacks'] span",
                "span[class*='review']",
                "div[class*='reviews'] span"
            ]

            for selector in reviews_selectors:

                try:

                    elements = driver.find_elements(
                        By.CSS_SELECTOR,
                        selector
                    )

                    for element in elements:

                        text = element.text.strip()

                        if not text:
                            continue

                        if not any(
                            c.isdigit()
                            for c in text
                        ):
                            continue

                        numbers = re.sub(
                            r"\D",
                            "",
                            text
                        )

                        if numbers:

                            candidate = int(numbers)

                            if candidate > 0:

                                reviews = candidate

                                print(f"Найдено отзывов: {reviews}")

                                break

                    if reviews:
                        break

                except Exception:
                    continue

        # ====================================================
        # РЕЗУЛЬТАТ
        # ====================================================

        result = {
            "name": name,
            "price": price,
            "rating": rating,
            "reviews": reviews,
            "brand": brand,
            "category": category,
            "sale_percent": sale_percent,
            "vendor_code": vendor_code,
            "stock": stock_info,
            "description": description,
            "url": url
        }

        print("=" * 50)
        print("РЕЗУЛЬТАТ:")
        print(result)
        print("=" * 50)

        return result

    except Exception as e:

        print(f"Ошибка получения данных: {e}")

        return None

    finally:

        driver.quit()


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
        "⏳ Это займёт примерно 15-20 секунд."
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
            product_data["name"] == "Название не найдено"
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
        "⏳ Ищу товар... (это займёт 15-20 секунд)"
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

        if product_data["price"] == 0 and product_data["name"] == "Название не найдено":
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
