import os
import time
import json
import re
import requests
import telebot

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_TELEGRAM_BOT_TOKEN")

# Данные Cloudflare Workers AI
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "ВАШ_CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "ВАШ_CLOUDFLARE_API_TOKEN")

# Прямой адрес API вашего сайта на Railway
RAILWAY_API_URL = "https://mircancelyarii-production.up.railway.app/api/products"

bot = telebot.TeleBot(BOT_TOKEN)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def analyze_image(image_bytes):
    """Распознавание товара через Cloudflare Workers AI (Llama 3.2 11B Vision)"""
    
    # Преобразуем байты изображения в список чисел (требование Cloudflare REST API для файлов)
    image_array = list(image_bytes)
    
    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/meta/llama-3.2-11b-vision-instruct"
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
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
        "2. Выведи ТОЛЬКО JSON-объект. Не добавляй никакого текста до или после JSON."
    )

    # Стандартная структура Cloudflare Workers AI для мультимодальных моделей
    payload = {
        "prompt": prompt,
        "image": image_array,
        "max_tokens": 500
    }

    response = requests.post(url, headers=headers, json=payload, timeout=35)
    res_data = response.json()

    # Автоматическое подтверждение соглашения при первом запуске
    if not res_data.get("success"):
        errors_str = str(res_data.get("errors", []))
        if "Model Agreement" in errors_str or "agree" in errors_str:
            requests.post(url, headers=headers, json={"prompt": "agree"}, timeout=15)
            response = requests.post(url, headers=headers, json=payload, timeout=35)
            res_data = response.json()

    if not res_data.get("success"):
        errors = res_data.get("errors", [])
        raise ValueError(f"Cloudflare API Error: {errors}")

    result = res_data.get("result", {})
    
    # Извлечение текста ответа
    raw_response = result.get("response", "")
    
    if isinstance(raw_response, dict):
        raw_text = str(raw_response.get("description") or raw_response.get("content") or "")
    else:
        raw_text = str(raw_response)

    raw_text = raw_text.strip()

    # Очистка от Markdown разметки ```json ... ```
    raw_text = re.sub(r'```(?:json)?', '', raw_text).strip()

    # Извлекаем JSON-строку
    json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if json_match:
        clean_json_str = json_match.group(0).strip()
    else:
        clean_json_str = raw_text

    if not clean_json_str:
        raise ValueError("Cloudflare вернул пустой ответ. Перепроверьте API Token или отправьте фото снова.")

    return json.loads(clean_json_str)

# ==================== ОБРАБОТЧИКИ ТЕЛЕГРАМ ====================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(
        message.chat.id, 
        "Привет! Бот работает на базе Cloudflare Workers AI.\n"
        "Отправляй фото товаров, и я добавлю их на сайт!"
    )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    status_msg = bot.reply_to(message, "⏳ Обрабатываю фото...")
    
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        bot.edit_message_text("⚡ Cloudflare AI анализирует товар...", chat_id=message.chat.id, message_id=status_msg.message_id)
        
        try:
            data = analyze_image(downloaded_file)
        except Exception as ai_err:
            err_text = str(ai_err)[:300]
            bot.edit_message_text(f"❌ Ошибка Cloudflare API:\n{err_text}", chat_id=message.chat.id, message_id=status_msg.message_id)
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
    print("Бот успешно запущен на базе Cloudflare Workers AI...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)