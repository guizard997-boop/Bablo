# -*- coding: utf-8 -*-
"""
Бот оплаты канцтоваров:
- каталог с кнопками
- выбор товара → цена + QR
- админ добавляет/удаляет товары
Токен: 8990176397:AAFeYA_iaidYzOmTfM-4x2J40Hj6vi8QKUY
Admin: 8569472160
Оплата: Абдумалик К. · +996 220 979 346
"""

import os
import sys
import json
import uuid
import io
import subprocess
from datetime import datetime

try:
    import telebot
    from telebot import types
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyTelegramBotAPI>=4.14.0", "-q"])
    import telebot
    from telebot import types

try:
    import qrcode
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "qrcode[pil]>=7.4", "-q"])
    import qrcode

# ================== CONFIG ==================
BOT_TOKEN = "8990176397:AAFeYA_iaidYzOmTfM-4x2J40Hj6vi8QKUY"
ADMIN_IDS = [8569472160]

PAYEE_NAME = "Абдумалик К."
PAYEE_PHONE = "+996 220 979 346"
PAYEE_PHONE_RAW = "996220979346"

CURRENCY = "KGS"  # канцтовары удобнее в сомах; можно USD
DATA_FILE = "shop_data.json"

# Стартовый каталог (админ может менять)
DEFAULT_PRODUCTS = [
    {"id": "p1", "name": "Тетрадь 48 л.", "price": 80, "category": "Тетради", "emoji": "📓"},
    {"id": "p2", "name": "Тетрадь 96 л.", "price": 120, "category": "Тетради", "emoji": "📕"},
    {"id": "p3", "name": "Ручка шариковая синяя", "price": 25, "category": "Письмо", "emoji": "🖊️"},
    {"id": "p4", "name": "Набор ручек 10 шт.", "price": 180, "category": "Письмо", "emoji": "✍️"},
    {"id": "p5", "name": "Карандаш HB", "price": 15, "category": "Письмо", "emoji": "✏️"},
    {"id": "p6", "name": "Ластик", "price": 20, "category": "Письмо", "emoji": "🧽"},
    {"id": "p7", "name": "Линейка 30 см", "price": 35, "category": "Черчение", "emoji": "📏"},
    {"id": "p8", "name": "Циркуль", "price": 90, "category": "Черчение", "emoji": "📐"},
    {"id": "p9", "name": "Папка-скоросшиватель", "price": 50, "category": "Папки", "emoji": "📁"},
    {"id": "p10", "name": "Файлы А4 100 шт.", "price": 150, "category": "Папки", "emoji": "📄"},
    {"id": "p11", "name": "Клей-карандаш", "price": 40, "category": "Клей/скотч", "emoji": "📎"},
    {"id": "p12", "name": "Скотч широкий", "price": 60, "category": "Клей/скотч", "emoji": "📦"},
]
# ============================================

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def load_data():
    empty = {
        "products": list(DEFAULT_PRODUCTS),
        "users": {},
        "orders": {},
        "meta": {},
    }
    if not os.path.exists(DATA_FILE):
        save_data(empty)
        return empty
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("products", list(DEFAULT_PRODUCTS))
        data.setdefault("users", {})
        data.setdefault("orders", {})
        return data
    except Exception:
        return empty


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_admin(uid):
    try:
        return int(uid) in ADMIN_IDS
    except Exception:
        return False


def register_user(user):
    if not user:
        return
    data = load_data()
    uid = str(user.id)
    prev = data["users"].get(uid, {})
    data["users"][uid] = {
        "id": int(user.id),
        "name": f"{user.first_name or ''} {getattr(user, 'last_name', '') or ''}".strip(),
        "username": user.username or "",
        "registered_at": prev.get("registered_at") or datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    save_data(data)


def money(price):
    if CURRENCY == "KGS":
        return f"{int(price)} сом"
    return f"${price}"


def find_product(pid):
    data = load_data()
    for p in data["products"]:
        if p["id"] == pid:
            return p
    return None


def categories(products):
    cats = []
    for p in products:
        c = p.get("category") or "Разное"
        if c not in cats:
            cats.append(c)
    return cats


def main_keyboard(admin=False):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🛍 Каталог", "🛒 Мои заказы")
    kb.row("💳 Реквизиты", "ℹ️ Помощь")
    if admin:
        kb.row("👑 Админ")
    return kb


def catalog_categories_kb(products):
    kb = types.InlineKeyboardMarkup()
    for cat in categories(products):
        kb.add(types.InlineKeyboardButton(f"📂 {cat}", callback_data=f"cat:{cat[:40]}"))
    kb.add(types.InlineKeyboardButton("📋 Все товары", callback_data="cat:__all__"))
    return kb


def products_kb(products, category=None):
    kb = types.InlineKeyboardMarkup()
    for p in products:
        if category and category != "__all__" and (p.get("category") or "Разное") != category:
            continue
        em = p.get("emoji") or "📦"
        kb.add(
            types.InlineKeyboardButton(
                f"{em} {p['name']} — {money(p['price'])}",
                callback_data=f"buy:{p['id']}",
            )
        )
    kb.add(types.InlineKeyboardButton("⬅️ К категориям", callback_data="cats"))
    return kb


def product_action_kb(pid):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Я оплатил", callback_data=f"paid:{pid}"),
        types.InlineKeyboardButton("📷 QR ещё раз", callback_data=f"qr:{pid}"),
    )
    kb.row(types.InlineKeyboardButton("⬅️ В каталог", callback_data="cats"))
    return kb


