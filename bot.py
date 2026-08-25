import os
import time
import json
import requests
import telebot
from google import genai
from google.api_core.exceptions import GoogleAPIError, ServiceUnavailable

# ==================== НАСТРОЙКИ ====================
# Токены берутся из переменных окружения Railway (или прямо из строк, если вставить в кавычки)
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "ВАШ_GEMINI_API_KEY")

# Прямой адрес API вашего сайта на Railway
RAILWAY_API_URL = "https://mircancelyarii-production.up.railway.app/api/products"

bot = telebot.TeleBot(BOT_TOKEN)
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def analyze_image_with_retry(image_bytes, retries=3, delay=2):
    """Отправка фото в Gemini 1.5 Flash с генерацией строгого JSON и защитой от ошибки 503"""
    
    prompt = (
        "Проанализируй этот канцелярский товар на фото.\n"
        "Сформируй JSON-ответ строго в таком формате:\n"
        "{\n"
        '  "title": "Краткое название товара на русском языке",\n'
        '  "price": 150.0,\n'
        '  "description": "Привлекательное описание товара на русском языке"\n'
        "}\n\n"
        "Правила:\n"
        "1. Поле 'price' должно быть числом (Float/Int). Это примерная средняя розничная цена товара в сомах (KGS).\n"
        "2. Не добавляй никаких лишних символов, кроме валидного JSON."
    )
    
    for attempt in range(retries):
        try:
            response = ai_client.models.generate_content(
                model='gemini-1.5-flash',
                contents=[
                    {'mime_type': 'image/jpeg', 'data': image_bytes},
                    prompt
                ]
            )
            
            # Очистка текста от возможных блоков markdown ```json ... ```
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
                
            return json.loads(raw_text.strip())

        except (ServiceUnavailable, GoogleAPIError) as e:
            if attempt == retries - 1:
                raise e
            print(f"Сервер Gemini перегружен (503). Повтор через {delay} сек...")
            time.sleep(delay)
            delay *= 2
        except json.JSONDecodeError:
            # Резервный вариант, если Gemini вернула не валидный JSON
            return {
                "title": "Канцелярский товар",
                "price": 0.0,
                "description": response.text.strip()
            }

# ==================== ОБРАБОТЧИКИ ТЕЛЕГРАМ ====================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(
        message.chat.id, 
        "Привет! Отправь мне фото канцелярского товара, и я автоматически распознаю его через Gemini 1.5 Flash, "
        "сформирую JSON с ценой в сомах и добавлю на сайт!"
    )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    status_msg = bot.reply_to(message, "⏳ Скачиваю фото и отправляю в Gemini 1.5 Flash...")
    
    try:
        # 1. Скачиваем фото из Telegram
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # 2. Распознаем через Gemini 1.5 Flash (получаем JSON)
        bot.edit_message_text("🤖 Gemini генерирует JSON-данные и цену...", chat_id=message.chat.id, message_id=status_msg.message_id)
        data = analyze_image_with_retry(downloaded_file)
        
        title = data.get("title", "Товар без названия")
        price = data.get("price", 0.0)
        description = data.get("description", "")

        # 3. Отправляем готовые данные на Railway
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
            bot.edit_message_text(
                f"✅ **Товар успешно добавлен на сайт!**\n\n"
                f"📌 **Название:** {title}\n"
                f"💰 **Цена:** {price} сом\n"
                f"📝 **Описание:** {description}", 
                chat_id=message.chat.id, 
                message_id=status_msg.message_id,
                parse_mode="Markdown"
            )
        else:
            bot.edit_message_text(
                f"❌ Ошибка сервера сайта ({response.status_code}):\n{response.text[:200]}", 
                chat_id=message.chat.id, 
                message_id=status_msg.message_id
            )

    except Exception as e:
        bot.edit_message_text(
            f"❌ Произошла ошибка: {str(e)}", 
            chat_id=message.chat.id, 
            message_id=status_msg.message_id
        )

# ==================== ЗАПУСК БОТА ====================
if __name__ == '__main__':
    print("Бот с JSON-обработкой и ценами в KGS запущен...")
    bot.infinity_polling()
