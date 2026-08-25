import os
import time
import json
import requests
import telebot
from google import genai
from google.api_core.exceptions import GoogleAPIError, ServiceUnavailable

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "ВАШ_GEMINI_API_KEY")

# Прямой адрес API вашего сайта на Railway
RAILWAY_API_URL = "https://mircancelyarii-production.up.railway.app/api/products"

bot = telebot.TeleBot(BOT_TOKEN)
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Кэш для предотвращения повторной обработки альбомов фото
processed_media_groups = set()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def analyze_image(image_bytes):
    """Запрос к Gemini 1.5 Flash с очисткой текста до JSON"""
    prompt = (
        "Проанализируй этот канцелярский товар на фото.\n"
        "Сформируй JSON-ответ строго в таком формате:\n"
        "{\n"
        '  "title": "Краткое название товара на русском языке",\n'
        '  "price": 150.0,\n'
        '  "description": "Привлекательное описание товара на русском языке"\n'
        "}\n\n"
        "Правила:\n"
        "1. Поле 'price' должно быть числом (Float/Int) — средняя примерная цена товара в сомах (KGS).\n"
        "2. Не добавляй абсолютно никакого текста, кроме чистого JSON."
    )
    
    response = ai_client.models.generate_content(
        model='gemini-1.5-flash',
        contents=[
            {'mime_type': 'image/jpeg', 'data': image_bytes},
            prompt
        ]
    )
    
    raw_text = response.text.strip()
    
    # Очистка Markdown разметки ```json ... ```
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
        
    return json.loads(raw_text.strip())

# ==================== ОБРАБОТЧИКИ ТЕЛЕГРАМ ====================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(
        message.chat.id, 
        "Привет! Отправь мне фото канцелярского товара, и я распознаю его через Gemini, "
        "сформирую JSON с ценой в сомах и автоматически добавлю на сайт!"
    )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    # Если отправлен альбом (несколько фото сразу), обрабатываем только 1-е фото из группы
    if message.media_group_id:
        if message.media_group_id in processed_media_groups:
            return
        processed_media_groups.add(message.media_group_id)
        if len(processed_media_groups) > 100:
            processed_media_groups.clear()

    status_msg = bot.reply_to(message, "⏳ Скачиваю фото...")
    
    try:
        # 1. Скачивание файла
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # 2. Генерация описания и цены через Gemini
        bot.edit_message_text("🤖 Gemini генерирует JSON-данные и цену...", chat_id=message.chat.id, message_id=status_msg.message_id)
        
        try:
            data = analyze_image(downloaded_file)
        except Exception as ai_err:
            err_text = str(ai_err)[:300]
            bot.edit_message_text(f"❌ Ошибка при запросе к Gemini:\n{err_text}", chat_id=message.chat.id, message_id=status_msg.message_id)
            return

        title = data.get("title", "Товар без названия")
        price = data.get("price", 0.0)
        description = data.get("description", "")

        # 3. Отправка POST-запроса на Railway API
        bot.edit_message_text("🚀 Отправляю данные на сайт...", chat_id=message.chat.id, message_id=status_msg.message_id)
        
        payload = {
            'title': title,
            'price': price,
            'description': description
        }
        files = {
            'image': ('photo.jpg', downloaded_file, 'image/jpeg')
        }
        
        response = requests.post(RAILWAY_API_URL, data=payload, files=files, timeout=15)
        
        if response.status_code in [200, 201]:
            # Безопасная обрезка описания, чтобы отрезать длинные тексты
            safe_desc = str(description)[:500]
            bot.edit_message_text(
                f"✅ **Товар успешно добавлен на сайт!**\n\n"
                f"📌 **Название:** {title}\n"
                f"💰 **Цена:** {price} сом\n"
                f"📝 **Описание:** {safe_desc}", 
                chat_id=message.chat.id, 
                message_id=status_msg.message_id,
                parse_mode="Markdown"
            )
        else:
            # Жесткая обрезка ответа сервера (до 150 символов)
            clean_error_text = response.text[:150].replace('<', '&lt;').replace('>', '&gt;')
            bot.edit_message_text(
                f"❌ Ошибка сервера сайта ({response.status_code}):\n{clean_error_text}", 
                chat_id=message.chat.id, 
                message_id=status_msg.message_id
            )

    except Exception as e:
        safe_exception = str(e)[:300].replace('<', '&lt;').replace('>', '&gt;')
        bot.edit_message_text(
            f"❌ Ошибка работы бота:\n{safe_exception}", 
            chat_id=message.chat.id, 
            message_id=status_msg.message_id
        )

# ==================== ЗАПУСК БОТА ====================
if __name__ == '__main__':
    print("Бот запущен и готов к работе...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)