def admin_order_kb(order_id):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"ok:{order_id}"),
        types.InlineKeyboardButton("❌ Не пришло", callback_data=f"no:{order_id}"),
    )
    return kb


def make_qr_png(payload: str) -> bytes:
    """Генерирует PNG QR-кода."""
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def qr_payload(product, order_id=None):
    """
    Текст внутри QR — телефон + сумма + товар.
    Клиент может отсканировать и увидеть реквизиты;
    перевод вручную на номер.
    """
    lines = [
        f"Оплата: {PAYEE_NAME}",
        f"Тел: {PAYEE_PHONE}",
        f"Сумма: {money(product['price'])}",
        f"Товар: {product['name']}",
    ]
    if order_id:
        lines.append(f"Заказ: #{order_id}")
    return "\n".join(lines)


def notify_admins(text, reply_markup=None):
    for a in ADMIN_IDS:
        try:
            bot.send_message(a, text, reply_markup=reply_markup)
        except Exception as e:
            print("admin notify", e)


def send_product_qr(chat_id, product, order_id=None):
    payload = qr_payload(product, order_id)
    png = make_qr_png(payload)
    caption = (
        f"{product.get('emoji') or '📦'} <b>{product['name']}</b>\n"
        f"💰 Цена: <b>{money(product['price'])}</b>\n\n"
        f"👤 Получатель: <b>{PAYEE_NAME}</b>\n"
        f"📱 Перевод: <code>{PAYEE_PHONE}</code>\n"
    )
    if order_id:
        caption += f"🧾 Заказ: <b>#{order_id}</b>\n"
        caption += f"В комментарии к платежу укажи: <code>#{order_id}</code>\n"
    caption += "\nОтсканируй QR или переведи на номер → затем «Я оплатил»."

    bio = io.BytesIO(png)
    bio.name = "qr.png"
    bot.send_photo(
        chat_id,
        bio,
        caption=caption,
        reply_markup=product_action_kb(product["id"]) if not order_id else product_action_kb(product["id"]),
    )
    # для заказа кнопки с order id удобнее
    if order_id:
        kb = types.InlineKeyboardMarkup()
        kb.row(
            types.InlineKeyboardButton("✅ Я оплатил", callback_data=f"opaid:{order_id}"),
            types.InlineKeyboardButton("📷 QR", callback_data=f"oqr:{order_id}"),
        )
        kb.row(types.InlineKeyboardButton("⬅️ Каталог", callback_data="cats"))
        try:
            bot.send_message(chat_id, "После оплаты нажми кнопку:", reply_markup=kb)
        except Exception:
            pass


# ---------- commands ----------
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    register_user(message.from_user)
    admin = is_admin(message.from_user.id)
    text = (
        "📒 <b>Канцтовары — оплата через QR</b>\n\n"
        "1) Открой <b>Каталог</b>\n"
        "2) Выбери товар\n"
        "3) Получи <b>QR + цену</b>\n"
        "4) Оплати и нажми «Я оплатил»\n"
    )
    if admin:
        text += (
            "\n👑 <b>Админ</b>\n"
            "<code>/add Название | цена | категория</code>\n"
            "Пример: <code>/add Степлер | 250 | Офис</code>\n"
            "/products — список\n"
            "/del ID — удалить\n"
            "/orders — заказы\n"
            "/users — клиенты\n"
        )
    bot.send_message(message.chat.id, text, reply_markup=main_keyboard(admin))


