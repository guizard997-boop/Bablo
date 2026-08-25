import os
import json
import re
import base64
import requests
import telebot
from openai import OpenAI

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "ВАШ_OPENROUTER_API_KEY")

# Прямой адрес API вашего сайта на Railway
RAILWAY_API_URL = "https://mircancelyarii-production.up.railway.app/api/products"

bot = telebot.TeleBot(BOT_TOKEN)

# Инициализация клиента OpenAI для OpenRouter с чисто ASCII-заголовками
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "HTTP-Referer": "https://mircancelyarii-production.up.railway.app",
        "X-Title": "Mir Kancelyarii Bot"
    }
)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def analyze_image(image_bytes):
    """Распознавание товара через бесплатный Qwen 2 VL на OpenRouter"""
    
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    data_url = f"data:image/jpeg;base64,{base64_image}"
    
    prompt = (
        "Проанализируй этот канцелярский товар на фото.\n"
        "Сформируй JSON-ответ строго в таком формате:\n"
        "{\n"
        '  "title": "Точное краткое название товара на русском языке (например, Ручка шариковая синяя)",\n'
        '  "price": 150.0,\n'
        '  "description": "Подробное и привлекательное описание товара на русском языке"\n'
        "}\n\n"
        "Правила:\n"
        "1. Поле 'price' должно быть числом (Float/Int) — средняя примерная цена товара в сомах (KGS).\n"
        "2. Выведи ТОЛЬКО JSON-объект. Не добавляй никакого лишнего текста до или после JSON."
    )

    response = client.chat.completions.create(
        model="qwen/qwen-2-vl-72b-instruct:free",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]
            }
        ],
        temperature=0.2,
        max_tokens=600
    )

    raw_text = response.choices[0].message.content.strip()
    
    # Очистка текста от возможных фоновых тегов ```json ... ```
    raw_text = re.sub(r'```(?:json)?', '', raw_text).strip()
    
    # Извлечение чистой структуры JSON
    json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if json_match:
        clean_json_str = json_match.group(0).strip()
        return json.loads(clean_json_str)
        
    raise ValueError(f"Не удалось извлечь JSON из ответа нейросети: {raw_text[:100]}")

# ==================== ОБРАБОТЧИКИ ТЕЛЕГРАМ ====================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(
        message.chat.id, 
        "Приветствую! Бот работает на базе OpenRouter (Qwen 2 VL).\n"
        "Отправляйте фото канцелярских товаров, и я добавлю их в каталог вашего сайта!"
    )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    status_msg = bot.reply_to(message, "⏳ Обрабатываю фото...")
    
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        bot.edit_message_text("⚡ Qwen 2 VL анализирует товар...", chat_id=message.chat.id, message_id=status_msg.message_id)
        
        try:
            data = analyze_image(downloaded_file)
        except Exception as ai_err:
            err_text = str(ai_err)[:300]
            bot.edit_message_text(f"❌ Ошибка OpenRouter API:\n{err_text}", chat_id=message.chat.id, message_id=status_msg.message_id)
            return

        title = data.get("title", "Товар без названия")
        price = data.get("price", 0.0)
        description = data.get("description", "")

        bot.edit_message_text("🚀 Загружаю на сайт...", chat_id=message.chat.id, message_id=status_msg.message_id)
        
        payload = {
            'title': title,
            'price': price,
            'description': description
        }
        files = {
            'image': ('photo.jpg', downloaded_file, 'image/jpeg')
        }
        
        response = requests.post(RAILWAY_API_URL, data=payload, files=files, timeout=20)
        
        if response.status_code in [200, 201]:
            safe_desc = str(description)[:300]
            bot.edit_message_text(
                f"✅ **Товар успешно добавлен!**\n\n"
                f"📌 **Название:** {title}\n"
                f"💰 **Цена:** {price} сом\n"
                f"📝 **Описание:** {safe_desc}", 
                chat_id=message.chat.id, 
                message_id=status_msg.message_id,
                parse_mode="Markdown"
            )
        else:
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
    print("Бот успешно запущен на базе OpenRouter...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
