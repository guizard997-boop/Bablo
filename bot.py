import os
import json
import re
import base64
import requests
import telebot

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
API_SECRET = os.getenv("API_SECRET", "mir-api-secret-2026")
RAILWAY_BASE_URL = os.getenv("SITE_URL", "https://mircancelyarii-production.up.railway.app").rstrip("/")
PRIMARY_API_URL = f"{RAILWAY_BASE_URL}/api/products"
FALLBACK_API_URL = f"{RAILWAY_BASE_URL}/api/product"
CATEGORIES_URL = f"{RAILWAY_BASE_URL}/api/categories"

if not BOT_TOKEN:
    raise SystemExit("Укажите BOT_TOKEN или TELEGRAM_BOT_TOKEN в Variables")

bot = telebot.TeleBot(BOT_TOKEN)

# chat_id -> draft dict
# steps: wait_name, wait_category, wait_price
drafts = {}


def get_categories():
    try:
        r = requests.get(CATEGORIES_URL, timeout=15)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items") or []
            if items:
                return items
    except Exception as e:
        print("categories fetch error", e)
    # запасной список
    names = [
        "Письменные принадлежности", "Ручки и маркеры", "Карандаши и грифели",
        "Тетради и блокноты", "Бумага и альбомы", "Творчество и рисование",
        "Краски и кисти", "Школьные товары", "Пеналы и сумки", "Ранцы и рюкзаки",
        "Офисные принадлежности", "Файлы и папки", "Клей и скотч",
        "Стикеры и закладки", "Линейки и чертежные", "Калькуляторы",
        "Подарки и сувениры", "Для дошкольников",
    ]
    return [{"id": i + 1, "name": n} for i, n in enumerate(names)]


def categories_text(cats):
    lines = ["📂 Выберите <b>категорию</b> — пришлите номер:\n"]
    for i, c in enumerate(cats, 1):
        lines.append(f"{i}. {c['name']}")
    lines.append("\n0 — без категории")
    return "\n".join(lines)


def analyze_with_gemini(image_bytes):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY не настроен")
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    prompt = (
        "Проанализируй канцелярский товар на фото. Ответь ТОЛЬКО JSON:\n"
        '{"title":"краткое название на русском","price":150.0,"description":"описание на русском"}'
    )
    last_err = None
    env_model = os.getenv("GEMINI_MODEL", "").strip()
    models = []
    if env_model:
        models.append(env_model)
    models += ["gemini-3.6-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
    seen = set()
    models = [m for m in models if m and not (m in seen or seen.add(m))]
    for model in models:
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
            return json.loads(m.group(0) if m else raw)
        except Exception as e:
            last_err = e
    raise ValueError(f"Gemini error: {last_err}")


def analyze_with_hf(image_bytes):
    if not HF_TOKEN:
        raise ValueError("HF_TOKEN не настроен")
    clean = re.sub(r"[^\x00-\x7F]+", "", HF_TOKEN).strip()
    r = requests.post(
        "https://api-inference.huggingface.co/models/Salesforce/blip-image-captioning-base",
        headers={"Authorization": f"Bearer {clean}"},
        data=image_bytes,
        timeout=60,
    )
    if r.status_code != 200:
        raise ValueError(f"HF Error ({r.status_code}): {r.text[:150]}")
    data = r.json()
    caption = ""
    if isinstance(data, list) and data:
        caption = data[0].get("generated_text", "")
    title = (caption or "Товар").strip()[:120]
    if title:
        title = title[0].upper() + title[1:]
    return {"title": title, "price": 100.0, "description": title}


def analyze_image(image_bytes):
    try:
        return analyze_with_gemini(image_bytes), "Gemini"
    except Exception as ge:
        print("Gemini fail", ge)
        try:
            return analyze_with_hf(image_bytes), "Hugging Face"
        except Exception as he:
            raise ValueError(f"Gemini: {ge} | HF: {he}")


def post_to_site(title, price, description, image_bytes, category_id=None):
    payload = {
        "title": title,
        "price": price,
        "description": description or "",
        "api_key": API_SECRET,
    }
    if category_id:
        payload["category_id"] = str(category_id)
    files = {"image": ("photo.jpg", image_bytes, "image/jpeg")}
    headers = {"X-API-Key": API_SECRET}
    r = requests.post(PRIMARY_API_URL, data=payload, files=files, headers=headers, timeout=25)
    if r.status_code == 404:
        r = requests.post(FALLBACK_API_URL, data=payload, files=files, headers=headers, timeout=25)
    return r


def ask_category(chat_id, prefix=""):
    cats = get_categories()
    drafts.setdefault(chat_id, {})["categories"] = cats
    drafts[chat_id]["step"] = "wait_category"
    bot.send_message(chat_id, (prefix + "\n\n" if prefix else "") + categories_text(cats), parse_mode="HTML")


@bot.message_handler(commands=["start", "help"])
def start_cmd(message):
    drafts.pop(message.chat.id, None)
    bot.send_message(
        message.chat.id,
        "👋 Бот «Мир канцелярии»\n\n"
        "Отправьте <b>фото</b> товара.\n"
        "Дальше: название → <b>категория</b> → цена.\n\n"
        "/cancel — отмена",
        parse_mode="HTML",
    )


@bot.message_handler(commands=["cancel"])
def cancel_cmd(message):
    drafts.pop(message.chat.id, None)
    bot.send_message(message.chat.id, "❌ Отменено. Пришлите новое фото.")


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    chat_id = message.chat.id
    status = bot.reply_to(message, "⏳ Обрабатываю фото...")
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)
        drafts[chat_id] = {
            "step": "wait_name",
            "image": downloaded,
            "title": "",
            "price": 0,
            "description": "",
            "category_id": None,
        }

        bot.edit_message_text(
            "⚡ ИИ анализирует товар...",
            chat_id=chat_id,
            message_id=status.message_id,
        )

        try:
            data, provider = analyze_image(downloaded)
            title = str(data.get("title") or "").strip()[:200]
            try:
                price = float(data.get("price") or 0)
            except (TypeError, ValueError):
                price = 0.0
            desc = str(data.get("description") or "")[:2000]
            if title:
                drafts[chat_id]["title"] = title
                drafts[chat_id]["price"] = price
                drafts[chat_id]["description"] = desc
                drafts[chat_id]["provider"] = provider
                bot.edit_message_text(
                    f"✅ Похоже, это: <b>{title}</b>\n"
                    f"(ИИ: {provider}" + (f", цена ~{price:g} сом" if price else "") + ")",
                    chat_id=chat_id,
                    message_id=status.message_id,
                    parse_mode="HTML",
                )
                ask_category(chat_id, "Теперь выберите категорию (или напишите другое название):")
                # if user sends text that is not a number, treat as new name - handled in text handler
                return
        except Exception as ai_err:
            print("AI error", ai_err)

        bot.edit_message_text(
            "📷 Фото получено. AI не распознал.\n\nНапишите <b>название</b> товара:",
            chat_id=chat_id,
            message_id=status.message_id,
            parse_mode="HTML",
        )
        drafts[chat_id]["step"] = "wait_name"
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка:\n{str(e)[:300]}", chat_id=chat_id, message_id=status.message_id)


