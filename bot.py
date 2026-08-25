import os
import json
import io
import requests
from PIL import Image
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types

# ---------------- CONFIGURATION ----------------
TELEGRAM_BOT_TOKEN = "8800283479:AAF2wbYPGH2aabxiOAuJ62qQqbNb1NyrX3k"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") # Берется из Variables в Railway
SITE_API_URL = os.environ.get("SITE_API_URL", "https://mircancelyarii-production.up.railway.app/api/products")
# -----------------------------------------------

if not GEMINI_API_KEY:
    raise ValueError("❌ Ошибка: Переменная GEMINI_API_KEY не задана в настройках Railway!")

# Инициализируем клиент Gemini
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я готов к работе. 🚀\n\n"
        "Отправь мне фото канцелярского товара, я распознаю его через Gemini ИИ, "
        "создам название и описание, а затем выложу на твой сайт!"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⏳ Скачиваю фото и анализирую через бесплатный Gemini ИИ...")
    
    try:
        # 1. Скачивание фото из Telegram
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # Преобразуем байты в объект Pillow Image
        image = Image.open(io.BytesIO(photo_bytes))

        # 2. Запрос к стабильной модель Gemini 2.0 Flash
        await status_msg.edit_text("🧠 Генерирую название и описание товара...")
        
        prompt = (
            "Распознай предмет на фото (это канцелярский товар). "
            "Верни ответ строго в формате JSON с двумя полями:\n"
            "1. \"title\": короткое понятное название товара на русском языке.\n"
            "2. \"description\": подробное привлекательное продающее описание товара на русском языке.\n"
            "Не добавляй никакой разметки markdown или лишнего текста, только чистый JSON."
        )

        response = gemini_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=[image, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        # Разбор ответа от ИИ
        product_data = json.loads(response.text)
        title = product_data.get("title", "Без названия")
        description = product_data.get("description", "Без описания")

        await status_msg.edit_text(
            f"✅ **ИИ распознал товар:**\n\n"
            f"📌 **Название:** {title}\n"
            f"📝 **Описание:** {description}\n\n"
            f"🚀 Отправляю товар на сайт..."
        )

        # 3. Отправка данных на сайт
        payload = {
            'title': title,
            'description': description
        }
        files = {
            'image': ('photo.jpg', photo_bytes, 'image/jpeg')
        }

        site_response = requests.post(SITE_API_URL, data=payload, files=files, timeout=30)

        if site_response.status_code in [200, 201]:
            await update.message.reply_text("🎉 Товар успешно опубликован на сайте!")
        else:
            await update.message.reply_text(
                f"⚠️ Ошибка при отправке на сайт.\n"
                f"Код ответа сервера: {site_response.status_code}\n"
                f"Текст ответа: {site_response.text}"
            )

    except Exception as e:
        await update.message.reply_text(f"❌ Произошла ошибка: {str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("🤖 Бот успешно запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
