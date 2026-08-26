import os
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
    url = "[https://router.huggingface.co/hf-inference/v1/chat/completions](https://router.huggingface.co/hf-inference/v1/chat/completions)"
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
            "[https://api-inference.huggingface.co/models/Salesforce/blip-image-captioning-base](https://api-inference.huggingface.co/models/Salesforce/blip-image-captioning-base)",
            headers={"Authorization": f"Bearer {clean}"},
            data=image_bytes,
            timeout=60,
        )
        if r2.status_code != 200:
            raise ValueError(f"HF Error ({r.status_code}): {r.text[:200]}")
        cap = r2.json()