@bot.message_handler(func=lambda m: m.content_type == "text" and not (m.text or "").startswith("/"))
def handle_text(message):
    chat_id = message.chat.id
    text = (message.text or "").strip()
    d = drafts.get(chat_id)
    if not d or not d.get("step"):
        bot.send_message(chat_id, "Сначала отправьте <b>фото</b> товара или /start", parse_mode="HTML")
        return

    step = d["step"]

    if step == "wait_name":
        d["title"] = text[:200]
        ask_category(chat_id, f"Название: <b>{d['title']}</b>")
        return

    if step == "wait_category":
        cats = d.get("categories") or get_categories()
        cat_id = None
        if text != "0":
            try:
                num = int(text)
                if 1 <= num <= len(cats):
                    cat_id = cats[num - 1].get("id")
                else:
                    bot.send_message(chat_id, f"Введите число от 0 до {len(cats)}")
                    return
            except ValueError:
                # пользователь мог написать новое название вместо номера
                d["title"] = text[:200]
                ask_category(chat_id, f"Название обновлено: <b>{d['title']}</b>")
                return
        d["category_id"] = cat_id
        d["step"] = "wait_price"
        cat_label = "без категории"
        if cat_id:
            for c in cats:
                if c.get("id") == cat_id:
                    cat_label = c["name"]
                    break
        suggested = d.get("price") or 0
        extra = f"\n(ИИ предлагал ~{suggested:g} сом — можно подтвердить или написать другую)" if suggested else ""
        bot.send_message(
            chat_id,
            f"Категория: <b>{cat_label}</b>\n\nПришлите <b>цену</b> в сомах (число):{extra}",
            parse_mode="HTML",
        )
        return

    if step == "wait_price":
        try:
            price = float(text.replace("сом", "").replace(",", ".").strip())
            if price <= 0:
                raise ValueError()
        except ValueError:
            bot.send_message(chat_id, "Нужно число, например: <code>150</code>", parse_mode="HTML")
            return

        bot.send_message(chat_id, "🚀 Загружаю на сайт...")
        try:
            r = post_to_site(
                d.get("title") or "Товар",
                price,
                d.get("description") or "",
                d.get("image") or b"",
                d.get("category_id"),
            )
            if r.status_code in (200, 201):
                try:
                    body = r.json()
                    link = body.get("url", RAILWAY_BASE_URL)
                except Exception:
                    link = RAILWAY_BASE_URL
                bot.send_message(
                    chat_id,
                    f"✅ Товар добавлен!\n\n"
                    f"📌 {d.get('title')}\n"
                    f"💰 {price:g} сом\n"
                    f"🔗 {link}\n\n"
                    f"Можете прислать следующее фото.",
                )
            else:
                bot.send_message(chat_id, f"❌ Ошибка сайта ({r.status_code}):\n{r.text[:200]}")
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка загрузки:\n{str(e)[:300]}")
        drafts.pop(chat_id, None)
        return


if __name__ == "__main__":
    print("Бот запущен →", RAILWAY_BASE_URL)
    print("Gemini:", "да" if GEMINI_API_KEY else "нет")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
