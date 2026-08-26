,import os
import json
import re
import base64
import requests
import telebot

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "8990176397:AAFeYA_iaidYzOmTfM-4x2J40Hj6vi8QKUY"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
API_SECRET = os.getenv("API_SECRET", "mir-api-secret-2026")

RAILWAY_BASE_URL = os.getenv("SITE_URL", "https://mircancelyarii-production.up.railway.app").rstrip("/")
PRIMARY_API_URL = f"{RAILWAY_BASE_URL}/api/products"
FALLBACK_API_URL = f"{RAILWAY_BASE_URL}/api/product"

bot = telebot.TeleBot(BOT_TOKEN)


def analyze_with_gemini(image_bytes):
    """Распознавание через Google Gemini (REST API, без лишних SDK)."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY не настроен")

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    prompt = (
        "Проанализируй этот канцелярский товар на фото.\n"
        "Сформируй JSON строго в формате:\n"
        "{\n"
        '  "title": "Краткое название на русском",\n'
        '  "price": 150.0,\n'
        '  "description": "Описание на русском"\n'
        "}\n"
        "price — примерная цена в сомах (KGS), число. Выведи ТОЛЬКО JSON."
    )

    last_err = None
    for model in ("gemini-3.6-flash", "gemini-1.5-flash", "gemini-1.5-flash-latest"):
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={GEMINI_API_KEY}"
            )
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                    ]
                }],
                "generationConfig": {"responseMimeType": "application/json"},
            }
            r = requests.post(url, json=payload, timeout=45)
            data = r.json()
            if "error" in data:
                last_err = data["error"]
                continue
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = re.sub(r"```(?:json)?", "", raw).strip()
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return json.loads(m.group(0))
            return json.loads(raw)
        except Exception as e:
            last_err = e
            continue
    raise ValueError(f"Gemini error: {last_err}")


def analyze_with_hf(image_bytes):
    """Резерв: Hugging Face."""
    if not HF_TOKEN:
        raise ValueError("HF_TOKEN не настроен")

    clean = re.sub(r"[^\x00-\x7F]+", "", HF_TOKEN).strip()
    data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("utf-8")
    url = "https://router.huggingface.co/hf-inference/v1/chat/completions"
    headers = {"Authorization": f"Bearer {clean}", "Content-Type": "application/json"}
    prompt = (
        "Проанализируй канцелярский товар на фото. Ответь ТОЛЬКО JSON:\n"
        '{"title":"название на русском","price":150.0,"description":"описание"}'
    )
    payload = {
        "model": "vikhyatk/moondream2",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "max_tokens": 500,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=35)
    if r.status_code != 200:
        # fallback BLIP caption
        r2 = requests.post(
            "https://api-inference.huggingface.co/models/Salesforce/blip-image-captioning-base",
            headers={"Authorization": f"Bearer {clean}"},
            data=image_bytes,
            timeout=60,
        )
        if r2.status_code != 200:
            raise ValueError(f"HF Error ({r.status_code}): {r.text[:200]}")
        cap = r2.json()
        caption = ""
        if isinstance(cap, list) and cap:
            caption = cap[0].get("generated_text", "")
        title = caption.strip() or "Товар"
        return {"title": title[:120], "price": 100.0, "description": title}
    raw = r.json()["choices"][0]["message"]["content"].strip()
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"Не удалось извлечь JSON: {raw[:100]}")


def analyze_image(image_bytes):
    try:
        data = analyze_with_gemini(image_bytes)
        return data, "Gemini"
    except Exception as gemini_err:
        print(f"Gemini недоступен ({gemini_err}), пробую HF...")
        try:
            data = analyze_with_hf(image_bytes)
            return data, "Hugging Face"
        except Exception as hf_err:
            raise ValueError(f"Gemini: {gemini_err} | HF: {hf_err}")


def post_to_site(title, price, description, image_bytes):
    payload = {
        "title": title,
        "price": price,
        "description": description,
        "api_key": API_SECRET,
    }
    files = {"image": ("photo.jpg", image_bytes, "image/jpeg")}
    headers = {"X-API-Key": API_SECRET}
    r = requests.post(PRIMARY_API_URL, data=payload, files=files, headers=headers, timeout=25)
    if r.status_code == 404:
        r = requests.post(FALLBACK_API_URL, data=payload, files=files, headers=headers, timeout=25)
    return r


@bot.message_handler(commands=["start", "help"])
def start_cmd(message):
    bot.send_message(
        message.chat.id,
        "👋 Бот каталога «Мир канцелярии»\n\n"
        "Отправьте <b>фото</b> товара — ИИ определит название, цену и описание "
        "и добавит товар на сайт.",
        parse_mode="HTML",
    )


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    status = bot.reply_to(message, "⏳ Обрабатываю фото...")
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)

        bot.edit_message_text(
            "⚡ ИИ анализирует товар...",
            chat_id=message.chat.id,
            message_id=status.message_id,
        )

        try:
            data, provider = analyze_image(downloaded)
        except Exception as ai_err:
            bot.edit_message_text(
                f"❌ Ошибка ИИ:\n{str(ai_err)[:300]}\n\n"
                "Проверьте GEMINI_API_KEY или HF_TOKEN в Variables.",
                chat_id=message.chat.id,
                message_id=status.message_id,
            )
            return

        title = str(data.get("title") or "Товар").strip()[:200]
        try:
            price = float(data.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0
        description = str(data.get("description") or "")[:2000]

        bot.edit_message_text(
            f"🚀 Загружаю на сайт ({provider})...",
            chat_id=message.chat.id,
            message_id=status.message_id,
        )

        response = post_to_site(title, price, description, downloaded)
        if response.status_code in (200, 201):
            try:
                body = response.json()
                link = body.get("url", RAILWAY_BASE_URL)
            except Exception:
                link = RAILWAY_BASE_URL
            bot.edit_message_text(
                f"✅ Товар добавлен!\n\n"
                f"📌 {title}\n"
                f"💰 {price:g} сом\n"
                f"📝 {description[:200]}\n\n"
                f"🔗 {link}\n"
                f"🤖 {provider}",
                chat_id=message.chat.id,
                message_id=status.message_id,
            )
        else:
            bot.edit_message_text(
                f"❌ Ошибка сайта ({response.status_code}):\n{response.text[:200]}",
                chat_id=message.chat.id,
                message_id=status.message_id,
            )
    except Exception as e:
        bot.edit_message_text(
            f"❌ Ошибка бота:\n{str(e)[:300]}",
            chat_id=message.chat.id,
            message_id=status.message_id,
        )


if __name__ == "__main__":
    print("Бот запущен →", RAILWAY_BASE_URL)
    print("Gemini:", "да" if GEMINI_API_KEY else "нет", "| HF:", "да" if HF_TOKEN else "нет")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