@bot.message_handler(commands=["requisites"])
def cmd_req(message):
    register_user(message.from_user)
    bot.reply_to(
        message,
        f"💳 <b>Реквизиты</b>\n\n👤 {PAYEE_NAME}\n📱 <code>{PAYEE_PHONE}</code>",
    )


@bot.message_handler(commands=["add"])
def cmd_add(message):
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").replace("/add", "", 1).strip()
    # Название | цена | категория
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) < 2:
        bot.reply_to(message, "Формат:\n<code>/add Степлер | 250 | Офис</code>")
        return
    name = parts[0]
    try:
        price = float(parts[1].replace(" ", "").replace(",", "."))
    except ValueError:
        bot.reply_to(message, "Цена — число.")
        return
    cat = parts[2] if len(parts) > 2 else "Разное"
    emoji = parts[3] if len(parts) > 3 else "📦"
    data = load_data()
    pid = "p" + uuid.uuid4().hex[:6]
    data["products"].append({
        "id": pid,
        "name": name,
        "price": price,
        "category": cat,
        "emoji": emoji,
    })
    save_data(data)
    bot.reply_to(message, f"✅ Добавлено: {emoji} <b>{name}</b> — {money(price)}\nID: <code>{pid}</code>")


@bot.message_handler(commands=["del"])
def cmd_del(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        bot.reply_to(message, "<code>/del ID</code> — смотри /products")
        return
    pid = parts[1].strip()
    data = load_data()
    before = len(data["products"])
    data["products"] = [p for p in data["products"] if p["id"] != pid]
    save_data(data)
    bot.reply_to(message, "Удалено." if len(data["products"]) < before else "ID не найден.")


@bot.message_handler(commands=["products"])
def cmd_products(message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    if not data["products"]:
        bot.reply_to(message, "Каталог пуст.")
        return
    lines = ["📦 <b>Товары</b>\n"]
    for p in data["products"]:
        lines.append(
            f"{p.get('emoji') or '📦'} <code>{p['id']}</code> · {p['name']} — "
            f"<b>{money(p['price'])}</b> · {p.get('category') or '—'}"
        )
    buf = ""
    for line in lines:
        if len(buf) + len(line) > 3500:
            bot.send_message(message.chat.id, buf)
            buf = line + "\n"
        else:
            buf += line + "\n"
    if buf:
        bot.send_message(message.chat.id, buf)


@bot.message_handler(commands=["orders"])
def cmd_orders(message):
    if not is_admin(message.from_user.id):
        return
    data = load_data()
    orders = list(data["orders"].values())
    orders.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    if not orders:
        bot.reply_to(message, "Заказов нет.")
        return
    for o in orders[:20]:
        st = o.get("status")
        mark = {"pending": "⏳", "waiting": "🔎", "paid": "✅", "rejected": "❌"}.get(st, st)
        bot.send_message(
            message.chat.id,
            f"{mark} <b>#{o['id']}</b> · {o.get('product_name')} · {money(o.get('price'))}\n"
            f"Клиент: {o.get('client_name')} (<code>{o.get('client_id')}</code>)\n"
            f"Статус: {st} · {o.get('created_at')}",
            reply_markup=admin_order_kb(o["id"]) if st == "waiting" else None,
        )


@bot.message_handler(commands=["users"])
def cmd_users(message):
    if not is_admin(message.from_user.id):
        return
    users = list(load_data()["users"].values())
    bot.reply_to(message, f"👥 В базе: <b>{len(users)}</b>")
    buf = ""
    for u in users[-40:]:
        line = f"· {u.get('name')} @{u.get('username') or '—'} <code>{u.get('id')}</code>\n"
        buf += line
        if len(buf) > 3500:
            bot.send_message(message.chat.id, buf)
            buf = ""
    if buf:
        bot.send_message(message.chat.id, buf)


@bot.message_handler(commands=["setprice"])
def cmd_setprice(message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        bot.reply_to(message, "<code>/setprice ID 150</code>")
        return
    pid = parts[1]
    try:
        price = float(parts[2].replace(",", "."))
    except ValueError:
        bot.reply_to(message, "Цена — число")
        return
    data = load_data()
    for p in data["products"]:
        if p["id"] == pid:
            p["price"] = price
            save_data(data)
            bot.reply_to(message, f"OK: {p['name']} = {money(price)}")
            return
    bot.reply_to(message, "ID не найден")


# ---------- reply buttons ----------
@bot.message_handler(func=lambda m: m.text == "🛍 Каталог")
def btn_catalog(message):
    register_user(message.from_user)
    data = load_data()
    if not data["products"]:
        bot.reply_to(message, "Каталог пуст. Админ ещё не добавил товары.")
        return
    bot.send_message(
        message.chat.id,
        "Выбери категорию:",
        reply_markup=catalog_categories_kb(data["products"]),
    )


@bot.message_handler(func=lambda m: m.text == "💳 Реквизиты")
def btn_req(message):
    cmd_req(message)


@bot.message_handler(func=lambda m: m.text == "ℹ️ Помощь")
def btn_help(message):
    cmd_start(message)


@bot.message_handler(func=lambda m: m.text == "🛒 Мои заказы")
def btn_my(message):
    register_user(message.from_user)
    data = load_data()
    uid = message.from_user.id
    orders = [o for o in data["orders"].values() if o.get("client_id") == uid]
    orders.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    if not orders:
        bot.reply_to(message, "Заказов пока нет. Открой 🛍 Каталог.")
        return
    for o in orders[:10]:
        st = {"pending": "⏳", "waiting": "🔎", "paid": "✅", "rejected": "❌"}.get(o.get("status"), "")
        bot.send_message(
            message.chat.id,
            f"{st} <b>#{o['id']}</b> · {o.get('product_name')} · {money(o.get('price'))}\n"
            f"Статус: {o.get('status')} · {o.get('created_at')}",
        )


@bot.message_handler(func=lambda m: m.text == "👑 Админ")
def btn_admin(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "Нет доступа.")
        return
    bot.reply_to(
        message,
        "👑 <b>Админ</b>\n\n"
        "<code>/add Название | цена | категория</code>\n"
        "<code>/add Степлер | 250 | Офис</code>\n"
        "/products — все товары\n"
        "/del ID\n"
        "/setprice ID цена\n"
        "/orders — заказы\n"
        "/users",
    )


# ---------- callbacks ----------
@bot.callback_query_handler(func=lambda c: True)
def on_cb(call):
    try:
        raw = (call.data or "").strip()
        data = load_data()

        if raw == "cats":
            bot.answer_callback_query(call.id)
            bot.send_message(
                call.message.chat.id,
                "Категории:",
                reply_markup=catalog_categories_kb(data["products"]),
            )
            return

        if raw.startswith("cat:"):
            cat = raw[4:]
            bot.answer_callback_query(call.id)
            bot.send_message(
                call.message.chat.id,
                f"Товары: <b>{'Все' if cat == '__all__' else cat}</b>",
                reply_markup=products_kb(data["products"], None if cat == "__all__" else cat),
            )
            return

        if raw.startswith("buy:"):
            pid = raw[4:]
            product = find_product(pid)
            if not product:
                bot.answer_callback_query(call.id, "Товар не найден", show_alert=True)
                return
            bot.answer_callback_query(call.id, "Формирую QR...")
            register_user(call.from_user)
            # создаём заказ
            order_id = uuid.uuid4().hex[:8].upper()
            order = {
                "id": order_id,
                "product_id": product["id"],
                "product_name": product["name"],
                "price": product["price"],
                "currency": CURRENCY,
                "client_id": call.from_user.id,
                "client_name": f"{call.from_user.first_name or ''} @{call.from_user.username or ''}".strip(),
                "status": "pending",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            data = load_data()
            data["orders"][order_id] = order
            save_data(data)
            send_product_qr(call.message.chat.id, product, order_id=order_id)
            return

        if raw.startswith("qr:"):
            pid = raw[3:]
            product = find_product(pid)
            if not product:
                bot.answer_callback_query(call.id, "Нет товара", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            send_product_qr(call.message.chat.id, product)
            return

        if raw.startswith("oqr:"):
            oid = raw[4:].upper()
            order = load_data()["orders"].get(oid)
            if not order:
                bot.answer_callback_query(call.id, "Заказ не найден", show_alert=True)
                return
            product = find_product(order["product_id"]) or {
                "id": order["product_id"],
                "name": order["product_name"],
                "price": order["price"],
                "emoji": "📦",
            }
            bot.answer_callback_query(call.id)
            send_product_qr(call.message.chat.id, product, order_id=oid)
            return

        if raw.startswith("opaid:") or raw.startswith("paid:"):
            # paid:pid  or  opaid:ORDER
            register_user(call.from_user)
            if raw.startswith("opaid:"):
                oid = raw[6:].upper()
                data = load_data()
                order = data["orders"].get(oid)
                if not order:
                    bot.answer_callback_query(call.id, "Заказ не найден", show_alert=True)
                    return
            else:
                # paid without order — create minimal
                pid = raw[5:]
                product = find_product(pid)
                if not product:
                    bot.answer_callback_query(call.id, "Нет товара", show_alert=True)
                    return
                data = load_data()
                oid = uuid.uuid4().hex[:8].upper()
                order = {
                    "id": oid,
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "price": product["price"],
                    "client_id": call.from_user.id,
                    "client_name": f"{call.from_user.first_name or ''} @{call.from_user.username or ''}".strip(),
                    "status": "waiting",
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
                data["orders"][oid] = order
                save_data(data)

            data = load_data()
            order = data["orders"].get(oid) or order
            order["status"] = "waiting"
            order["claimed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            data["orders"][oid] = order
            save_data(data)

            bot.answer_callback_query(call.id, "На проверке")
            bot.send_message(
                call.message.chat.id,
                f"🔎 Заказ <b>#{oid}</b> на проверке.\nОжидайте подтверждения.",
            )
            notify_admins(
                f"🔎 Оплата канцтоваров?\n"
                f"Заказ <b>#{oid}</b>\n"
                f"Товар: {order.get('product_name')}\n"
                f"Сумма: <b>{money(order.get('price'))}</b>\n"
                f"Клиент: {order.get('client_name')} (<code>{order.get('client_id')}</code>)",
                reply_markup=admin_order_kb(oid),
            )
            return

        if raw.startswith("ok:") or raw.startswith("no:"):
            if not is_admin(call.from_user.id):
                bot.answer_callback_query(call.id, "Только админ", show_alert=True)
                return
            oid = raw[3:].upper()
            data = load_data()
            order = data["orders"].get(oid)
            if not order:
                bot.answer_callback_query(call.id, "Нет заказа", show_alert=True)
                return
            if raw.startswith("ok:"):
                order["status"] = "paid"
                order["paid_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                data["orders"][oid] = order
                save_data(data)
                bot.answer_callback_query(call.id, "Подтверждено")
                try:
                    bot.edit_message_text(
                        f"✅ ОПЛАЧЕНО\n#{oid} · {order.get('product_name')} · {money(order.get('price'))}",
                        call.message.chat.id,
                        call.message.message_id,
                    )
                except Exception:
                    pass
                try:
                    bot.send_message(
                        int(order["client_id"]),
                        f"✅ Оплата по заказу <b>#{oid}</b> подтверждена.\n"
                        f"Товар: {order.get('product_name')}\nСпасибо!",
                    )
                except Exception:
                    pass
            else:
                order["status"] = "pending"
                data["orders"][oid] = order
                save_data(data)
                bot.answer_callback_query(call.id, "Отклонено")
                try:
                    bot.edit_message_text(
                        f"❌ НЕ НАЙДЕНО\n#{oid} · {order.get('product_name')}",
                        call.message.chat.id,
                        call.message.message_id,
                    )
                except Exception:
                    pass
                try:
                    bot.send_message(
                        int(order["client_id"]),
                        f"❌ По заказу <b>#{oid}</b> оплата не найдена.\n"
                        f"Проверьте перевод на <code>{PAYEE_PHONE}</code> и нажмите «Я оплатил» снова.",
                    )
                except Exception:
                    pass
            return

        bot.answer_callback_query(call.id)
    except Exception as e:
        print("callback error:", e)
        try:
            bot.answer_callback_query(call.id, "Ошибка", show_alert=True)
        except Exception:
            pass


@bot.message_handler(func=lambda m: True, content_types=["text"])
def fallback(message):
    register_user(message.from_user)
    if is_admin(message.from_user.id):
        bot.reply_to(message, "Кнопки меню или /add /products /orders /help")
    else:
        bot.reply_to(message, "Жми 🛍 Каталог или /start")


def main():
    print("Stationery payment bot starting...")
    try:
        bot.remove_webhook()
    except Exception:
        pass
    # init data
    load_data()
    notify_admins(
        "📒 <b>Бот канцтоваров запущен</b>\n"
        f"Оплата: {PAYEE_NAME} · {PAYEE_PHONE}\n"
        "Клиент: Каталог → товар → QR\n"
        "Админ: /add · /products · /orders"
    )
    bot.infinity_polling(timeout=60, long_polling_timeout=40, skip_pending=True)


if __name__ == "__main__":
    main()
