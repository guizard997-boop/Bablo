import os
import json
import re
import base64
import requests
import telebot
from google import genai
from google.genai import types

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "ВАШ_GEMINI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN", "ВАШ_HUGGINGFACE_TOKEN")

# API вашего сайта на Railway (для загрузки товаров в базу данных)
RAILWAY_API_URL = "[https://mircancelyarii-production.up.railway.app/api/products](https://mircancelyarii-production.up.railway.app/api/products)"

bot = telebot.TeleBot(BOT_TOKEN)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ИИ ====================

def analyze_with_gemini(image_bytes):
    """Основной метод: Распознавание товара через Gemini API (версия 3.6 Flash)"""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "ВАШ_GEMINI_API_KEY":
        raise ValueError("GEMINI_API_KEY не настроен")

    client = genai.Client(api_key=GEMINI_API_KEY)

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
        "2. Выведи ТОЛЬКО JSON-объект."
    )

    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=[
            types.Part.from_bytes(
                data=image_bytes,
                mime_type='image/jpeg',
            ),
            prompt
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )

    raw_text = response.text.strip()
    return json.loads(raw_text)


def analyze_with_hf(image_bytes):
    """Резервный метод: Распознавание товара через Hugging Face Serverless API"""
    if not HF_TOKEN or HF_TOKEN == "ВАШ_HUGGINGFACE_TOKEN":
        raise ValueError("HF_TOKEN не настроен")

    clean_hf_token = re.sub(r'[^\x00-\x7F]+', '', HF_TOKEN).strip()
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    data_url = f"data:image/jpeg;base64,{base64_image}"

    url = "[https://router.huggingface.co/hf-inference/v1/chat/completions](https://router.huggingface.co/hf-inference/v1/chat/completions)"
    headers = {
        "Authorization": f"Bearer {clean_hf_token}",
        "Content-Type": "application/json"
    }

    prompt = (
        "Проанализируй этот канцелярский товар на фото.\n"
        "Сформируй JSON-ответ строго в таком формате:\n"
        "{\n"
        '  "title": "Точное краткое название товара на русском языке (например, Ручка шариковая синяя)",\n'
        '  "price": 150.0,\n'
        '  "description": "Подробное и привлекательное описание товара на русском языке"\n'
        "}\n\n"
        "Правила:\n"
        "1. Поле 'price' должно быть числом (Float/Int) — средняя цена товара в сомах (KGS).\n"
        "2. Выведи ТОЛЬКО JSON-объект без разметки markdown."
    )

    payload = {
        "model": "vikhyatk/moondream2",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]
            }
        ],
        "max_tokens": 500
    }

    response = requests.post(url, headers=headers, json=payload, timeout=35)
    if response.status_code != 200:
        raise ValueError(f"Hugging Face Error ({response.status_code}): {response.text[:200]}")

    res_data = response.json()
    raw_text = res_data["choices"][0]["message"]["content"].strip()
    raw_text = re.sub(r'```(?:json)?', '', raw_text).strip()

    json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0).strip())

    raise ValueError(f"Не удалось извлечь JSON из ответа HF: {raw_text[:100]}")


def analyze_image(image_bytes):
    """Каскадный анализ: сначала Gemini 3.6 Flash, в случае ошибки — Hugging Face"""
    try:
        data = analyze_with_gemini(image_bytes)
        return data, "Gemini 3.6 Flash"
    except Exception as gemini_err:
        print(f"Gemini недоступен ({gemini_err}), переключаюсь на Hugging Face...")
        try:
            data = analyze_with_hf(image_bytes)
            return data, "Hugging Face (Moondream2)"
        except Exception as hf_err:
            raise ValueError(f"Gemini error: {gemini_err} | HF error: {hf_err}")

# ==================== ОБРАБОТЧИКИ ТЕЛЕГРАМ ====================

@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(
        message.chat.id,
        "Приветствую! Бот работает на базе Gemini 3.6 Flash с автоматическим резервом на Hugging Face (Moondream2).\n"
        "Отправляйте фото канцелярских товаров, и я добавлю их в каталог вашего сайта!"
    )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    status_msg = bot.reply_to(message, "⏳ Обрабатываю фото...")

    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        bot.edit_message_text("⚡ ИИ анализирует товар...", chat_id=message.chat.id, message_id=status_msg.message_id)

        try:
            data, provider_used = analyze_image(downloaded_file)
        except Exception as ai_err:
            err_text = str(ai_err)[:300]
            bot.edit_message_text(f"❌ Ошибка распознавания (все ИИ недоступны):\n{err_text}", chat_id=message.chat.id, message_id=status_msg.message_id)
            return

        title = data.get("title", "Товар без названия")
        price = data.get("price", 0.0)
        description = data.get("description", "")

        bot.edit_message_text(f"🚀 Загружаю на сайт (обработано через {provider_used})...", chat_id=message.chat.id, message_id=status_msg.message_id)

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
                f"📝 **Описание:** {safe_desc}\n\n"
                f"🤖 *Провайдер ИИ:* {provider_used}",
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
    print("Бот успешно запущен (Gemini 3.6 + HF Fallback)...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
